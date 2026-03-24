use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Get earnings data (balance, pending, per_campaign, per_platform, payout_history)
#[tauri::command]
pub async fn get_earnings(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("get_earnings", json!({}))
}

/// Request a payout withdrawal
#[tauri::command]
pub async fn request_payout(state: State<'_, AppState>, amount: f64) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("request_payout", json!({ "amount": amount }))
}
