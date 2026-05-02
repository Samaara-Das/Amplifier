"""Server communication layer — handles auth, campaign polling, metric/post reporting."""

import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime, timezone

import httpx

from utils.crypto import decrypt_safe, encrypt_if_needed

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / "config"
AUTH_FILE = CONFIG_DIR / "server_auth.json"


def _get_server_url() -> str:
    return os.getenv("CAMPAIGN_SERVER_URL", "http://127.0.0.1:8000")


def _load_auth() -> dict:
    if AUTH_FILE.exists():
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Decrypt the token (returns as-is if already plaintext for migration)
        if "access_token" in data and data["access_token"]:
            data["access_token"] = decrypt_safe(data["access_token"])
        return data
    return {}


def _save_auth(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Encrypt the token before saving to disk
    save_data = dict(data)
    if "access_token" in save_data and save_data["access_token"]:
        save_data["access_token"] = encrypt_if_needed(save_data["access_token"])
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2)


def _get_headers() -> dict:
    auth = _load_auth()
    token = auth.get("access_token")
    if not token:
        raise RuntimeError("Not logged in. Run onboarding first.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _request_with_retry(method: str, path: str, max_retries: int = 3, **kwargs) -> httpx.Response:
    """Make HTTP request with exponential backoff retry."""
    url = f"{_get_server_url()}{path}"
    headers = kwargs.pop("headers", _get_headers())

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.request(method, url, headers=headers, **kwargs)
                if resp.status_code == 401:
                    logger.error("Auth token expired or invalid. Re-login needed.")
                    # Clear stored credentials so next startup forces re-auth
                    try:
                        from utils.local_db import clear_jwt
                        clear_jwt()
                    except Exception:
                        pass
                    # Send desktop notification if tray is available
                    try:
                        from utils.tray import send_notification
                        send_notification(
                            "Amplifier",
                            "Re-authenticate at amplifier.app/login",
                        )
                    except Exception:
                        pass
                    raise RuntimeError("Auth token expired. Run onboarding to re-login.")
                return resp
        except httpx.ConnectError:
            wait = 2 ** attempt * 5
            logger.warning("Server unreachable (attempt %d/%d). Retrying in %ds...",
                           attempt + 1, max_retries, wait)
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise
        except httpx.TimeoutException:
            wait = 2 ** attempt * 5
            logger.warning("Request timeout (attempt %d/%d). Retrying in %ds...",
                           attempt + 1, max_retries, wait)
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise


# ── Auth ───────────────────────────────────────────────────────────


def register(email: str, password: str) -> dict:
    """Register a new user account."""
    url = f"{_get_server_url()}/api/auth/register"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Registration failed: {resp.json().get('detail', resp.text)}")
    data = resp.json()
    _save_auth({"access_token": data["access_token"], "email": email})
    logger.info("Registered and logged in as %s", email)
    return data


def login(email: str, password: str) -> dict:
    """Log in to existing account."""
    url = f"{_get_server_url()}/api/auth/login"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.json().get('detail', resp.text)}")
    data = resp.json()
    _save_auth({"access_token": data["access_token"], "email": email})
    logger.info("Logged in as %s", email)
    return data


def reset_password(email: str, current_password: str, new_password: str) -> dict:
    """Reset password using current password as verification."""
    url = f"{_get_server_url()}/api/auth/reset-password"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json={
            "email": email,
            "current_password": current_password,
            "new_password": new_password,
        })
    if resp.status_code != 200:
        raise RuntimeError(f"Password reset failed: {resp.json().get('detail', resp.text)}")
    data = resp.json()
    _save_auth({"access_token": data["access_token"], "email": email})
    logger.info("Password reset for %s", email)
    return data


def is_logged_in() -> bool:
    auth = _load_auth()
    return bool(auth.get("access_token"))


# ── Profile ────────────────────────────────────────────────────────


def get_profile() -> dict:
    resp = _request_with_retry("GET", "/api/users/me")
    resp.raise_for_status()
    return resp.json()


