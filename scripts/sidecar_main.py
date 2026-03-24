"""
Amplifier Python Sidecar — JSON-RPC over stdin/stdout.

Spawned by the Tauri Rust backend. Reads JSON-RPC requests from stdin,
dispatches to handler functions, writes JSON-RPC responses to stdout.

Protocol:
  Rust -> Python (stdin):  {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}
  Python -> Rust (stdout): {"jsonrpc": "2.0", "result": {"status": "pong"}, "id": 1}
  Python -> Rust (stdout): {"jsonrpc": "2.0", "method": "event", "params": {...}}  (unsolicited)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path

# ── Setup paths ─────────────────────────────────────

def setup_paths(project_root: str):
    """Add project root and scripts/ to sys.path so we can import existing modules."""
    root = Path(project_root).resolve()
    paths_to_add = [
        str(root),
        str(root / "scripts"),
    ]
    for p in paths_to_add:
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(str(root))
    return root


# ── Logging (stderr only — stdout is for JSON-RPC) ─

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,  # IMPORTANT: logs go to stderr, not stdout
)
logger = logging.getLogger("sidecar")


# ── JSON-RPC helpers ────────────────────────────────

def send_response(result, request_id):
    """Send a JSON-RPC success response."""
    response = {
        "jsonrpc": "2.0",
        "result": result,
        "id": request_id,
    }
    line = json.dumps(response, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def send_error(code, message, request_id, data=None):
    """Send a JSON-RPC error response."""
    error_obj = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    response = {
        "jsonrpc": "2.0",
        "error": error_obj,
        "id": request_id,
    }
    line = json.dumps(response, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def send_event(event_type, payload):
    """Send an unsolicited event notification to Rust."""
    notification = {
        "jsonrpc": "2.0",
        "method": "event",
        "params": {"type": event_type, **payload},
    }
    line = json.dumps(notification, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ── Handler functions ───────────────────────────────

def handle_ping(params):
    """Health check."""
    return {"status": "pong"}


def handle_shutdown(params):
    """Graceful shutdown."""
    logger.info("Shutdown requested. Cleaning up...")
    # TODO: Close any open Playwright browsers
    return {"status": "shutting_down"}


def handle_get_status(params):
    """Get overall app status — active campaigns, earnings, platform health, recent activity."""
    try:
        from utils.local_db import init_db, _get_db
        from utils.server_client import is_logged_in

        init_db()
        conn = _get_db()

        # Count active campaigns (accepted, content_generated, posted)
        active = conn.execute(
            "SELECT COUNT(*) FROM local_campaign WHERE status IN ('assigned', 'active', 'in_progress', 'accepted', 'content_generated', 'posted')"
        ).fetchone()[0]

        # Count pending invitations (not expired)
        pending = conn.execute(
            "SELECT COUNT(*) FROM local_campaign WHERE invitation_status = 'pending_invitation' AND (expires_at IS NULL OR expires_at > datetime('now'))"
        ).fetchone()[0]

        # Count queued posts from post_schedule table
        queued = conn.execute(
            "SELECT COUNT(*) FROM post_schedule WHERE status = 'queued'"
        ).fetchone()[0]

        # Get earnings balance (available for withdrawal)
        earnings_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM local_earning WHERE status = 'available'"
        ).fetchone()
        earnings = earnings_row[0] if earnings_row else 0.0

        # Get recent activity (last 10 events)
        recent_activity = _get_recent_activity(conn)

        logged_in = False
        try:
            logged_in = is_logged_in()
        except Exception:
            pass

        # Check onboarding completion
        onboarding_done = True  # default to True for existing users
        email = ""
        try:
            ob_val = conn.execute(
                "SELECT value FROM settings WHERE key = 'onboarding_done'"
            ).fetchone()
            if ob_val:
                onboarding_done = ob_val[0].lower() in ("true", "1", "yes")
            elif logged_in:
                # Logged in but no onboarding_done flag → assume not done
                onboarding_done = False
            else:
                onboarding_done = False
        except Exception:
            pass

        conn.close()

        try:
            from utils.server_client import _load_auth
            auth = _load_auth()
            email = auth.get("email", "") if auth else ""
        except Exception:
            pass

        return {
            "logged_in": logged_in,
            "onboarding_done": onboarding_done,
            "email": email,
            "active_campaigns": active,
            "pending_invitations": pending,
            "posts_queued": queued,
            "earnings_balance": round(earnings, 2),
            "platforms": _get_platform_health(),
            "recent_activity": recent_activity,
        }
    except Exception as e:
        logger.error("get_status failed: %s", e)
        return {
            "logged_in": False,
            "onboarding_done": False,
            "email": "",
            "active_campaigns": 0,
            "pending_invitations": 0,
            "posts_queued": 0,
            "earnings_balance": 0.0,
            "platforms": {},
            "recent_activity": [],
        }


def _get_platform_health():
    """Check which platform profiles exist and have content (basic health check).

    Returns dict with 'connected' bool and 'health' color per platform.
    Green = profile directory exists and has files.
    Red = no profile directory or empty.
    """
    health = {}
    profiles_dir = Path("profiles")
    platforms = {
        "x": "x-profile",
        "linkedin": "linkedin-profile",
        "facebook": "facebook-profile",
        "reddit": "reddit-profile",
    }
    for platform, profile_dir in platforms.items():
        full_path = profiles_dir / profile_dir
        if full_path.exists() and any(full_path.iterdir()):
            health[platform] = {"connected": True, "health": "green"}
        else:
            health[platform] = {"connected": False, "health": "red"}
    return health


def _get_recent_activity(conn, limit=10):
    """Build a recent activity feed from local database tables.

    Merges events from campaigns, posts, and earnings, sorted by time descending.
    """
    events = []

    # Campaign events (accepted/rejected)
    try:
        campaign_rows = conn.execute("""
            SELECT title, invitation_status, responded_at, updated_at
            FROM local_campaign
            WHERE invitation_status IN ('accepted', 'rejected')
            ORDER BY COALESCE(responded_at, updated_at) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        for row in campaign_rows:
            status = row["invitation_status"]
            title = row["title"] or "Untitled Campaign"
            # Truncate long titles
            if len(title) > 40:
                title = title[:37] + "..."
            event_type = "campaign_accepted" if status == "accepted" else "campaign_rejected"
            desc = f"{'Accepted' if status == 'accepted' else 'Rejected'} '{title}'"
            ts = row["responded_at"] or row["updated_at"]
            events.append({"type": event_type, "description": desc, "timestamp": ts})
    except Exception as e:
        logger.debug("Error fetching campaign events: %s", e)

    # Post events (published)
    try:
        post_rows = conn.execute("""
            SELECT p.platform, p.posted_at, c.title as campaign_title
            FROM local_post p
            LEFT JOIN local_campaign c ON p.campaign_server_id = c.server_id
            WHERE p.posted_at IS NOT NULL
            ORDER BY p.posted_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        platform_display = {
            "x": "X", "linkedin": "LinkedIn", "facebook": "Facebook",
            "reddit": "Reddit", "tiktok": "TikTok", "instagram": "Instagram",
        }
        for row in post_rows:
            platform = platform_display.get(row["platform"], row["platform"])
            campaign_title = row["campaign_title"] or ""
            if campaign_title:
                if len(campaign_title) > 30:
                    campaign_title = campaign_title[:27] + "..."
                desc = f"Posted to {platform} for '{campaign_title}'"
            else:
                desc = f"Posted to {platform}"
            events.append({"type": "post_published", "description": desc, "timestamp": row["posted_at"]})
    except Exception as e:
        logger.debug("Error fetching post events: %s", e)

    # Earnings events
    try:
        earning_rows = conn.execute("""
            SELECT e.amount, e.status, e.updated_at, c.title as campaign_title
            FROM local_earning e
            LEFT JOIN local_campaign c ON e.campaign_server_id = c.server_id
            ORDER BY e.updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        for row in earning_rows:
            amount = row["amount"] or 0
            campaign_title = row["campaign_title"] or "Campaign"
            if len(campaign_title) > 30:
                campaign_title = campaign_title[:27] + "..."
            desc = f"Earned ${amount:.2f} from '{campaign_title}'"
            events.append({"type": "earning_received", "description": desc, "timestamp": row["updated_at"]})
    except Exception as e:
        logger.debug("Error fetching earning events: %s", e)

    # Sort all events by timestamp descending, return top N
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    events = events[:limit]

    # Convert timestamps to relative time strings
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for event in events:
        event["time"] = _relative_time(event.get("timestamp"), now)
        del event["timestamp"]  # Don't send raw timestamp to frontend

    return events


def _relative_time(timestamp_str, now=None):
    """Convert an ISO timestamp string to a human-readable relative time."""
    if not timestamp_str:
        return "unknown"
    from datetime import datetime, timezone, timedelta
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        # Parse the timestamp — handle both naive and aware datetimes
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        diff = now - ts
        seconds = int(diff.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days}d ago"
        weeks = days // 7
        if weeks < 4:
            return f"{weeks}w ago"
        return f"{days // 30}mo ago"
    except Exception:
        return "unknown"


def handle_poll_campaigns(params):
    """Poll the server for new campaign invitations."""
    try:
        from utils.server_client import poll_campaigns
        result = poll_campaigns()
        return {"success": True, "campaigns": result}
    except Exception as e:
        logger.error("poll_campaigns failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_get_invitations(params):
    """Get pending campaign invitations from local DB (excludes expired)."""
    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM local_campaign WHERE invitation_status = 'pending_invitation' AND (expires_at IS NULL OR expires_at > datetime('now')) ORDER BY invited_at DESC"
        ).fetchall()
        conn.close()

        invitations = [dict(row) for row in rows]
        return {"invitations": invitations}
    except Exception as e:
        logger.error("get_invitations failed: %s", e)
        return {"invitations": [], "error": str(e)}


def handle_accept_invitation(params):
    """Accept a campaign invitation."""
    invitation_id = params.get("invitation_id")
    if not invitation_id:
        raise ValueError("invitation_id is required")

    try:
        from utils.server_client import accept_invitation
        from utils.local_db import init_db, _get_db

        # Accept on server
        result = accept_invitation(invitation_id)

        # Update local DB
        init_db()
        conn = _get_db()
        conn.execute(
            "UPDATE local_campaign SET invitation_status = 'accepted', status = 'assigned' WHERE server_id = ?",
            (invitation_id,),
        )
        conn.commit()
        conn.close()

        return {"success": True, "result": result}
    except Exception as e:
        logger.error("accept_invitation failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_reject_invitation(params):
    """Reject a campaign invitation."""
    invitation_id = params.get("invitation_id")
    if not invitation_id:
        raise ValueError("invitation_id is required")

    try:
        from utils.server_client import reject_invitation
        from utils.local_db import init_db, _get_db

        # Reject on server
        result = reject_invitation(invitation_id)

        # Update local DB
        init_db()
        conn = _get_db()
        conn.execute(
            "UPDATE local_campaign SET invitation_status = 'rejected' WHERE server_id = ?",
            (invitation_id,),
        )
        conn.commit()
        conn.close()

        return {"success": True, "result": result}
    except Exception as e:
        logger.error("reject_invitation failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_get_campaigns(params):
    """Get active campaigns from local DB with per-platform status."""
    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM local_campaign WHERE status IN ('assigned', 'active', 'in_progress', 'accepted', 'content_generated', 'posted') ORDER BY created_at DESC"
        ).fetchall()

        campaigns = []
        for row in rows:
            campaign = dict(row)
            server_id = campaign.get("server_id")

            # Build per-platform statuses from drafts and post_schedule
            platform_statuses = {}
            try:
                # Check drafts (generating/review)
                drafts = conn.execute(
                    "SELECT platform, approved, posted FROM agent_draft WHERE campaign_id = ? ORDER BY id DESC",
                    (server_id,),
                ).fetchall()

                seen_platforms = set()
                for d in drafts:
                    plat = d["platform"]
                    if plat in seen_platforms:
                        continue
                    seen_platforms.add(plat)
                    if d["posted"] and d["approved"]:
                        platform_statuses[plat] = "posted"
                    elif d["approved"]:
                        platform_statuses[plat] = "approved"
                    else:
                        platform_statuses[plat] = "review"

                # Check post_schedule for scheduled/posted/failed
                schedules = conn.execute(
                    "SELECT platform, status FROM post_schedule WHERE campaign_server_id = ?",
                    (server_id,),
                ).fetchall()
                for s in schedules:
                    plat = s["platform"]
                    sched_status = s["status"]
                    if sched_status == "queued":
                        platform_statuses[plat] = "scheduled"
                    elif sched_status == "posted":
                        platform_statuses[plat] = "posted"

                # Check local_post for actual posts
                posts = conn.execute(
                    "SELECT platform FROM local_post WHERE campaign_server_id = ? AND post_url IS NOT NULL",
                    (server_id,),
                ).fetchall()
                for p in posts:
                    platform_statuses[p["platform"]] = "posted"

            except Exception as e:
                logger.debug("Error building platform statuses for campaign %s: %s", server_id, e)

            campaign["platform_statuses"] = platform_statuses
            campaigns.append(campaign)

        conn.close()
        return {"campaigns": campaigns}
    except Exception as e:
        logger.error("get_campaigns failed: %s", e)
        return {"campaigns": [], "error": str(e)}


def handle_get_completed_campaigns(params):
    """Get completed campaigns with final metrics and earnings."""
    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        rows = conn.execute("""
            SELECT
                c.*,
                COALESCE(SUM(m.impressions), 0) as total_impressions,
                COALESCE(SUM(COALESCE(m.likes, 0) + COALESCE(m.reposts, 0) + COALESCE(m.clicks, 0) + COALESCE(m.comments, 0)), 0) as total_engagement,
                COALESCE(SUM(e.amount), 0) as total_earned,
                MAX(p.posted_at) as completed_at
            FROM local_campaign c
            LEFT JOIN local_post p ON c.server_id = p.campaign_server_id
            LEFT JOIN (
                SELECT post_id, impressions, likes, reposts, clicks, comments
                FROM local_metric
                WHERE id IN (SELECT MAX(id) FROM local_metric GROUP BY post_id)
            ) m ON m.post_id = p.id
            LEFT JOIN local_earning e ON c.server_id = e.campaign_server_id
            WHERE c.status IN ('completed', 'paid', 'done')
            GROUP BY c.server_id
            ORDER BY completed_at DESC
        """).fetchall()

        conn.close()

        campaigns = [dict(row) for row in rows]
        return {"campaigns": campaigns}
    except Exception as e:
        logger.error("get_completed_campaigns failed: %s", e)
        return {"campaigns": [], "error": str(e)}


def handle_get_earnings(params):
    """Get earnings data — tries server first for full breakdown, falls back to local DB."""
    # Try server first for authoritative data with full breakdowns
    try:
        from utils.server_client import get_earnings, is_logged_in

        if is_logged_in():
            server_data = get_earnings()
            logger.info("Loaded earnings from server")
            return server_data
    except Exception as e:
        logger.warning("Server earnings fetch failed, falling back to local DB: %s", e)

    # Fallback: build earnings from local database
    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        # Total available balance
        available = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM local_earning WHERE status = 'available'"
        ).fetchone()[0]

        # Total pending
        pending = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM local_earning WHERE status = 'pending'"
        ).fetchone()[0]

        # Total earned (all time)
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM local_earning"
        ).fetchone()[0]

        # Per-campaign breakdown from local earnings + campaigns
        per_campaign = []
        try:
            campaign_rows = conn.execute("""
                SELECT
                    c.server_id as campaign_id,
                    c.title as campaign_title,
                    COUNT(DISTINCT p.id) as posts,
                    COALESCE(SUM(m.impressions), 0) as impressions,
                    COALESCE(SUM(m.likes) + SUM(m.reposts) + SUM(m.clicks), 0) as engagement,
                    COALESCE(SUM(e.amount), 0) as earned,
                    CASE
                        WHEN SUM(CASE WHEN e.status = 'paid' THEN 1 ELSE 0 END) > 0 THEN 'paid'
                        WHEN SUM(CASE WHEN e.status = 'available' THEN 1 ELSE 0 END) > 0 THEN 'calculated'
                        ELSE 'pending'
                    END as status
                FROM local_campaign c
                LEFT JOIN local_post p ON c.server_id = p.campaign_server_id
                LEFT JOIN local_metric m ON p.id = m.post_id
                LEFT JOIN local_earning e ON c.server_id = e.campaign_server_id
                WHERE e.id IS NOT NULL
                GROUP BY c.server_id
                ORDER BY earned DESC
            """).fetchall()
            per_campaign = [dict(row) for row in campaign_rows]
        except Exception as e:
            logger.debug("Error building per-campaign breakdown: %s", e)

        # Per-platform breakdown from local posts + earnings
        per_platform = {}
        try:
            platform_rows = conn.execute("""
                SELECT
                    p.platform,
                    COALESCE(SUM(e.amount), 0) as total
                FROM local_post p
                JOIN local_earning e ON p.campaign_server_id = e.campaign_server_id
                GROUP BY p.platform
                HAVING total > 0
                ORDER BY total DESC
            """).fetchall()
            per_platform = {row["platform"]: round(row["total"], 2) for row in platform_rows}
        except Exception as e:
            logger.debug("Error building per-platform breakdown: %s", e)

        # Payout history (withdrawals) — from local earnings with status 'paid'
        payout_history = []
        try:
            payout_rows = conn.execute("""
                SELECT id, amount, status, updated_at as requested_at
                FROM local_earning
                WHERE status IN ('paid', 'processing')
                ORDER BY updated_at DESC
                LIMIT 20
            """).fetchall()
            payout_history = [dict(row) for row in payout_rows]
        except Exception as e:
            logger.debug("Error building payout history: %s", e)

        conn.close()

        return {
            "total_earned": round(total, 2),
            "current_balance": round(available, 2),
            "pending": round(pending, 2),
            "per_campaign": per_campaign,
            "per_platform": per_platform,
            "payout_history": payout_history,
        }
    except Exception as e:
        logger.error("get_earnings failed: %s", e)
        return {
            "total_earned": 0.0,
            "current_balance": 0.0,
            "pending": 0.0,
            "per_campaign": [],
            "per_platform": {},
            "payout_history": [],
        }


