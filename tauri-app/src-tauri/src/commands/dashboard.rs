use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Get dashboard summary data (active campaigns, earnings, platform health, etc.)
#[tauri::command]
pub async fn get_status(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_status", json!({}))
}

/// Poll the server for new campaigns and invitations
#[tauri::command]
pub async fn poll_campaigns(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("poll_campaigns", json!({}))
}

/// Health check — ping the Python sidecar
#[tauri::command]
pub async fn ping_sidecar(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    match sidecar.health_check() {
        Ok(true) => Ok(json!({"status": "connected"})),
        Ok(false) => Ok(json!({"status": "unhealthy"})),
        Err(e) => Ok(json!({"status": "disconnected", "error": e})),
    }
}
