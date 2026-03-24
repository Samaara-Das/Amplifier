use serde_json::{json, Value};
use tauri::State;

use crate::state::AppState;

/// Register a new user account with the server
#[tauri::command]
pub async fn register(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("register", json!({
        "email": email,
        "password": password,
    }))
}

/// Log in to an existing account
#[tauri::command]
pub async fn login(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("login", json!({
        "email": email,
        "password": password,
    }))
}

/// Scrape platform profile data (followers, engagement, etc.)
#[tauri::command]
pub async fn scrape_platform(
    state: State<'_, AppState>,
    platform: String,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("scrape_platform", json!({"platform": platform}))
}

/// Classify user niches based on connected platform content
#[tauri::command]
pub async fn classify_niches(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("classify_niches", json!({}))
}

/// Logout — clear auth token and reset onboarding
#[tauri::command]
pub async fn logout(state: State<'_, AppState>) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("logout", json!({}))
}

/// Save onboarding settings (mode, niches, platforms)
#[tauri::command]
pub async fn save_onboarding(
    state: State<'_, AppState>,
    mode: String,
    niches: Value,
    platforms: Value,
) -> Result<Value, String> {
    let mut sidecar = state.sidecar.lock().await;
    sidecar.call("save_onboarding", json!({
        "mode": mode,
        "niches": niches,
        "platforms": platforms,
    }))
}
