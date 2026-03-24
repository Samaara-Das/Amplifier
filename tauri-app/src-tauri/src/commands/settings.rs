use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Get current user settings
#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_settings", json!({}))
}

/// Update user settings (mode, notifications, etc.)
#[tauri::command]
pub async fn update_settings(
    state: State<'_, AppState>,
    settings: Value,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("update_settings", json!({"settings": settings}))
}
