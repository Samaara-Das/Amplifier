use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use log::{info, warn, error};

/// JSON-RPC request sent from Rust to Python
#[derive(Debug, Serialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    method: String,
    params: Value,
    id: u64,
}

/// JSON-RPC response received from Python
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct JsonRpcResponse {
    jsonrpc: String,
    result: Option<Value>,
    error: Option<JsonRpcError>,
    id: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct JsonRpcError {
    code: i64,
    message: String,
    data: Option<Value>,
}

/// Manages the Python sidecar process lifecycle.
///
/// Stdin and stdout are taken from the Child process and stored separately
/// so that BufReader persists across calls (avoiding lost buffered data).
pub struct SidecarManager {
    process: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout_reader: Option<BufReader<ChildStdout>>,
    project_root: String,
    request_id: AtomicU64,
    restart_count: u32,
    max_restarts: u32,
}

impl SidecarManager {
    pub fn new(project_root: String) -> Self {
        Self {
            process: None,
            stdin: None,
            stdout_reader: None,
            project_root,
            request_id: AtomicU64::new(1),
            restart_count: 0,
            max_restarts: 5,
        }
    }

    /// Spawn the Python sidecar process
    pub fn spawn(&mut self) -> Result<(), String> {
        if self.process.is_some() {
            return Ok(()); // Already running
        }

        let sidecar_script = std::path::Path::new(&self.project_root)
            .join("scripts")
            .join("sidecar_main.py");

        if !sidecar_script.exists() {
            return Err(format!(
                "Sidecar script not found: {}",
                sidecar_script.display()
            ));
        }

        info!("Spawning Python sidecar: {}", sidecar_script.display());
        info!("Project root: {}", self.project_root);

        // On Windows, try "python" first. The command inherits PATH from the parent process.
        let mut cmd = Command::new("python");
        cmd.arg(sidecar_script.to_str().unwrap())
            .arg("--project-root")
            .arg(&self.project_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .current_dir(&self.project_root);

        // On Windows, prevent a console window from appearing
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = cmd.spawn()
            .map_err(|e| format!("Failed to spawn Python sidecar: {}", e))?;

        info!("Python sidecar spawned with PID: {}", child.id());

        // Take ownership of stdin and stdout from the child process.
        // This is crucial: BufReader must persist across calls to avoid losing buffered data.
        let stdin = child.stdin.take()
            .ok_or("Failed to take stdin from sidecar process")?;
        let stdout = child.stdout.take()
            .ok_or("Failed to take stdout from sidecar process")?;
        let reader = BufReader::new(stdout);

        // Spawn a thread to drain stderr so it doesn't block the sidecar
        if let Some(stderr) = child.stderr.take() {
            std::thread::spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines() {
                    match line {
                        Ok(l) => info!("[sidecar-stderr] {}", l),
                        Err(_) => break,
                    }
                }
            });
        }

        self.process = Some(child);
        self.stdin = Some(stdin);
        self.stdout_reader = Some(reader);
        self.restart_count = 0;

        // Wait briefly for the sidecar to initialize, then verify with a ping
        std::thread::sleep(Duration::from_millis(500));

        Ok(())
    }

    /// Send a JSON-RPC request to the sidecar and wait for a response
    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        // Ensure sidecar is running
        if !self.is_running() {
            info!("Sidecar not running, spawning...");
            self.try_restart()?;
        }

        let id = self.request_id.fetch_add(1, Ordering::SeqCst);
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            method: method.to_string(),
            params,
            id,
        };

        let request_str =
            serde_json::to_string(&request).map_err(|e| format!("Serialize error: {}", e))?;

        // Write request to stdin
        let stdin = self.stdin.as_mut().ok_or("Sidecar stdin not available")?;
        if let Err(e) = writeln!(stdin, "{}", request_str) {
            error!("Failed to write to sidecar stdin: {}", e);
            self.cleanup();
            return Err(format!("Failed to write to sidecar stdin: {}", e));
        }
        if let Err(e) = stdin.flush() {
            error!("Failed to flush sidecar stdin: {}", e);
            self.cleanup();
            return Err(format!("Failed to flush sidecar stdin: {}", e));
        }

        // Read response from stdout (using persistent BufReader)
        let reader = self.stdout_reader.as_mut().ok_or("Sidecar stdout not available")?;
        let mut response_line = String::new();
        match reader.read_line(&mut response_line) {
            Ok(0) => {
                // EOF — sidecar process has closed stdout
                error!("Sidecar stdout closed (EOF)");
                self.cleanup();
                return Err("Sidecar process closed (EOF)".to_string());
            }
            Ok(_) => {}
            Err(e) => {
                error!("Failed to read sidecar response: {}", e);
                self.cleanup();
                return Err(format!("Failed to read sidecar response: {}", e));
            }
        }

        if response_line.trim().is_empty() {
            return Err("Sidecar returned empty response (may have crashed)".to_string());
        }

        let response: JsonRpcResponse = serde_json::from_str(response_line.trim())
            .map_err(|e| format!("Failed to parse sidecar response: {} | raw: {}", e, response_line.trim()))?;

        if let Some(err) = response.error {
            return Err(format!(
                "Sidecar error ({}): {} {:?}",
                err.code, err.message, err.data
            ));
        }

        Ok(response.result.unwrap_or(Value::Null))
    }

    /// Check if the sidecar process is still running
    pub fn is_running(&mut self) -> bool {
        if let Some(ref mut child) = self.process {
            match child.try_wait() {
                Ok(Some(status)) => {
                    // Process has exited
                    warn!("Sidecar process exited with status: {}", status);
                    self.cleanup();
                    false
                }
                Ok(None) => true,  // Still running
                Err(e) => {
                    warn!("Error checking sidecar status: {}", e);
                    false
                }
            }
        } else {
            false
        }
    }

    /// Health check — ping the sidecar
    pub fn health_check(&mut self) -> Result<bool, String> {
        match self.call("ping", json!({})) {
            Ok(result) => {
                if result.get("status").and_then(|s| s.as_str()) == Some("pong") {
                    Ok(true)
                } else {
                    Ok(false)
                }
            }
            Err(e) => {
                warn!("Sidecar health check failed: {}", e);
                Ok(false)
            }
        }
    }

    /// Try to restart the sidecar with backoff
    fn try_restart(&mut self) -> Result<(), String> {
        if self.restart_count >= self.max_restarts {
            return Err(format!(
                "Sidecar exceeded max restart attempts ({})",
                self.max_restarts
            ));
        }

        self.restart_count += 1;
        let backoff = Duration::from_millis(500 * (self.restart_count as u64));
        warn!(
            "Restarting sidecar (attempt {}/{}) after {:?}...",
            self.restart_count, self.max_restarts, backoff
        );

        std::thread::sleep(backoff);
        self.spawn()
    }

    /// Clean up resources without killing (process may already be dead)
    fn cleanup(&mut self) {
        self.stdin = None;
        self.stdout_reader = None;
        self.process = None;
    }

    /// Gracefully shut down the sidecar
    pub fn shutdown(&mut self) {
        if self.process.is_some() {
            info!("Shutting down Python sidecar...");
            // Try to send shutdown command via stdin
            if let Some(ref mut stdin) = self.stdin {
                let shutdown_req = json!({
                    "jsonrpc": "2.0",
                    "method": "shutdown",
                    "params": {},
                    "id": 0
                });
                let _ = writeln!(stdin, "{}", shutdown_req);
                let _ = stdin.flush();
            }

            // Wait briefly for graceful shutdown
            std::thread::sleep(Duration::from_secs(1));

            // Force kill if still running
            if let Some(ref mut child) = self.process {
                match child.try_wait() {
                    Ok(Some(_)) => info!("Sidecar exited gracefully"),
                    _ => {
                        warn!("Force-killing sidecar process");
                        let _ = child.kill();
                    }
                }
            }
        }
        self.cleanup();
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.shutdown();
    }
}