def update_profile(platforms: dict = None, follower_counts: dict = None,
                   niche_tags: list = None, audience_region: str = None,
                   mode: str = None, scraped_profiles: dict = None,
                   ai_detected_niches: list = None) -> dict:
    payload = {}
    if platforms is not None:
        payload["platforms"] = platforms
    if follower_counts is not None:
        payload["follower_counts"] = follower_counts
    if niche_tags is not None:
        payload["niche_tags"] = niche_tags
    if audience_region is not None:
        payload["audience_region"] = audience_region
    if mode is not None:
        payload["mode"] = mode
    if scraped_profiles is not None:
        payload["scraped_profiles"] = scraped_profiles
    if ai_detected_niches is not None:
        payload["ai_detected_niches"] = ai_detected_niches

    resp = _request_with_retry("PATCH", "/api/users/me", json=payload)
    resp.raise_for_status()
    return resp.json()


# ── Campaigns ──────────────────────────────────────────────────────


def get_invitations() -> list[dict]:
    """Get pending campaign invitations for this user."""
    resp = _request_with_retry("GET", "/api/campaigns/invitations")
    if resp.status_code == 200:
        return resp.json()
    logger.warning("Failed to get invitations: %s", resp.status_code)
    return []


def accept_invitation(assignment_id: int) -> dict:
    """Accept a campaign invitation."""
    resp = _request_with_retry("POST", f"/api/campaigns/invitations/{assignment_id}/accept")
    resp.raise_for_status()
    return resp.json()


def reject_invitation(assignment_id: int, reason: str = None) -> dict:
    """Reject a campaign invitation with optional decline reason."""
    body = {"reason": reason} if reason else None
    resp = _request_with_retry("POST", f"/api/campaigns/invitations/{assignment_id}/reject", json=body)
    resp.raise_for_status()
    return resp.json()


def get_active_campaigns() -> list[dict]:
    """Get user's active (accepted) campaigns."""
    resp = _request_with_retry("GET", "/api/campaigns/active")
    if resp.status_code == 200:
        return resp.json()
    logger.warning("Failed to get active campaigns: %s", resp.status_code)
    return []


def poll_campaigns() -> list[dict]:
    """Poll server for campaigns matched to this user."""
    resp = _request_with_retry("GET", "/api/campaigns/mine")
    if resp.status_code == 200:
        campaigns = resp.json()
        logger.info("Polled server: %d campaign(s) available", len(campaigns))
        return campaigns
    logger.warning("Campaign poll failed: %s", resp.text)
    return []


def update_assignment(assignment_id: int, status: str, content_mode: str = None) -> dict:
    """Update campaign assignment status."""
    params = {"status": status}
    if content_mode:
        params["content_mode"] = content_mode
    resp = _request_with_retry("PATCH", f"/api/campaigns/assignments/{assignment_id}",
                               params=params)
    resp.raise_for_status()
    return resp.json()


# ── Posts ──────────────────────────────────────────────────────────


def report_posts(posts: list[dict]) -> dict:
    """Report posted content URLs to server.

    Each post: {assignment_id, platform, post_url, content_hash, posted_at}
    """
    resp = _request_with_retry("POST", "/api/posts", json={"posts": posts})
    resp.raise_for_status()
    result = resp.json()
    logger.info("Reported %d post(s) to server", result.get("count", 0))
    return result


# ── Metrics ────────────────────────────────────────────────────────


def report_metrics(metrics: list[dict]) -> dict:
    """Batch submit scraped metrics to server.

    Each metric: {post_id, impressions, likes, reposts, comments, clicks, scraped_at, is_final}
    """
    resp = _request_with_retry("POST", "/api/metrics", json={"metrics": metrics})
    resp.raise_for_status()
    result = resp.json()
    logger.info("Reported %d metric(s) to server", result.get("accepted", 0))
    return result


def report_post_deleted(server_post_id: int) -> dict:
    """Notify the server that a post has been deleted. Triggers earning voiding."""
    resp = _request_with_retry(
        "PATCH", f"/api/posts/{server_post_id}/status",
        json={"status": "deleted"},
    )
    resp.raise_for_status()
    result = resp.json()
    logger.info("Reported post %d as deleted to server (voided: %s)",
                server_post_id, result.get("earnings_voided", 0))
    return result


# ── Earnings ───────────────────────────────────────────────────────


