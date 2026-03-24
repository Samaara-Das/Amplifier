use std::sync::Arc;
use tokio::sync::Mutex;

use crate::sidecar::SidecarManager;

/// Shared application state accessible from all Tauri commands
#[allow(dead_code)]
pub struct AppState {
    pub sidecar: Arc<Mutex<SidecarManager>>,
    pub project_root: String,
}

impl AppState {
    pub fn new(project_root: String) -> Self {
        Self {
            sidecar: Arc::new(Mutex::new(SidecarManager::new(project_root.clone()))),
            project_root,
        }
    }
}