def handle_request_payout(params):
    """Request a payout withdrawal via the server."""
    amount = params.get("amount")
    if not amount or float(amount) < 10:
        return {"success": False, "error": "Minimum withdrawal is $10.00"}

    try:
        from utils.server_client import request_payout

        result = request_payout(float(amount))
        logger.info("Payout requested: $%.2f — %s", float(amount), result.get("status"))
        return {"success": True, **result}
    except Exception as e:
        logger.error("request_payout failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_get_settings(params):
    """Get comprehensive user settings -- mode, platforms, profile, notifications, stats."""
    try:
        from utils.local_db import init_db, _get_db, get_setting, get_all_scraped_profiles
        import json as _json

        init_db()
        conn = _get_db()

        # ── Basic settings from key-value store ──
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        kv = {row["key"]: row["value"] for row in rows}
        mode = kv.get("mode", "semi_auto")

        # Notifications (stored as JSON string)
        notif_raw = kv.get("notifications")
        if notif_raw:
            try:
                notifications = _json.loads(notif_raw)
            except (_json.JSONDecodeError, TypeError):
                notifications = {"invitations": True, "failures": True, "earnings": True}
        else:
            notifications = {"invitations": True, "failures": True, "earnings": True}

        # ── Email from server auth ──
        email = ""
        try:
            from utils.server_client import _load_auth
            auth = _load_auth()
            email = auth.get("email", "") if auth else ""
        except Exception:
            email = kv.get("email", "")

        # ── Platform health + scraped profile data ──
        platforms = {}
        health_data = _get_platform_health()

        # Merge with session_health from local_db if available
        session_health_raw = kv.get("session_health")
        session_health = {}
        if session_health_raw:
            try:
                session_health = _json.loads(session_health_raw)
            except (_json.JSONDecodeError, TypeError):
                pass

        # Get scraped profile data
        scraped_profiles = {}
        try:
            profiles = get_all_scraped_profiles()
            for p in profiles:
                scraped_profiles[p["platform"]] = p
        except Exception:
            pass

        # Collect niches across all platforms
        all_niches = set()

        for platform_key in ["x", "linkedin", "facebook", "reddit"]:
            basic = health_data.get(platform_key, {"connected": False, "health": "red"})
            # Override health with session_health if available
            if platform_key in session_health:
                basic["health"] = session_health[platform_key].get("status", basic["health"])

            profile = scraped_profiles.get(platform_key, {})
            followers = profile.get("follower_count", 0)
            engagement = profile.get("engagement_rate", 0.0)

            # Parse AI niches
            ai_niches_raw = profile.get("ai_niches", "[]")
            try:
                ai_niches = _json.loads(ai_niches_raw) if isinstance(ai_niches_raw, str) else ai_niches_raw
            except (_json.JSONDecodeError, TypeError):
                ai_niches = []
            for n in ai_niches:
                all_niches.add(n)

            platforms[platform_key] = {
                "connected": basic["connected"],
                "health": basic["health"],
                "followers": followers,
                "engagement_rate": engagement,
            }

        # Last scraped timestamp (most recent across platforms)
        last_scraped = None
        for p in scraped_profiles.values():
            ts = p.get("scraped_at")
            if ts and (last_scraped is None or ts > last_scraped):
                last_scraped = ts

        # ── Trust score from server or local ──
        trust_score = None
        try:
            from utils.server_client import is_logged_in
            if is_logged_in():
                # Try to get trust score from server user stats
                try:
                    from utils.server_client import get_user_stats
                    user_stats = get_user_stats()
                    trust_score = user_stats.get("trust_score")
                except Exception:
                    pass
        except Exception:
            pass
        if trust_score is None:
            try:
                ts_raw = kv.get("trust_score")
                trust_score = int(float(ts_raw)) if ts_raw else None
            except (ValueError, TypeError):
                trust_score = None

        # ── Statistics ──
        stats = {}

        # Campaign completion
        try:
            total_campaigns = conn.execute(
                "SELECT COUNT(*) FROM local_campaign"
            ).fetchone()[0]
            completed_campaigns = conn.execute(
                "SELECT COUNT(*) FROM local_campaign WHERE status IN ('completed', 'done', 'posted')"
            ).fetchone()[0]
            stats["campaigns_completed"] = completed_campaigns
            stats["campaigns_total"] = total_campaigns
        except Exception:
            stats["campaigns_completed"] = 0
            stats["campaigns_total"] = 0

        # Best platform by engagement
        best_platform = None
        best_engagement = 0
        for pk, pdata in platforms.items():
            if pdata.get("connected") and pdata.get("engagement_rate", 0) > best_engagement:
                best_engagement = pdata["engagement_rate"]
                best_platform = pk
        stats["best_platform"] = best_platform
        stats["best_platform_engagement"] = best_engagement

        # Post success rate per platform
        post_success = {}
        try:
            for pk in ["x", "linkedin", "facebook", "reddit"]:
                total_posts = conn.execute(
                    "SELECT COUNT(*) FROM post_schedule WHERE platform = ?", (pk,)
                ).fetchone()[0]
                successful = conn.execute(
                    "SELECT COUNT(*) FROM post_schedule WHERE platform = ? AND status = 'posted'", (pk,)
                ).fetchone()[0]
                if total_posts > 0:
                    post_success[pk] = round(successful / total_posts, 2)
        except Exception:
            pass
        stats["post_success_rate"] = post_success

        # 30-day earnings for sparkline
        earnings_30d = []
        try:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            for i in range(30):
                day = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
                day_next = (now - timedelta(days=28 - i)).strftime("%Y-%m-%d")
                row = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM local_earning WHERE updated_at >= ? AND updated_at < ?",
                    (day, day_next),
                ).fetchone()
                earnings_30d.append(round(row[0], 2) if row else 0)
        except Exception:
            earnings_30d = []
        stats["earnings_30d"] = earnings_30d

        conn.close()

        return {
            "mode": mode,
            "email": email,
            "notifications": notifications,
            "platforms": platforms,
            "niches": sorted(all_niches),
            "last_scraped": last_scraped,
            "trust_score": trust_score,
            "stats": stats,
        }

    except Exception as e:
        logger.error("get_settings failed: %s", e)
        return {
            "mode": "semi_auto",
            "email": "",
            "notifications": {"invitations": True, "failures": True, "earnings": True},
            "platforms": {},
            "niches": [],
            "last_scraped": None,
            "trust_score": None,
            "stats": {},
        }