def get_earnings() -> dict:
    resp = _request_with_retry("GET", "/api/users/me/earnings")
    resp.raise_for_status()
    return resp.json()


def request_payout(amount: float) -> dict:
    """Request a payout withdrawal from the user's earnings balance."""
    resp = _request_with_retry("POST", "/api/users/me/payout", json={"amount": amount})
    resp.raise_for_status()
    return resp.json()


# ── Agent Commands ─────────────────────────────────────────────────


def get_pending_commands() -> list[dict]:
    """GET /api/agent/commands?status=pending. Returns list of pending commands for current user."""
    resp = _request_with_retry("GET", "/api/agent/commands", params={"status": "pending"})
    if resp.status_code == 200:
        return resp.json()
    logger.warning("Failed to get pending commands: %s", resp.status_code)
    return []


def post_agent_command(command_type: str, payload: dict) -> dict:
    """POST /api/agent/commands. Insert a command for the current user (authenticated via JWT).

    Used by local_server.py to queue scrape_profiles after platform connect.
    The server's POST /api/agent/commands endpoint uses the user's JWT to set user_id.
    """
    resp = _request_with_retry(
        "POST", "/api/agent/commands", json={"type": command_type, "payload": payload}
    )
    resp.raise_for_status()
    return resp.json()


def ack_command(command_id: int, result: str = "done", error: str | None = None) -> dict:
    """POST /api/agent/commands/{id}/ack. result: 'done' | 'failed'."""
    body: dict = {"result": result}
    if error is not None:
        body["error"] = error
    resp = _request_with_retry("POST", f"/api/agent/commands/{command_id}/ack", json=body)
    resp.raise_for_status()
    return resp.json()


def push_agent_status(running: bool, paused: bool, platform_health: dict,
                      ai_keys_configured: dict, version: str | None = None) -> dict:
    """POST /api/agent/status. Daemon pushes own status. Returns the upserted row."""
    body: dict = {
        "running": running,
        "paused": paused,
        "platform_health": platform_health,
        "ai_keys_configured": ai_keys_configured,
    }
    if version is not None:
        body["version"] = version
    resp = _request_with_retry("POST", "/api/agent/status", json=body)
    resp.raise_for_status()
    return resp.json()


# ── Drafts ─────────────────────────────────────────────────────────


def upload_draft(*, campaign_id: int, platform: str, text: str,
                 image_url: str | None = None, image_local_path: str | None = None,
                 quality_score: int | None = None, iteration: int = 1,
                 local_id: int | None = None) -> dict:
    """POST /api/drafts. Idempotent for the same (user_id, campaign_id, platform, local_id) tuple."""
    body: dict = {
        "campaign_id": campaign_id,
        "platform": platform,
        "text": text,
        "iteration": iteration,
    }
    if image_url is not None:
        body["image_url"] = image_url
    if image_local_path is not None:
        body["image_local_path"] = image_local_path
    if quality_score is not None:
        body["quality_score"] = quality_score
    if local_id is not None:
        body["local_id"] = local_id
    resp = _request_with_retry("POST", "/api/drafts", json=body)
    resp.raise_for_status()
    return resp.json()


def upload_draft_image(image_path: str) -> dict:
    """POST /api/drafts/upload-image (multipart). Returns {'url': ...}."""
    url = f"{_get_server_url()}/api/drafts/upload-image"
    # Auth only — no Content-Type header (httpx sets multipart boundary automatically)
    auth = _load_auth()
    token = auth.get("access_token")
    if not token:
        raise RuntimeError("Not logged in. Run onboarding first.")
    headers = {"Authorization": f"Bearer {token}"}
    with open(image_path, "rb") as fh:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, files={"file": fh})
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Image upload failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def update_draft_status_remote(draft_id: int, status: str | None = None,
                               text: str | None = None, image_url: str | None = None) -> dict:
    """PATCH /api/drafts/{id}. Used when local user approves/edits a draft."""
    body: dict = {}
    if status is not None:
        body["status"] = status
    if text is not None:
        body["text"] = text
    if image_url is not None:
        body["image_url"] = image_url
    resp = _request_with_retry("PATCH", f"/api/drafts/{draft_id}", json=body)
    resp.raise_for_status()
    return resp.json()
