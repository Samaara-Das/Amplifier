"""Auto-update checker for Amplifier.

Checks GitHub Releases for newer versions once at startup and every 24 hours.
Downloads the platform-specific installer to a temp file, stores the path in a
sentinel file, and launches the installer on the next app quit.

All errors are caught and logged — this module must never raise to its caller.
Uses only stdlib (urllib.request) for HTTP so no extra deps are needed.
"""

import json
import logging
import os
import platform
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("auto_update")

GITHUB_API_URL = "https://api.github.com/repos/Samaara-Das/Amplifier/releases/latest"
SENTINEL_PATH = Path.home() / ".amplifier" / "pending_update.txt"

# Timeout for GitHub API + download requests (seconds)
_HTTP_TIMEOUT = 20


def get_local_version() -> str:
    """Read the local app version from pyproject.toml [tool.amplifier].version."""
    try:
        # When running from source, pyproject.toml is two dirs up from this file
        # (scripts/utils/auto_update.py -> repo_root/pyproject.toml)
        repo_root = Path(__file__).resolve().parent.parent.parent
        pyproject_path = repo_root / "pyproject.toml"
        if not pyproject_path.exists():
            logger.debug("pyproject.toml not found at %s", pyproject_path)
            return "0.0.0"

        content = pyproject_path.read_text(encoding="utf-8")
        # Simple line-by-line parse to avoid needing tomllib on Python < 3.11
        in_amplifier_section = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[tool.amplifier]":
                in_amplifier_section = True
                continue
            if in_amplifier_section:
                if stripped.startswith("["):
                    # Entered a new section — stop looking
                    break
                if stripped.startswith("version"):
                    # e.g.  version = "0.1.0"
                    _, _, raw_val = stripped.partition("=")
                    version = raw_val.strip().strip('"').strip("'")
                    logger.debug("Local version: %s", version)
                    return version

        logger.debug("version key not found in [tool.amplifier]")
        return "0.0.0"
    except Exception as exc:
        logger.warning("get_local_version failed: %s", exc)
        return "0.0.0"


def get_latest_release() -> Optional[dict]:
    """Fetch the latest GitHub release metadata.

    Returns parsed JSON dict or None on any network / rate-limit failure.
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Amplifier-auto-updater/1",
            },
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning("GitHub API returned status %s", resp.status)
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as exc:
        logger.warning("get_latest_release failed (will retry in 24h): %s", exc)
        return None


def is_newer(latest: str, local: str) -> bool:
    """Return True if latest version is strictly newer than local version.

    Strips leading 'v' from both strings and compares as integer tuples.
    Handles any parse error by returning False (don't update on bad data).
    """
    try:
        def _parse(v: str):
            return tuple(int(x) for x in v.lstrip("v").split("."))

        return _parse(latest) > _parse(local)
    except Exception as exc:
        logger.warning("is_newer parse error (%r vs %r): %s", latest, local, exc)
        return False


def download_installer(release: dict, platform_name: str) -> Optional[Path]:
    """Find and download the platform-specific installer asset.

    Args:
        release: GitHub release dict (from get_latest_release).
        platform_name: "Windows" or "Darwin".

    Returns:
        Path to the downloaded temp file, or None on failure.
    """
    try:
        assets = release.get("assets", [])
        if not assets:
            logger.info("Release has no assets — nothing to download")
            return None

        # Pick asset by name pattern
        if platform_name == "Windows":
            pattern = ".exe"
            prefix = "AmplifierSetup-"
        else:
            pattern = ".pkg"
            prefix = "Amplifier-"

        chosen = None
        for asset in assets:
            name = asset.get("name", "")
            if name.startswith(prefix) and name.endswith(pattern):
                chosen = asset
                break

        if not chosen:
            logger.info(
                "No matching installer asset for platform=%s in release %s",
                platform_name, release.get("tag_name"),
            )
            return None

        download_url = chosen["browser_download_url"]
        asset_name = chosen["name"]
        logger.info("Downloading installer: %s (%s bytes)", asset_name, chosen.get("size"))

        # Download to a named temp file (don't auto-delete on close)
        suffix = ".exe" if platform_name == "Windows" else ".pkg"
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix,
            prefix="amplifier_update_",
            delete=False,
        )
        tmp_path = Path(tmp.name)
        tmp.close()

        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Amplifier-auto-updater/1"},
        )
        with urllib.request.urlopen(req, timeout=None) as resp, open(tmp_path, "wb") as fh:
            # Stream in 1 MB chunks to avoid loading entire installer into memory
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)

        logger.info("Installer downloaded to %s", tmp_path)
        return tmp_path

    except Exception as exc:
        logger.warning("download_installer failed: %s", exc)
        return None


def check_and_notify() -> None:
    """Full update check orchestration — safe to call from any thread.

    Steps:
      1. Get local version from pyproject.toml.
      2. Fetch latest release from GitHub.
      3. If newer, download installer.
      4. Write sentinel file so the quit handler can launch the installer.
      5. Send tray notification.

    All errors are caught — this function never raises.
    """
    try:
        local = get_local_version()
        release = get_latest_release()

        if release is None:
            logger.debug("No release data — skipping update check")
            return

        latest_tag = release.get("tag_name", "")
        if not latest_tag:
            logger.debug("Release has no tag_name — skipping")
            return

        if not is_newer(latest_tag, local):
            logger.info(
                "Already up-to-date (local=%s, latest=%s)", local, latest_tag
            )
            return

        logger.info("New version available: %s (running %s)", latest_tag, local)

        system = platform.system()  # "Windows" or "Darwin"
        installer_path = download_installer(release, system)
        if installer_path is None:
            # No asset yet or download failed — will retry next cycle
            return

        # Write sentinel so the quit handler / next startup can run the installer
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.write_text(str(installer_path), encoding="utf-8")
        logger.info("Pending update stored at sentinel: %s", SENTINEL_PATH)

        # Tray notification
        try:
            from utils import tray as _tray
            _tray.send_notification(
                "Amplifier Update Available",
                f"Version {latest_tag} is ready. Restart Amplifier to install.",
            )
        except Exception as notif_exc:
            logger.debug("Tray notification failed (non-fatal): %s", notif_exc)

    except Exception as exc:
        logger.error("check_and_notify unexpected error: %s", exc)


def apply_pending_update() -> None:
    """Called on app quit — launches the downloaded installer and exits.

    Windows: runs installer with /SILENT flag.
    macOS:   runs `installer -pkg <path> -target /`.

    All errors are caught — if the installer can't be launched, logs and returns
    without crashing the quit path.
    """
    try:
        if not SENTINEL_PATH.exists():
            return

        installer_path = Path(SENTINEL_PATH.read_text(encoding="utf-8").strip())
        if not installer_path.exists():
            logger.warning(
                "Sentinel points to missing installer: %s — removing sentinel",
                installer_path,
            )
            SENTINEL_PATH.unlink(missing_ok=True)
            return

        logger.info("Applying pending update from %s", installer_path)

        import subprocess
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(
                [str(installer_path), "/SILENT"],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        elif system == "Darwin":
            subprocess.Popen(["installer", "-pkg", str(installer_path), "-target", "/"])
        else:
            logger.warning("apply_pending_update: unsupported platform %s", system)
            return

        # Remove sentinel — installer takes over from here
        SENTINEL_PATH.unlink(missing_ok=True)

        # Give the installer process a moment to start, then exit
        import time
        time.sleep(1)
        sys.exit(0)

    except Exception as exc:
        logger.error("apply_pending_update failed: %s", exc)
