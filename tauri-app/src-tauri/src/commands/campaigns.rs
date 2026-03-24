use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Get pending campaign invitations
#[tauri::command]
pub async fn get_invitations(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_invitations", json!({}))
}

/// Accept a campaign invitation
#[tauri::command]
pub async fn accept_invitation(
    state: State<'_, AppState>,
    invitation_id: u64,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("accept_invitation", json!({"invitation_id": invitation_id}))
}

/// Reject a campaign invitation
#[tauri::command]
pub async fn reject_invitation(
    state: State<'_, AppState>,
    invitation_id: u64,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("reject_invitation", json!({"invitation_id": invitation_id}))
}

/// Get active campaigns
#[tauri::command]
pub async fn get_campaigns(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_campaigns", json!({}))
}

/// Get completed campaigns with final metrics
#[tauri::command]
pub async fn get_completed_campaigns(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_completed_campaigns", json!({}))
}
