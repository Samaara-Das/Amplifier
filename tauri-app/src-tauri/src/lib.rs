mod commands;
mod sidecar;
mod state;
mod tray;

use log::info;
use state::AppState;
use tauri::Manager;

/// Main Tauri app setup — called by main.rs
pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Determine project root by walking up from cwd until we find scripts/sidecar_main.py.
            // During `tauri dev`, cwd could be tauri-app/ or tauri-app/src-tauri/.
            let project_root = {
                let cwd = std::env::current_dir().unwrap();
                let mut candidate = cwd.as_path();
                loop {
                    if candidate.join("scripts").join("sidecar_main.py").exists() {
                        break candidate.to_path_buf();
                    }
                    match candidate.parent() {
                        Some(parent) => candidate = parent,
                        None => {
                            // Fallback: hardcoded project root for development
                            log::warn!("Could not find project root by walking up from {:?}, using fallback", cwd);
                            break std::path::PathBuf::from("C:\\Users\\dassa\\Work\\Auto-Posting-System");
                        }
                    }
                }
            };

            let project_root_str = project_root.to_string_lossy().to_string();
            info!("Project root: {}", project_root_str);

            // Initialize app state with sidecar manager
            let app_state = AppState::new(project_root_str);
            app.manage(app_state);

            // Set up system tray
            let app_handle = app.handle().clone();
            if let Err(e) = tray::setup_tray(&app_handle) {
                log::error!("Failed to set up system tray: {}", e);
            }

            // Intercept window close to minimize to tray instead of quitting
            let window = app.get_webview_window("main").unwrap();
            let window_handle = window.clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    // Prevent the window from actually closing — hide it instead
                    api.prevent_close();
                    let _ = window_handle.hide();
                    info!("Window hidden to system tray");
                }
            });

            // Spawn the Python sidecar in the background
            let sidecar_state = app.state::<AppState>();
            let sidecar = sidecar_state.sidecar.clone();
            tauri::async_runtime::spawn(async move {
                let mut manager = sidecar.lock().await;
                match manager.spawn() {
                    Ok(()) => info!("Python sidecar started successfully"),
                    Err(e) => log::error!("Failed to start Python sidecar: {}", e),
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Dashboard
            commands::dashboard::get_status,
            commands::dashboard::poll_campaigns,
            commands::dashboard::ping_sidecar,
            // Auth & onboarding
            commands::auth::register,
            commands::auth::login,
            commands::auth::scrape_platform,
            commands::auth::classify_niches,
            commands::auth::save_onboarding,
            // Campaigns
            commands::campaigns::get_invitations,
            commands::campaigns::accept_invitation,
            commands::campaigns::reject_invitation,
            commands::campaigns::get_campaigns,
            commands::campaigns::get_completed_campaigns,
            // Posts
            commands::posts::get_posts,
            commands::posts::edit_content,
            commands::posts::regenerate_content,
            commands::posts::approve_content,
            commands::posts::skip_content,
            commands::posts::cancel_scheduled,
            commands::posts::retry_failed,
            // Earnings
            commands::earnings::get_earnings,
            commands::earnings::request_payout,
            // Settings
            commands::settings::get_settings,
            commands::settings::update_settings,
            // Platforms
            commands::platforms::connect_platform,
            commands::platforms::disconnect_platform,
            commands::platforms::refresh_profile,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Amplifier");
}