def handle_update_settings(params):
    """Update user settings in local DB."""
    settings = params.get("settings", {})
    if not settings:
        return {"success": True}  # Nothing to update

    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()
        for key, value in settings.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        conn.commit()
        conn.close()

        return {"success": True}
    except Exception as e:
        logger.error("update_settings failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_get_posts(params):
    """Get all posts grouped by status: pending_review, scheduled, posted, failed."""
    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        result = {
            "pending_review": [],
            "scheduled": [],
            "posted": [],
            "failed": [],
        }

        # ── Pending Review: drafts from agent_draft that are not approved ──
        try:
            draft_rows = conn.execute("""
                SELECT d.*, c.title as campaign_title, c.updated_at as campaign_updated_at,
                       c.status as campaign_status
                FROM agent_draft d
                LEFT JOIN local_campaign c ON d.campaign_id = c.server_id
                WHERE d.approved = 0 AND d.posted = 0
                ORDER BY d.created_at DESC
            """).fetchall()

            # Group drafts by campaign_id
            campaigns_map = {}
            for row in draft_rows:
                row_dict = dict(row)
                cid = row_dict["campaign_id"]
                if cid not in campaigns_map:
                    campaigns_map[cid] = {
                        "campaign_id": cid,
                        "campaign_title": row_dict.get("campaign_title") or "Untitled Campaign",
                        "campaign_updated": False,
                        "quality_score": 0,
                        "platforms": {},
                    }
                platform = row_dict["platform"]
                score = row_dict.get("quality_score", 0) or 0
                campaigns_map[cid]["platforms"][platform] = {
                    "text": row_dict.get("draft_text", ""),
                    "draft_id": row_dict["id"],
                }
                # Use max quality score across platforms
                if score > campaigns_map[cid]["quality_score"]:
                    campaigns_map[cid]["quality_score"] = int(score)

            result["pending_review"] = list(campaigns_map.values())
        except Exception as e:
            logger.debug("Error fetching pending review drafts: %s", e)

        # ── Scheduled: posts in post_schedule with status='queued' ──
        try:
            sched_rows = conn.execute("""
                SELECT ps.*, c.title as campaign_title
                FROM post_schedule ps
                LEFT JOIN local_campaign c ON ps.campaign_server_id = c.server_id
                WHERE ps.status = 'queued'
                ORDER BY ps.scheduled_at ASC
            """).fetchall()
            result["scheduled"] = [dict(r) for r in sched_rows]
        except Exception as e:
            logger.debug("Error fetching scheduled posts: %s", e)

        # ── Posted: local_post entries with post_url set ──
        try:
            posted_rows = conn.execute("""
                SELECT p.*, c.title as campaign_title,
                       m.impressions, m.likes, m.reposts, m.comments, m.clicks
                FROM local_post p
                LEFT JOIN local_campaign c ON p.campaign_server_id = c.server_id
                LEFT JOIN (
                    SELECT post_id, impressions, likes, reposts, comments, clicks
                    FROM local_metric
                    WHERE id IN (SELECT MAX(id) FROM local_metric GROUP BY post_id)
                ) m ON m.post_id = p.id
                WHERE p.post_url IS NOT NULL
                ORDER BY p.posted_at DESC
            """).fetchall()
            posted_list = []
            for row in posted_rows:
                d = dict(row)
                d["status"] = "live"  # default status
                posted_list.append(d)
            result["posted"] = posted_list
        except Exception as e:
            logger.debug("Error fetching posted posts: %s", e)

        # ── Failed: post_schedule entries with status='failed' ──
        try:
            failed_rows = conn.execute("""
                SELECT ps.*, c.title as campaign_title
                FROM post_schedule ps
                LEFT JOIN local_campaign c ON ps.campaign_server_id = c.server_id
                WHERE ps.status = 'failed'
                ORDER BY ps.created_at DESC
            """).fetchall()
            failed_list = []
            for row in failed_rows:
                d = dict(row)
                d["failed_at"] = d.get("actual_posted_at") or d.get("created_at")
                failed_list.append(d)
            result["failed"] = failed_list
        except Exception as e:
            logger.debug("Error fetching failed posts: %s", e)

        conn.close()
        return result

    except Exception as e:
        logger.error("get_posts failed: %s", e)
        return {"pending_review": [], "scheduled": [], "posted": [], "failed": []}


def handle_approve_content(params):
    """Approve content for a campaign. Can approve single platform or all platforms."""
    campaign_id = params.get("campaign_id")
    platform = params.get("platform")
    approve_all = params.get("approve_all", False)

    if not campaign_id:
        raise ValueError("campaign_id is required")

    try:
        from utils.local_db import init_db, _get_db
        from datetime import datetime, timezone, timedelta

        init_db()
        conn = _get_db()

        if approve_all:
            # Approve all unapproved drafts for this campaign
            draft_rows = conn.execute(
                "SELECT id, platform, draft_text FROM agent_draft WHERE campaign_id = ? AND approved = 0 AND posted = 0",
                (campaign_id,),
            ).fetchall()
        elif platform:
            draft_rows = conn.execute(
                "SELECT id, platform, draft_text FROM agent_draft WHERE campaign_id = ? AND platform = ? AND approved = 0 AND posted = 0",
                (campaign_id, platform),
            ).fetchall()
        else:
            conn.close()
            raise ValueError("Either platform or approve_all is required")

        scheduled_count = 0
        base_time = datetime.now(timezone.utc) + timedelta(minutes=30)

        for i, row in enumerate(draft_rows):
            row_dict = dict(row)
            draft_id = row_dict["id"]
            plat = row_dict["platform"]
            content = row_dict.get("draft_text", "")

            # Mark draft as approved
            conn.execute("UPDATE agent_draft SET approved = 1 WHERE id = ?", (draft_id,))

            # Schedule the post (stagger by 30 min intervals)
            scheduled_at = (base_time + timedelta(minutes=30 * i)).isoformat()
            conn.execute("""
                INSERT INTO post_schedule (campaign_server_id, platform, scheduled_at, content, draft_id, status)
                VALUES (?, ?, ?, ?, ?, 'queued')
            """, (campaign_id, plat, scheduled_at, content, draft_id))
            scheduled_count += 1

        conn.commit()
        conn.close()

        return {"success": True, "approved": scheduled_count}

    except Exception as e:
        logger.error("approve_content failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_skip_content(params):
    """Skip (decline) content for a campaign. Marks drafts as skipped."""
    campaign_id = params.get("campaign_id")
    if not campaign_id:
        raise ValueError("campaign_id is required")

    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        # Mark all unapproved drafts for this campaign as "skipped" (posted=1, approved=0)
        conn.execute(
            "UPDATE agent_draft SET posted = 1 WHERE campaign_id = ? AND approved = 0",
            (campaign_id,),
        )

        # Update campaign status
        conn.execute(
            "UPDATE local_campaign SET status = 'skipped', updated_at = datetime('now') WHERE server_id = ?",
            (campaign_id,),
        )

        conn.commit()
        conn.close()

        return {"success": True}

    except Exception as e:
        logger.error("skip_content failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_edit_content(params):
    """Update the content text for a specific platform draft."""
    campaign_id = params.get("campaign_id")
    platform = params.get("platform")
    text = params.get("text")

    if not campaign_id or not platform:
        raise ValueError("campaign_id and platform are required")
    if text is None:
        raise ValueError("text is required")

    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        # Find the latest unapproved draft for this campaign + platform
        row = conn.execute(
            "SELECT id FROM agent_draft WHERE campaign_id = ? AND platform = ? AND approved = 0 AND posted = 0 ORDER BY id DESC LIMIT 1",
            (campaign_id, platform),
        ).fetchone()

        if row:
            conn.execute(
                "UPDATE agent_draft SET draft_text = ? WHERE id = ?",
                (text, row["id"]),
            )
            conn.commit()
            conn.close()
            return {"success": True, "draft_id": row["id"]}
        else:
            conn.close()
            return {"success": False, "error": "No draft found for this campaign and platform"}

    except Exception as e:
        logger.error("edit_content failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_regenerate_content(params):
    """Regenerate content for a specific platform of a campaign."""
    campaign_id = params.get("campaign_id")
    platform = params.get("platform")

    if not campaign_id or not platform:
        raise ValueError("campaign_id and platform are required")

    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        # Get campaign details
        campaign = conn.execute(
            "SELECT * FROM local_campaign WHERE server_id = ?",
            (campaign_id,),
        ).fetchone()

        if not campaign:
            conn.close()
            return {"success": False, "error": "Campaign not found"}

        campaign_dict = dict(campaign)

        # Try to regenerate using content_generator
        try:
            from utils.content_generator import generate_text

            title = campaign_dict.get("title", "")
            brief = campaign_dict.get("brief", "")
            content_guidance = campaign_dict.get("content_guidance", "")
            assets = campaign_dict.get("assets", "{}")

            new_text = generate_text(
                title=title,
                brief=brief,
                content_guidance=content_guidance,
                assets=assets,
                platforms=[platform],
            )

            if new_text and isinstance(new_text, dict) and platform in new_text:
                generated = new_text[platform]
            elif isinstance(new_text, str):
                generated = new_text
            else:
                generated = f"[Regenerated content for {platform}] -- AI generation temporarily unavailable. Please edit manually."

        except Exception as gen_err:
            logger.warning("Content generation failed, using placeholder: %s", gen_err)
            generated = f"[Regenerated content for {platform}] -- AI generation temporarily unavailable. Please edit manually."

        # Get the current draft's iteration number
        current = conn.execute(
            "SELECT MAX(iteration) as max_iter FROM agent_draft WHERE campaign_id = ? AND platform = ?",
            (campaign_id, platform),
        ).fetchone()
        next_iter = (current["max_iter"] or 0) + 1 if current else 1

        # Mark old unapproved drafts as superseded (set posted=1 to hide them)
        conn.execute(
            "UPDATE agent_draft SET posted = 1 WHERE campaign_id = ? AND platform = ? AND approved = 0",
            (campaign_id, platform),
        )

        # Insert new draft
        conn.execute("""
            INSERT INTO agent_draft (campaign_id, platform, draft_text, quality_score, iteration)
            VALUES (?, ?, ?, 0, ?)
        """, (campaign_id, platform, generated, next_iter))

        conn.commit()
        conn.close()

        return {"success": True, "platform": platform}

    except Exception as e:
        logger.error("regenerate_content failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_cancel_scheduled(params):
    """Cancel a scheduled post and move it back to review."""
    schedule_id = params.get("schedule_id")
    if not schedule_id:
        raise ValueError("schedule_id is required")

    try:
        from utils.local_db import init_db, _get_db

        init_db()
        conn = _get_db()

        # Get the scheduled post's draft_id to un-approve it
        row = conn.execute(
            "SELECT draft_id FROM post_schedule WHERE id = ? AND status = 'queued'",
            (schedule_id,),
        ).fetchone()

        if row and row["draft_id"]:
            # Un-approve the draft so it goes back to pending review
            conn.execute(
                "UPDATE agent_draft SET approved = 0 WHERE id = ?",
                (row["draft_id"],),
            )

        # Remove the scheduled post
        conn.execute(
            "DELETE FROM post_schedule WHERE id = ? AND status = 'queued'",
            (schedule_id,),
        )

        conn.commit()
        conn.close()

        return {"success": True}

    except Exception as e:
        logger.error("cancel_scheduled failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_retry_failed(params):
    """Retry a failed post by resetting its status to queued."""
    schedule_id = params.get("schedule_id")
    if not schedule_id:
        raise ValueError("schedule_id is required")

    try:
        from utils.local_db import init_db, _get_db
        from datetime import datetime, timezone, timedelta

        init_db()
        conn = _get_db()

        # Reset to queued with a new scheduled time (30 minutes from now)
        new_time = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        conn.execute(
            "UPDATE post_schedule SET status = 'queued', error_message = NULL, scheduled_at = ? WHERE id = ? AND status = 'failed'",
            (new_time, schedule_id),
        )
        conn.commit()
        conn.close()

        return {"success": True}

    except Exception as e:
        logger.error("retry_failed failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_register(params):
    """Register a new user account on the server."""
    email = params.get("email")
    password = params.get("password")
    if not email or not password:
        raise ValueError("email and password are required")

    try:
        from utils.server_client import register
        result = register(email, password)
        logger.info("Registered user: %s", email)
        return result
    except Exception as e:
        logger.error("register failed: %s", e)
        return {"error": str(e)}


def handle_login(params):
    """Log in to an existing user account."""
    email = params.get("email")
    password = params.get("password")
    if not email or not password:
        raise ValueError("email and password are required")

    try:
        from utils.server_client import login
        result = login(email, password)
        logger.info("Logged in user: %s", email)
        return result
    except Exception as e:
        logger.error("login failed: %s", e)
        return {"error": str(e)}


def handle_scrape_platform(params):
    """Scrape a single platform profile during onboarding."""
    import asyncio
    platform = params.get("platform")
    if not platform:
        raise ValueError("platform is required")

    try:
        from utils.profile_scraper import SCRAPER_MAP
        from playwright.async_api import async_playwright

        scraper = SCRAPER_MAP.get(platform)
        if not scraper:
            return {"platform": platform, "error": f"No scraper for platform: {platform}"}

        async def _scrape():
            async with async_playwright() as pw:
                return await scraper(pw)

        # Run the async scraper
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, _scrape()).result()
            else:
                result = loop.run_until_complete(_scrape())
        except RuntimeError:
            result = asyncio.run(_scrape())

        # Store in local DB
        try:
            from utils.local_db import upsert_scraped_profile
            import json as _json
            upsert_scraped_profile(
                platform=platform,
                follower_count=result.get("follower_count", 0),
                following_count=result.get("following_count", 0),
                bio=result.get("bio"),
                display_name=result.get("display_name"),
                profile_pic_url=result.get("profile_pic_url"),
                recent_posts=_json.dumps(result.get("recent_posts", [])),
                engagement_rate=result.get("engagement_rate", 0.0),
                posting_frequency=result.get("posting_frequency", 0.0),
                ai_niches="[]",
            )
        except Exception as db_err:
            logger.warning("Failed to store scraped profile in local DB: %s", db_err)

        logger.info("Scraped %s: followers=%d, posts=%d",
                     platform,
                     result.get("follower_count", 0),
                     len(result.get("recent_posts", [])))
        return result

    except Exception as e:
        logger.error("scrape_platform failed for %s: %s", platform, e)
        return {"platform": platform, "error": str(e)}


def handle_classify_niches(params):
    """Run AI niche classification on scraped profiles."""
    import asyncio

    try:
        from utils.niche_classifier import classify_and_store, get_detected_niches

        # Run classification (async)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, classify_and_store()).result()
            else:
                loop.run_until_complete(classify_and_store())
        except RuntimeError:
            asyncio.run(classify_and_store())

        niches = get_detected_niches()
        logger.info("Classified niches: %s", niches)
        return {"niches": niches}

    except Exception as e:
        logger.error("classify_niches failed: %s", e)
        return {"niches": [], "error": str(e)}


def handle_save_onboarding(params):
    """Save onboarding selections (niches, region, mode) to server + local DB."""
    niches = params.get("niches", [])
    region = params.get("region", "global")
    mode = params.get("mode", "semi_auto")

    try:
        from utils.local_db import init_db, _get_db
        import json as _json

        init_db()
        conn = _get_db()

        # Save to local settings
        settings_to_save = {
            "mode": mode,
            "audience_region": region,
            "niche_tags": _json.dumps(niches),
            "onboarding_done": "true",
        }
        for key, value in settings_to_save.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
        conn.close()

        # Sync to server
        try:
            from utils.server_client import update_profile
            update_profile(
                niche_tags=niches,
                audience_region=region,
                mode=mode,
            )
            logger.info("Synced onboarding data to server")
        except Exception as sync_err:
            logger.warning("Failed to sync onboarding to server (non-fatal): %s", sync_err)

        logger.info("Onboarding saved: niches=%s, region=%s, mode=%s", niches, region, mode)
        return {"success": True}

    except Exception as e:
        logger.error("save_onboarding failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_connect_platform(params):
    """Launch browser for platform login (delegates to login_setup.py)."""
    platform = params.get("platform")
    if not platform:
        raise ValueError("platform is required")

    try:
        # Import and run the login setup for this platform
        from login_setup import setup_platform_login

        setup_platform_login(platform)
        return {"success": True, "platform": platform}
    except ImportError:
        # Fallback: run as subprocess
        logger.info("Running login_setup.py as subprocess for %s", platform)
        subprocess.Popen(
            [sys.executable, "scripts/login_setup.py", platform],
            cwd=str(Path.cwd()),
        )
        return {"success": True, "platform": platform, "note": "launched as subprocess"}
    except Exception as e:
        logger.error("connect_platform failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_disconnect_platform(params):
    """Disconnect a platform by removing its browser profile directory."""
    platform = params.get("platform")
    if not platform:
        raise ValueError("platform is required")

    try:
        import shutil

        profile_dir = Path("profiles") / f"{platform}-profile"
        if profile_dir.exists():
            shutil.rmtree(str(profile_dir), ignore_errors=True)
            logger.info("Disconnected platform %s — removed profile directory", platform)
        else:
            logger.info("Platform %s already disconnected (no profile directory)", platform)

        # Clear session health for this platform
        try:
            from utils.local_db import get_setting, set_setting
            import json as _json
            health_raw = get_setting("session_health")
            if health_raw:
                health = _json.loads(health_raw)
                health.pop(platform, None)
                set_setting("session_health", _json.dumps(health))
        except Exception:
            pass

        return {"success": True, "platform": platform}
    except Exception as e:
        logger.error("disconnect_platform failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_refresh_profile(params):
    """Trigger a profile re-scrape for a platform."""
    platform = params.get("platform")
    if not platform:
        raise ValueError("platform is required")

    # Delegate to the scrape_platform handler (same logic)
    try:
        result = handle_scrape_platform({"platform": platform})
        if "error" in result:
            return {"success": False, "platform": platform, "error": result["error"]}
        return {"success": True, "platform": platform}
    except Exception as e:
        logger.error("refresh_profile failed for %s: %s", platform, e)
        return {"success": False, "platform": platform, "error": str(e)}


def handle_start_background_agent(params):
    """Start the background agent loop."""
    import asyncio
    try:
        from background_agent import start_background_agent
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(start_background_agent())
        else:
            loop.run_until_complete(start_background_agent())
        return {"success": True, "status": "started"}
    except Exception as e:
        logger.error("start_background_agent failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_stop_background_agent(params):
    """Stop the background agent loop."""
    import asyncio
    try:
        from background_agent import stop_background_agent
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(stop_background_agent())
        else:
            loop.run_until_complete(stop_background_agent())
        return {"success": True, "status": "stopped"}
    except Exception as e:
        logger.error("stop_background_agent failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_pause_posting(params):
    """Pause the background agent (stop posting, scraping, polling)."""
    try:
        from background_agent import get_agent
        agent = get_agent()
        if agent:
            agent.pause()
            return {"success": True, "paused": True}
        return {"success": False, "error": "Agent not running"}
    except Exception as e:
        logger.error("pause_posting failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_resume_posting(params):
    """Resume the background agent."""
    try:
        from background_agent import get_agent
        agent = get_agent()
        if agent:
            agent.resume()
            return {"success": True, "paused": False}
        return {"success": False, "error": "Agent not running"}
    except Exception as e:
        logger.error("resume_posting failed: %s", e)
        return {"success": False, "error": str(e)}


def handle_get_agent_status(params):
    """Get background agent status — running/paused state + last run times."""
    try:
        from background_agent import get_agent
        agent = get_agent()
        if agent:
            return agent.get_status()
        return {"running": False, "paused": False, "iteration_count": 0}
    except Exception as e:
        logger.error("get_agent_status failed: %s", e)
        return {"running": False, "paused": False, "error": str(e)}


def handle_check_playwright(params):
    """Check if Playwright and Chromium are installed. Install if needed."""
    try:
        import playwright
        from playwright.sync_api import sync_playwright

        # Try to launch — if Chromium is missing, this will fail
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return {"installed": True}
    except Exception as e:
        logger.warning("Playwright check failed: %s. Attempting install...", e)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return {"installed": True, "note": "chromium installed on first run"}
            else:
                return {"installed": False, "error": result.stderr}
        except Exception as install_err:
            return {"installed": False, "error": str(install_err)}


# ── Command dispatch table ──────────────────────────

HANDLERS = {
    "ping": handle_ping,
    "shutdown": handle_shutdown,
    "get_status": handle_get_status,
    "register": handle_register,
    "login": handle_login,
    "scrape_platform": handle_scrape_platform,
    "classify_niches": handle_classify_niches,
    "save_onboarding": handle_save_onboarding,
    "poll_campaigns": handle_poll_campaigns,
    "get_invitations": handle_get_invitations,
    "accept_invitation": handle_accept_invitation,
    "reject_invitation": handle_reject_invitation,
    "get_campaigns": handle_get_campaigns,
    "get_completed_campaigns": handle_get_completed_campaigns,
    "get_earnings": handle_get_earnings,
    "request_payout": handle_request_payout,
    "get_posts": handle_get_posts,
    "approve_content": handle_approve_content,
    "skip_content": handle_skip_content,
    "edit_content": handle_edit_content,
    "regenerate_content": handle_regenerate_content,
    "cancel_scheduled": handle_cancel_scheduled,
    "retry_failed": handle_retry_failed,
    "get_settings": handle_get_settings,
    "update_settings": handle_update_settings,
    "connect_platform": handle_connect_platform,
    "disconnect_platform": handle_disconnect_platform,
    "refresh_profile": handle_refresh_profile,
    "check_playwright": handle_check_playwright,
    "start_background_agent": handle_start_background_agent,
    "stop_background_agent": handle_stop_background_agent,
    "pause_posting": handle_pause_posting,
    "resume_posting": handle_resume_posting,
    "get_agent_status": handle_get_agent_status,
}


# ── Main loop ───────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Amplifier Python Sidecar")
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(Path(__file__).resolve().parent.parent),
        help="Path to the Amplifier project root",
    )
    args = parser.parse_args()

    # Set up paths and imports
    project_root = setup_paths(args.project_root)
    logger.info("Sidecar started. Project root: %s", project_root)

    # Initialize local database
    try:
        from utils.local_db import init_db
        init_db()
        logger.info("Local database initialized")
    except Exception as e:
        logger.error("Failed to initialize local DB: %s", e)

    # Main JSON-RPC loop — read from stdin, write to stdout
    logger.info("Entering JSON-RPC loop (reading from stdin)...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            logger.info("Received: method=%s id=%s", method, request_id)

            if method == "shutdown":
                result = handle_shutdown(params)
                send_response(result, request_id)
                logger.info("Shutdown complete. Exiting.")
                break

            handler = HANDLERS.get(method)
            if handler is None:
                send_error(-32601, f"Method not found: {method}", request_id)
                continue

            result = handler(params)
            send_response(result, request_id)

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON: %s", e)
            send_error(-32700, f"Parse error: {e}", request_id)
        except ValueError as e:
            logger.error("Invalid params: %s", e)
            send_error(-32602, f"Invalid params: {e}", request_id)
        except Exception as e:
            logger.error("Handler error: %s\n%s", e, traceback.format_exc())
            send_error(-32603, f"Internal error: {e}", request_id)

    logger.info("Sidecar exiting.")


if __name__ == "__main__":
    main()
