"""Tests for tray.py menu layout and server_client.py 401 handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Path setup ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_tray_menu(port=5222, env_server_url=None):
    """Call start_tray with mocked pystray and PIL, capture Menu construction args."""
    import utils.tray as tray_mod

    mock_pystray = MagicMock()
    mock_image = MagicMock()
    mock_draw = MagicMock()

    # MenuItem returns a distinct sentinel per call so we can identify items
    item_calls = []
    def mock_menu_item(*args, **kwargs):
        obj = MagicMock()
        obj._args = args
        obj._kwargs = kwargs
        item_calls.append(obj)
        return obj

    mock_pystray.MenuItem.side_effect = mock_menu_item
    mock_pystray.Menu.SEPARATOR = "SEPARATOR"

    # Capture Menu() construction
    menu_args = []
    def mock_menu(*args, **kwargs):
        menu_args.extend(args)
        return MagicMock()

    mock_pystray.Menu.side_effect = mock_menu

    # PIL image mock
    mock_image.new.return_value = MagicMock()
    mock_draw.Draw.return_value = MagicMock()

    env_patch = {}
    if env_server_url is not None:
        env_patch["CAMPAIGN_SERVER_URL"] = env_server_url

    with patch.dict("os.environ", env_patch, clear=False):
        tray_mod._pystray = mock_pystray
        tray_mod._Image = mock_image
        tray_mod._ImageDraw = mock_draw
        tray_mod._tray_icon = None
        tray_mod._tray_thread = None

        # Patch Icon.run so the thread returns immediately
        mock_pystray.Icon.return_value.run = MagicMock(return_value=None)

        tray_mod.start_tray(port=port)

    return menu_args, item_calls


# ── Tray menu tests ────────────────────────────────────────────────────────────

class TestTrayMenu:
    def test_menu_has_correct_item_count(self):
        """Menu: 4 nav items + status + pause + quit = 7 items, plus 2 separators = 9 total."""
        menu_args, item_calls = _build_tray_menu()
        # 7 non-separator items: Open Dashboard, Review Drafts, Connect Platforms, API Keys,
        # Agent status (disabled), Pause/Resume, Quit
        non_sep = [a for a in menu_args if a != "SEPARATOR"]
        assert len(non_sep) == 7, f"Expected 7 non-separator items, got {len(non_sep)}"
        separators = [a for a in menu_args if a == "SEPARATOR"]
        assert len(separators) == 2

    def test_open_dashboard_opens_hosted_url(self):
        """'Open Dashboard' callback must open the HOSTED URL, not localhost."""
        import utils.tray as tray_mod

        mock_pystray = MagicMock()
        mock_image = MagicMock()
        mock_draw = MagicMock()

        captured_callbacks = {}

        def mock_menu_item(*args, **kwargs):
            obj = MagicMock()
            obj._args = args
            obj._kwargs = kwargs
            if args and isinstance(args[0], str):
                captured_callbacks[args[0]] = args[1] if len(args) > 1 else None
            return obj

        mock_pystray.MenuItem.side_effect = mock_menu_item
        mock_pystray.Menu.SEPARATOR = "SEPARATOR"
        mock_pystray.Menu.side_effect = lambda *a, **k: MagicMock()
        mock_image.new.return_value = MagicMock()
        mock_draw.Draw.return_value = MagicMock()
        mock_pystray.Icon.return_value.run = MagicMock(return_value=None)

        tray_mod._pystray = mock_pystray
        tray_mod._Image = mock_image
        tray_mod._ImageDraw = mock_draw
        tray_mod._tray_icon = None

        with patch.dict("os.environ", {"CAMPAIGN_SERVER_URL": "https://api.pointcapitalis.com"}, clear=False):
            tray_mod.start_tray(port=5222)

        assert "Open Dashboard" in captured_callbacks
        cb = captured_callbacks["Open Dashboard"]

        opened_urls = []
        with patch("webbrowser.open", side_effect=lambda u: opened_urls.append(u)):
            # Invoke callback directly (bypasses thread for test)
            cb(None, None)
            # Give daemon thread a moment
            import time; time.sleep(0.05)

        assert any("api.pointcapitalis.com/user/" in u for u in opened_urls), \
            f"Expected hosted URL, got: {opened_urls}"

    def test_review_drafts_opens_local_drafts(self):
        """'Review Drafts' callback must open localhost:5222/drafts."""
        import utils.tray as tray_mod

        mock_pystray = MagicMock()
        mock_image = MagicMock()
        mock_draw = MagicMock()

        captured_callbacks = {}
        def mock_menu_item(*args, **kwargs):
            obj = MagicMock()
            if args and isinstance(args[0], str):
                captured_callbacks[args[0]] = args[1] if len(args) > 1 else None
            return obj

        mock_pystray.MenuItem.side_effect = mock_menu_item
        mock_pystray.Menu.SEPARATOR = "SEPARATOR"
        mock_pystray.Menu.side_effect = lambda *a, **k: MagicMock()
        mock_image.new.return_value = MagicMock()
        mock_draw.Draw.return_value = MagicMock()
        mock_pystray.Icon.return_value.run = MagicMock(return_value=None)

        tray_mod._pystray = mock_pystray
        tray_mod._Image = mock_image
        tray_mod._ImageDraw = mock_draw
        tray_mod._tray_icon = None

        tray_mod.start_tray(port=5222)

        cb = captured_callbacks.get("Review Drafts")
        assert cb is not None, "Missing 'Review Drafts' menu item"

        opened_urls = []
        with patch("webbrowser.open", side_effect=lambda u: opened_urls.append(u)):
            cb(None, None)
            import time; time.sleep(0.05)

        assert any("localhost:5222/drafts" in u for u in opened_urls), \
            f"Expected /drafts URL, got: {opened_urls}"

    def test_connect_platforms_opens_local_connect(self):
        """'Connect Platforms' callback must open localhost:5222/connect."""
        import utils.tray as tray_mod

        mock_pystray = MagicMock()
        mock_image = MagicMock()
        mock_draw = MagicMock()

        captured_callbacks = {}
        def mock_menu_item(*args, **kwargs):
            obj = MagicMock()
            if args and isinstance(args[0], str):
                captured_callbacks[args[0]] = args[1] if len(args) > 1 else None
            return obj

        mock_pystray.MenuItem.side_effect = mock_menu_item
        mock_pystray.Menu.SEPARATOR = "SEPARATOR"
        mock_pystray.Menu.side_effect = lambda *a, **k: MagicMock()
        mock_image.new.return_value = MagicMock()
        mock_draw.Draw.return_value = MagicMock()
        mock_pystray.Icon.return_value.run = MagicMock(return_value=None)

        tray_mod._pystray = mock_pystray
        tray_mod._Image = mock_image
        tray_mod._ImageDraw = mock_draw
        tray_mod._tray_icon = None

        tray_mod.start_tray(port=5222)

        cb = captured_callbacks.get("Connect Platforms")
        assert cb is not None, "Missing 'Connect Platforms' menu item"

        opened_urls = []
        with patch("webbrowser.open", side_effect=lambda u: opened_urls.append(u)):
            cb(None, None)
            import time; time.sleep(0.05)

        assert any("localhost:5222/connect" in u for u in opened_urls), \
            f"Expected /connect URL, got: {opened_urls}"

    def test_api_keys_opens_local_keys(self):
        """'API Keys' callback must open localhost:5222/keys."""
        import utils.tray as tray_mod

        mock_pystray = MagicMock()
        mock_image = MagicMock()
        mock_draw = MagicMock()

        captured_callbacks = {}
        def mock_menu_item(*args, **kwargs):
            obj = MagicMock()
            if args and isinstance(args[0], str):
                captured_callbacks[args[0]] = args[1] if len(args) > 1 else None
            return obj

        mock_pystray.MenuItem.side_effect = mock_menu_item
        mock_pystray.Menu.SEPARATOR = "SEPARATOR"
        mock_pystray.Menu.side_effect = lambda *a, **k: MagicMock()
        mock_image.new.return_value = MagicMock()
        mock_draw.Draw.return_value = MagicMock()
        mock_pystray.Icon.return_value.run = MagicMock(return_value=None)

        tray_mod._pystray = mock_pystray
        tray_mod._Image = mock_image
        tray_mod._ImageDraw = mock_draw
        tray_mod._tray_icon = None

        tray_mod.start_tray(port=5222)

        cb = captured_callbacks.get("API Keys")
        assert cb is not None, "Missing 'API Keys' menu item"

        opened_urls = []
        with patch("webbrowser.open", side_effect=lambda u: opened_urls.append(u)):
            cb(None, None)
            import time; time.sleep(0.05)

        assert any("localhost:5222/keys" in u for u in opened_urls), \
            f"Expected /keys URL, got: {opened_urls}"


# ── 401 handler tests ──────────────────────────────────────────────────────────

class Test401Handler:
    """Tests for _request_with_retry 401 handling in server_client."""

    def _make_response(self, status_code: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_2xx_returns_response(self):
        """2xx response is returned without clearing JWT or notifying."""
        import utils.server_client as sc

        mock_resp = self._make_response(200)

        with patch("utils.server_client._get_headers", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("utils.local_db.clear_jwt") as mock_clear, \
             patch("utils.tray.send_notification") as mock_notify:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = sc._request_with_retry("GET", "/api/health")

        assert result.status_code == 200
        mock_clear.assert_not_called()
        mock_notify.assert_not_called()

    def test_5xx_retries_and_raises_on_connect_error(self):
        """ConnectError triggers retries up to max_retries, then raises."""
        import utils.server_client as sc
        import httpx

        with patch("utils.server_client._get_headers", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("time.sleep"):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                sc._request_with_retry("GET", "/api/health", max_retries=3)

        assert mock_client.request.call_count == 3

    def test_401_clears_jwt_notifies_and_raises(self):
        """401 response → clear_jwt() + send_notification + raises RuntimeError immediately."""
        import utils.server_client as sc

        mock_resp = self._make_response(401)

        with patch("utils.server_client._get_headers", return_value={}), \
             patch("httpx.Client") as mock_client_cls, \
             patch("utils.local_db.clear_jwt") as mock_clear, \
             patch("utils.tray.send_notification") as mock_notify:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="Auth token expired"):
                sc._request_with_retry("GET", "/api/campaigns", max_retries=3)

        # Must have been called exactly once — no retries on 401
        assert mock_client.request.call_count == 1
        mock_clear.assert_called_once()
        mock_notify.assert_called_once()
        # Notification must reference re-auth
        args = mock_notify.call_args
        assert "amplifier.app/login" in str(args)
