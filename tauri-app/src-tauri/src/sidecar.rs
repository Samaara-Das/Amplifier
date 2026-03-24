use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use log::{info, warn};

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

/// Manages the Python sidecar process lifecycle
#[allow(dead_code)]
pub struct SidecarManager {
    process: Option<Child>,
    project_root: String,
    request_id: AtomicU64,
    restart_count: u32,
    max_restarts: u32,
}

impl SidecarManager {
    pub fn new(project_root: String) -> Self {
        Self {
            process: None,
            project_root,
            request_id: AtomicU64::new(1),
            restart_count: 0,
            max_restarts: 3,
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

        let child = Command::new("python")
            .arg(sidecar_script.to_str().unwrap())
            .arg("--project-root")
            .arg(&self.project_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .current_dir(&self.project_root)
            .spawn()
            .map_err(|e| format!("Failed to spawn Python sidecar: {}", e))?;

        info!("Python sidecar spawned with PID: {}", child.id());
        self.process = Some(child);
        self.restart_count = 0;

        Ok(())
    }

    /// Send a JSON-RPC request to the sidecar and wait for a response
    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        // Ensure sidecar is running
        if !self.is_running() {
            self.spawn()?;
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

        let process = self
            .process
            .as_mut()
            .ok_or("Sidecar process not available")?;

        // Write request to stdin
        let stdin = process
            .stdin
            .as_mut()
            .ok_or("Sidecar stdin not available")?;
        writeln!(stdin, "{}", request_str)
            .map_err(|e| format!("Failed to write to sidecar stdin: {}", e))?;
        stdin
            .flush()
            .map_err(|e| format!("Failed to flush sidecar stdin: {}", e))?;

        // Read response from stdout
        let stdout = process
            .stdout
            .as_mut()
            .ok_or("Sidecar stdout not available")?;
        let mut reader = BufReader::new(stdout);
        let mut response_line = String::new();
        reader
            .read_line(&mut response_line)
            .map_err(|e| format!("Failed to read sidecar response: {}", e))?;

        if response_line.trim().is_empty() {
            // Sidecar may have crashed
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
                Ok(Some(_status)) => {
                    // Process has exited
                    self.process = None;
                    false
                }
                Ok(None) => true,  // Still running
                Err(_) => false,
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

    /// Restart the sidecar if it has crashed, with backoff
    #[allow(dead_code)]
    pub fn restart_if_needed(&mut self) -> Result<(), String> {
        if self.is_running() {
            return Ok(());
        }

        if self.restart_count >= self.max_restarts {
            return Err(format!(
                "Sidecar exceeded max restart attempts ({})",
                self.max_restarts
            ));
        }

        self.restart_count += 1;
        let backoff = Duration::from_secs(2u64.pow(self.restart_count));
        warn!(
            "Sidecar crashed. Restarting (attempt {}/{}) after {:?}...",
            self.restart_count, self.max_restarts, backoff
        );

        std::thread::sleep(backoff);
        self.spawn()
    }

    /// Gracefully shut down the sidecar
    pub fn shutdown(&mut self) {
        if let Some(ref mut child) = self.process {
            info!("Shutting down Python sidecar...");
            // Try to send shutdown command
            if let Some(ref mut stdin) = child.stdin {
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
            std::thread::sleep(Duration::from_secs(2));

            // Force kill if still running
            match child.try_wait() {
                Ok(Some(_)) => info!("Sidecar exited gracefully"),
                _ => {
                    warn!("Force-killing sidecar process");
                    let _ = child.kill();
                }
            }
        }
        self.process = None;
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        self.shutdown();
    }
}
