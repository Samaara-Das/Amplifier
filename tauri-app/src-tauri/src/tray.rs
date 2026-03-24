use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};
use log::info;

/// Set up the system tray icon and context menu
pub fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let open_dashboard = MenuItem::with_id(app, "open_dashboard", "Open Dashboard", true, None::<&str>)?;
    let separator1 = PredefinedMenuItem::separator(app)?;
    let pause_posting = MenuItem::with_id(app, "pause_posting", "Pause Posting", true, None::<&str>)?;
    let separator2 = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Amplifier", true, None::<&str>)?;

    let menu = Menu::with_items(
        app,
        &[&open_dashboard, &separator1, &pause_posting, &separator2, &quit],
    )?;

    let _tray = TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("Amplifier")
        .icon(Image::from_path("icons/icon.png").unwrap_or_else(|_| {
            // Fallback: try to load from resource path
            Image::from_bytes(include_bytes!("../icons/icon.png"))
                .expect("Failed to load tray icon")
        }))
        .on_menu_event(move |app, event| {
            match event.id.as_ref() {
                "open_dashboard" => {
                    info!("Tray: Open Dashboard");
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "pause_posting" => {
                    info!("Tray: Toggle pause posting");
                    // TODO: Toggle posting state via sidecar
                }
                "quit" => {
                    info!("Tray: Quit");
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(|tray, event| {
            // Click on tray icon opens the main window
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}
