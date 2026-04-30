"""System tray icon for Amplifier — keeps the app visible and accessible.

Shows a tray icon with right-click menu: Open Dashboard, Pause/Resume Agent,
Quit. Sends Windows desktop notifications for key events.
"""

import logging
import os
import threading
import webbrowser

logger = logging.getLogger(__name__)

# Lazy imports — these may not be installed in all environments
_pystray = None
_Image = None
_ImageDraw = None
_notification = None


def _ensure_imports():
    """Lazy import pystray and PIL to avoid import errors if not installed."""
    global _pystray, _Image, _ImageDraw, _notification
    if _pystray is None:
        try:
            import pystray
            from PIL import Image, ImageDraw
            _pystray = pystray
            _Image = Image
            _ImageDraw = ImageDraw
        except ImportError:
            logger.warning("pystray or Pillow not installed — tray icon disabled")
            return False
    if _notification is None:
        try:
            from plyer import notification
            _notification = notification
        except ImportError:
            logger.warning("plyer not installed — desktop notifications disabled")
    return True


def _create_icon_image(color="#2563eb"):
    """Create a simple 64x64 icon image with an 'A' on colored background."""
    _ensure_imports()
    if _Image is None:
        return None
    img = _Image.new("RGB", (64, 64), color)
    draw = _ImageDraw.Draw(img)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 36)
    except (OSError, ImportError):
        font = _ImageDraw.getfont() if hasattr(_ImageDraw, "getfont") else None
    draw.text((18, 10), "A", fill="white", font=font)
    return img


# ── Desktop Notifications ────────────────────────────────────────


def send_notification(title: str, message: str, timeout: int = 10):
    """Send a Windows desktop notification."""
    _ensure_imports()
    if _notification is None:
        logger.debug("Notification skipped (plyer not available): %s", title)
        return
    try:
        _notification.notify(
            title=title,
            message=message,
            app_name="Amplifier",
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)


# ── Tray Icon ────────────────────────────────────────────────────


_tray_icon = None
_tray_thread = None


def start_tray(port: int = 5222, on_quit=None):
    """Start the system tray icon in a background thread.

    Args:
        port: Local server port (for local menu items /drafts, /connect, /keys)
        on_quit: Callback when user clicks "Quit" (should stop local server + agent)
    """
    global _tray_icon, _tray_thread

    if not _ensure_imports():
        logger.warning("System tray not available — running without tray icon")
        return

    # Resolve hosted dashboard URL once at startup (not per-click)
    _server_base = os.getenv("CAMPAIGN_SERVER_URL", "https://api.pointcapitalis.com")
    hosted_url = f"{_server_base}/user/"

    def _open(url):
        """Open URL in a daemon thread to avoid blocking the tray event loop."""
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    def open_dashboard(icon, item):
        _open(hosted_url)

    def open_drafts(icon, item):
        _open(f"http://localhost:{port}/drafts")

    def open_connect(icon, item):
        _open(f"http://localhost:{port}/connect")

    def open_keys(icon, item):
        _open(f"http://localhost:{port}/keys")

    def pause_agent(icon, item):
        try:
            from background_agent import get_agent
            agent = get_agent()
            if agent:
                if agent.paused:
                    agent.resume()
                    send_notification("Amplifier", "Agent resumed")
                else:
                    agent.pause()
                    send_notification("Amplifier", "Agent paused")
                _update_menu(icon, port, on_quit)
        except Exception as e:
            logger.error("Failed to pause/resume agent: %s", e)

    def quit_app(icon, item):
        icon.stop()
        if on_quit:
            on_quit()

    def _get_agent_status():
        try:
            from background_agent import get_agent
            agent = get_agent()
            if agent and agent.running:
                return "Paused" if agent.paused else "Running"
        except Exception:
            pass
        return "Stopped"

    icon_image = _create_icon_image()
    if icon_image is None:
        return

    menu = _pystray.Menu(
        _pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        _pystray.MenuItem("Review Drafts", open_drafts),
        _pystray.MenuItem("Connect Platforms", open_connect),
        _pystray.MenuItem("API Keys", open_keys),
        _pystray.Menu.SEPARATOR,
        _pystray.MenuItem(
            lambda item: f"Agent: {_get_agent_status()}",
            None,
            enabled=False,
        ),
        _pystray.MenuItem(
            lambda item: "Resume Agent" if _is_agent_paused() else "Pause Agent",
            pause_agent,
        ),
        _pystray.Menu.SEPARATOR,
        _pystray.MenuItem("Quit Amplifier", quit_app),
    )

    _tray_icon = _pystray.Icon("amplifier", icon_image, "Amplifier", menu)

    _tray_thread = threading.Thread(target=_tray_icon.run, daemon=True)
    _tray_thread.start()
    logger.info("System tray icon started")


def _is_agent_paused():
    try:
        from background_agent import get_agent
        agent = get_agent()
        return agent.paused if agent else False
    except Exception:
        return False


def _update_menu(icon, port, on_quit):
    """Rebuild menu to reflect current agent state."""
    # pystray auto-updates dynamic menu items via lambdas
    pass


def stop_tray():
    """Stop the system tray icon."""
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass
        _tray_icon = None
        logger.info("System tray icon stopped")
