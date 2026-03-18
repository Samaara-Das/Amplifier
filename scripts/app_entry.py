"""Main entry point for the packaged desktop app.

Starts the campaign runner (background loop) and the dashboard (Flask) together.
Used as the PyInstaller entry point.
"""

import os
import sys
import threading
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

from utils.local_db import init_db, get_setting
from utils.server_client import is_logged_in

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def check_for_updates():
    """Check server for newer version and notify user."""
    from utils.server_client import _get_server_url, _get_headers
    import httpx

    current_version = "0.1.0"

    try:
        url = f"{_get_server_url()}/api/version"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("version") != current_version:
                logger.info(
                    "Update available: %s -> %s. Download: %s",
                    current_version, data["version"], data.get("download_url", ""),
                )
                return data
    except Exception:
        pass
    return None


def start_dashboard():
    """Start the campaign dashboard in a background thread."""
    from campaign_dashboard import app, init_db as dash_init
    dash_init()
    port = int(os.getenv("CAMPAIGN_DASHBOARD_PORT", "5222"))
    logger.info("Starting dashboard on http://localhost:%d", port)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def start_runner():
    """Start the campaign runner loop."""
    import asyncio
    from campaign_runner import run_poll_loop, init_db as runner_init
    runner_init()
    logger.info("Starting campaign runner...")
    asyncio.run(run_poll_loop())


def main():
    logger.info("Campaign Auto-Poster starting...")

    init_db()

    # Check if onboarding is needed
    if not is_logged_in():
        logger.info("Not logged in. Running onboarding...")
        from onboarding import run_onboarding
        run_onboarding()

    # Check for updates
    update_info = check_for_updates()
    if update_info:
        print(f"\n  Update available: v{update_info.get('version')}")
        print(f"  Download: {update_info.get('download_url', 'Check server')}\n")

    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard started in background")

    # Open dashboard in browser
    import webbrowser
    port = int(os.getenv("CAMPAIGN_DASHBOARD_PORT", "5222"))
    webbrowser.open(f"http://localhost:{port}")

    # Run campaign loop in main thread (blocking)
    start_runner()


if __name__ == "__main__":
    main()
