use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Open browser for platform login (delegates to login_setup.py)
#[tauri::command]
pub async fn connect_platform(
    state: State<'_, AppState>,
    platform: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("connect_platform", json!({"platform": platform}))
}

/// Trigger a profile re-scrape for a platform
#[tauri::command]
pub async fn refresh_profile(
    state: State<'_, AppState>,
    platform: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("refresh_profile", json!({"platform": platform}))
}
