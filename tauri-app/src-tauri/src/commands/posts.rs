use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Get all posts grouped by status (pending_review, scheduled, posted, failed)
#[tauri::command]
pub async fn get_posts(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_posts", json!({}))
}

/// Edit content for a specific platform draft
#[tauri::command]
pub async fn edit_content(
    state: State<'_, AppState>,
    campaign_id: u64,
    platform: String,
    content: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("edit_content", json!({
        "campaign_id": campaign_id,
        "platform": platform,
        "content": content,
    }))
}

/// Regenerate content for a specific platform
#[tauri::command]
pub async fn regenerate_content(
    state: State<'_, AppState>,
    campaign_id: u64,
    platform: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("regenerate_content", json!({
        "campaign_id": campaign_id,
        "platform": platform,
    }))
}

/// Approve content for a specific platform (or all platforms)
#[tauri::command]
pub async fn approve_content(
    state: State<'_, AppState>,
    campaign_id: u64,
    platform: Option<String>,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    let mut params = json!({"campaign_id": campaign_id});
    if let Some(p) = platform {
        params["platform"] = json!(p);
    }
    sidecar.call("approve_content", params)
}

/// Skip content for a campaign
#[tauri::command]
pub async fn skip_content(
    state: State<'_, AppState>,
    campaign_id: u64,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("skip_content", json!({"campaign_id": campaign_id}))
}

/// Cancel a scheduled post
#[tauri::command]
pub async fn cancel_scheduled(
    state: State<'_, AppState>,
    schedule_id: u64,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("cancel_scheduled", json!({"schedule_id": schedule_id}))
}

/// Retry a failed post
#[tauri::command]
pub async fn retry_failed(
    state: State<'_, AppState>,
    schedule_id: u64,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("retry_failed", json!({"schedule_id": schedule_id}))
}
