"""Local SQLite database for campaign/post/metric tracking on the user's device."""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "local.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS local_campaign (
            server_id INTEGER PRIMARY KEY,
            assignment_id INTEGER UNIQUE,
            title TEXT NOT NULL,
            brief TEXT NOT NULL,
            assets TEXT DEFAULT '{}',
            content_guidance TEXT,
            payout_rules TEXT DEFAULT '{}',
            payout_multiplier REAL DEFAULT 1.0,
            status TEXT DEFAULT 'assigned',
            content TEXT,
            invitation_status TEXT DEFAULT 'pending_invitation',
            invited_at TEXT,
            expires_at TEXT,
            responded_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS local_post (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_server_id INTEGER,
            assignment_id INTEGER,
            platform TEXT NOT NULL,
            post_url TEXT,
            content TEXT,
            content_hash TEXT,
            posted_at TEXT,
            status TEXT DEFAULT 'posted',
            server_post_id INTEGER,
            synced INTEGER DEFAULT 0,
            FOREIGN KEY (campaign_server_id) REFERENCES local_campaign(server_id)
        );

        CREATE TABLE IF NOT EXISTS local_metric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            impressions INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            reposts INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            scraped_at TEXT NOT NULL,
            is_final INTEGER DEFAULT 0,
            reported INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES local_post(id)
        );

        CREATE TABLE IF NOT EXISTS local_earning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_server_id INTEGER,
            amount REAL DEFAULT 0.0,
            period TEXT,
            status TEXT DEFAULT 'pending',
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        -- v2: Scraped profile data per platform
        CREATE TABLE IF NOT EXISTS scraped_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL UNIQUE,
            follower_count INTEGER DEFAULT 0,
            following_count INTEGER DEFAULT 0,
            bio TEXT,
            display_name TEXT,
            profile_pic_url TEXT,
            recent_posts TEXT,
            engagement_rate REAL DEFAULT 0.0,
            posting_frequency REAL DEFAULT 0.0,
            ai_niches TEXT DEFAULT '[]',
            scraped_at TEXT NOT NULL
        );

        -- v2: Post scheduling queue for background agent
        -- v2/v3 upgrade: error_code, execution_log, max_retries for structured retry lifecycle
        CREATE TABLE IF NOT EXISTS post_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_server_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            content TEXT,
            image_path TEXT,
            draft_id INTEGER,
            status TEXT DEFAULT 'queued',
            -- Status lifecycle: queued → posting → posted | posted_no_url | failed
            -- Retry:           failed → queued (requeued with incremented retry_count)
            error_code TEXT,
            -- Categorized error: SELECTOR_FAILED | TIMEOUT | AUTH_EXPIRED | RATE_LIMITED | UNKNOWN
            error_message TEXT,
            execution_log TEXT,
            -- JSON array of step results from ScriptExecutor [{step_id, success, message}]
            actual_posted_at TEXT,
            local_post_id INTEGER,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            last_retry_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (campaign_server_id) REFERENCES local_campaign(server_id)
        );

        CREATE INDEX IF NOT EXISTS ix_post_schedule_status_time
            ON post_schedule(status, scheduled_at);

        -- Agent pipeline tables
        CREATE TABLE IF NOT EXISTS agent_user_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT UNIQUE,
            bio TEXT,
            recent_posts TEXT,
            style_notes TEXT,
            follower_count INTEGER DEFAULT 0,
            extracted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            research_type TEXT,
            content TEXT,
            source_url TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_draft (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            platform TEXT,
            draft_text TEXT,
            image_path TEXT,
            -- Path to generated image file (product photo img2img or txt2img from prompt)
            pillar_type TEXT,
            quality_score REAL DEFAULT 0,
            iteration INTEGER DEFAULT 1,
            approved INTEGER DEFAULT 0,
            posted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS agent_content_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            pillar_type TEXT,
            hook_type TEXT,
            avg_engagement_rate REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            best_performing_text TEXT,
            last_updated TEXT DEFAULT (datetime('now'))
        );

        -- Notification feed for background agent events
        CREATE TABLE IF NOT EXISTS local_notification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS ix_notification_read_time
            ON local_notification(read, created_at DESC);
    """)

    # Add new columns to existing tables (idempotent — catches "duplicate column" errors)
    _safe_alter_columns = [
        "ALTER TABLE local_campaign ADD COLUMN invitation_status TEXT DEFAULT 'pending_invitation'",
        "ALTER TABLE local_campaign ADD COLUMN invited_at TEXT",
        "ALTER TABLE local_campaign ADD COLUMN expires_at TEXT",
        "ALTER TABLE local_campaign ADD COLUMN responded_at TEXT",
        # v3: extended profile data (location, about, experience, education) as JSON blob
        "ALTER TABLE scraped_profile ADD COLUMN profile_data TEXT",
        # v3: local_post status column
        "ALTER TABLE local_post ADD COLUMN status TEXT DEFAULT 'posted'",
        # v3: scraped_data for content research
        "ALTER TABLE local_campaign ADD COLUMN scraped_data TEXT DEFAULT '{}'",
        # v4: company name for display
        "ALTER TABLE local_campaign ADD COLUMN company_name TEXT",
    ]
    for stmt in _safe_alter_columns:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()
    logger.info("Local database initialized at %s", DB_PATH)


# ── Settings ───────────────────────────────────────────────────────


# Keys that contain sensitive data and should be encrypted at rest
_SENSITIVE_KEYS = {"gemini_api_key", "mistral_api_key", "groq_api_key"}


def get_setting(key: str, default: str = None) -> str | None:
    conn = _get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    value = row["value"]
    # Decrypt sensitive settings transparently
    if key in _SENSITIVE_KEYS and value:
        from utils.crypto import decrypt_safe
        value = decrypt_safe(value)
    return value


def set_setting(key: str, value: str) -> None:
    # Encrypt sensitive settings before storage
    stored_value = value
    if key in _SENSITIVE_KEYS and value:
        from utils.crypto import encrypt_if_needed
        stored_value = encrypt_if_needed(value)
    conn = _get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, stored_value),
    )
    conn.commit()
    conn.close()


# ── Campaigns ──────────────────────────────────────────────────────


def upsert_campaign(campaign: dict) -> None:
    """Insert or update a campaign from server response.

    IMPORTANT: Does NOT overwrite the local status if the campaign already
    exists with a more advanced status (e.g., assigned, content_generated).
    This prevents re-polling from resetting accepted campaigns back to
    pending_invitation.
    """
    conn = _get_db()
    campaign_id = campaign["campaign_id"]

    # Check if campaign already exists locally
    existing = conn.execute(
        "SELECT status FROM local_campaign WHERE server_id = ?", (campaign_id,)
    ).fetchone()

    if existing is None:
        # New campaign — insert with default pending_invitation status
        conn.execute("""
            INSERT INTO local_campaign
            (server_id, assignment_id, title, brief, assets, content_guidance,
             payout_rules, payout_multiplier, status,
             invitation_status, invited_at, expires_at, responded_at,
             company_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            campaign_id,
            campaign["assignment_id"],
            campaign["title"],
            campaign["brief"],
            json.dumps(campaign.get("assets", {})),
            campaign.get("content_guidance"),
            json.dumps(campaign.get("payout_rules", {})),
            campaign.get("payout_multiplier", 1.0),
            campaign.get("status", "pending_invitation"),
            campaign.get("invitation_status", "pending_invitation"),
            campaign.get("invited_at"),
            campaign.get("expires_at"),
            campaign.get("responded_at"),
            campaign.get("company_name"),
        ))
    else:
        # Existing campaign — update data but PRESERVE the local status
        conn.execute("""
            UPDATE local_campaign SET
                assignment_id = ?, title = ?, brief = ?, assets = ?,
                content_guidance = ?, payout_rules = ?, payout_multiplier = ?,
                invitation_status = ?, invited_at = ?, expires_at = ?,
                responded_at = ?, company_name = ?, updated_at = datetime('now')
            WHERE server_id = ?
        """, (
            campaign["assignment_id"],
            campaign["title"],
            campaign["brief"],
            json.dumps(campaign.get("assets", {})),
            campaign.get("content_guidance"),
            json.dumps(campaign.get("payout_rules", {})),
            campaign.get("payout_multiplier", 1.0),
            campaign.get("invitation_status", "pending_invitation"),
            campaign.get("invited_at"),
            campaign.get("expires_at"),
            campaign.get("responded_at"),
            campaign.get("company_name"),
            campaign_id,
        ))

    conn.commit()
    conn.close()


def get_campaigns(status: str = None) -> list[dict]:
    conn = _get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM local_campaign WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM local_campaign ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_campaign(server_id: int) -> dict | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM local_campaign WHERE server_id = ?", (server_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_campaign_status(server_id: int, status: str, content: str = None) -> None:
    conn = _get_db()
    if content:
        conn.execute(
            "UPDATE local_campaign SET status = ?, content = ?, updated_at = datetime('now') WHERE server_id = ?",
            (status, content, server_id),
        )
    else:
        conn.execute(
            "UPDATE local_campaign SET status = ?, updated_at = datetime('now') WHERE server_id = ?",
            (status, server_id),
        )
    conn.commit()
    conn.close()


def update_invitation_status(server_id: int, invitation_status: str,
                              responded_at: str = None) -> None:
    """Update the invitation status of a local campaign."""
    conn = _get_db()
    conn.execute(
        """UPDATE local_campaign
           SET invitation_status = ?, responded_at = ?, updated_at = datetime('now')
           WHERE server_id = ?""",
        (invitation_status, responded_at, server_id),
    )
    conn.commit()
    conn.close()


def get_campaigns_by_invitation_status(invitation_status: str) -> list[dict]:
    """Get campaigns filtered by invitation status."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM local_campaign WHERE invitation_status = ? ORDER BY created_at DESC",
        (invitation_status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Posts ──────────────────────────────────────────────────────────


def add_post(campaign_server_id: int, assignment_id: int, platform: str,
             post_url: str, content: str, content_hash: str) -> int:
    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO local_post (campaign_server_id, assignment_id, platform,
                                post_url, content, content_hash, posted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        campaign_server_id, assignment_id, platform,
        post_url, content, content_hash,
        datetime.now(timezone.utc).isoformat(),
    ))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id


def get_unsynced_posts() -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM local_post WHERE synced = 0 AND post_url IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_posts_synced(post_ids: list[int], server_post_ids: dict = None) -> None:
    """Mark posts as synced. server_post_ids maps local_id -> server_id."""
    conn = _get_db()
    for pid in post_ids:
        server_id = (server_post_ids or {}).get(pid)
        if server_id:
            conn.execute(
                "UPDATE local_post SET synced = 1, server_post_id = ? WHERE id = ?",
                (server_id, pid),
            )
        else:
            conn.execute("UPDATE local_post SET synced = 1 WHERE id = ?", (pid,))
    conn.commit()
    conn.close()


def get_posts_for_scraping() -> list[dict]:
    """Get posts that need metric scraping (have URLs, campaign still active).

    No time cutoff — scraping continues while the campaign is live.
    The _should_scrape() function in metric_scraper.py decides the schedule.
    """
    conn = _get_db()
    rows = conn.execute("""
        SELECT lp.* FROM local_post lp
        JOIN local_campaign lc ON lp.campaign_server_id = lc.server_id
        WHERE lp.post_url IS NOT NULL
        AND lp.post_url NOT LIKE 'posted_but%'
        AND lp.post_url NOT LIKE '%/submitted%'
        AND lp.post_url NOT LIKE '%/submitted'
        AND lc.status NOT IN ('skipped', 'cancelled')
        ORDER BY lp.posted_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_posts_for_campaign(campaign_server_id: int) -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM local_post WHERE campaign_server_id = ?", (campaign_server_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_posts() -> list[dict]:
    """Return all local posts joined with campaign titles and latest metrics."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT p.*, c.title as campaign_title,
               m.impressions, m.likes, m.reposts, m.comments, m.clicks
        FROM local_post p
        LEFT JOIN local_campaign c ON p.campaign_server_id = c.server_id
        LEFT JOIN (
            SELECT post_id, impressions, likes, reposts, comments, clicks
            FROM local_metric
            WHERE id IN (SELECT MAX(id) FROM local_metric GROUP BY post_id)
        ) m ON m.post_id = p.id
        ORDER BY p.posted_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Metrics ────────────────────────────────────────────────────────


def add_metric(post_id: int, impressions: int = 0, likes: int = 0,
               reposts: int = 0, comments: int = 0, clicks: int = 0,
               is_final: bool = False) -> int:
    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO local_metric (post_id, impressions, likes, reposts, comments,
                                  clicks, scraped_at, is_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post_id, impressions, likes, reposts, comments, clicks,
        datetime.now(timezone.utc).isoformat(), int(is_final),
    ))
    metric_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return metric_id


def get_unreported_metrics() -> list[dict]:
    conn = _get_db()
    rows = conn.execute("""
        SELECT m.*, p.server_post_id
        FROM local_metric m
        JOIN local_post p ON m.post_id = p.id
        WHERE m.reported = 0 AND p.server_post_id IS NOT NULL
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_metrics_reported(metric_ids: list[int]) -> None:
    conn = _get_db()
    for mid in metric_ids:
        conn.execute("UPDATE local_metric SET reported = 1 WHERE id = ?", (mid,))
    conn.commit()
    conn.close()


# ── Earnings ───────────────────────────────────────────────────────


def get_earnings_summary() -> dict:
    conn = _get_db()
    total = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM local_earning").fetchone()
    pending = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM local_earning WHERE status = 'pending'"
    ).fetchone()
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM local_earning WHERE status = 'paid'"
    ).fetchone()
    conn.close()
    return {
        "total_earned": total["total"],
        "pending": pending["total"],
        "paid": paid["total"],
    }


def get_campaign_earnings() -> list[dict]:
    conn = _get_db()
    rows = conn.execute("""
        SELECT e.*, c.title as campaign_title
        FROM local_earning e
        LEFT JOIN local_campaign c ON e.campaign_server_id = c.server_id
        ORDER BY e.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Scraped Profiles (v2) ─────────────────────────────────────────


def upsert_scraped_profile(platform: str, follower_count: int = 0,
                            following_count: int = 0, bio: str = None,
                            display_name: str = None, profile_pic_url: str = None,
                            recent_posts: str = "[]", engagement_rate: float = 0.0,
                            posting_frequency: float = 0.0,
                            ai_niches: str = "[]",
                            profile_data: str = None) -> None:
    """Insert or update a scraped profile for a platform.

    profile_data — JSON string with extended fields: location, about,
    experience (list of jobs), education (list of entries). LinkedIn only for now.
    """
    conn = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO scraped_profile
        (platform, follower_count, following_count, bio, display_name,
         profile_pic_url, recent_posts, engagement_rate, posting_frequency,
         ai_niches, profile_data, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform) DO UPDATE SET
            follower_count=excluded.follower_count,
            following_count=excluded.following_count,
            bio=excluded.bio,
            display_name=excluded.display_name,
            profile_pic_url=excluded.profile_pic_url,
            recent_posts=excluded.recent_posts,
            engagement_rate=excluded.engagement_rate,
            posting_frequency=excluded.posting_frequency,
            ai_niches=excluded.ai_niches,
            profile_data=excluded.profile_data,
            scraped_at=excluded.scraped_at
    """, (platform, follower_count, following_count, bio, display_name,
          profile_pic_url, recent_posts, engagement_rate, posting_frequency,
          ai_niches, profile_data, now))
    conn.commit()
    conn.close()


def get_scraped_profile(platform: str) -> dict | None:
    """Get scraped profile for a single platform."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM scraped_profile WHERE platform = ?", (platform,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_scraped_profiles() -> list[dict]:
    """Get all scraped profiles."""
    conn = _get_db()
    rows = conn.execute("SELECT * FROM scraped_profile ORDER BY platform").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Post Schedule (v2) ────────────────────────────────────────────


def add_scheduled_post(campaign_server_id: int, platform: str,
                        scheduled_at: str, content: str = None,
                        image_path: str = None, draft_id: int = None) -> int:
    """Add a post to the schedule queue."""
    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO post_schedule
        (campaign_server_id, platform, scheduled_at, content, image_path, draft_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (campaign_server_id, platform, scheduled_at, content, image_path, draft_id))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id


def get_scheduled_posts(status: str = None) -> list[dict]:
    """Get scheduled posts, optionally filtered by status."""
    conn = _get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM post_schedule WHERE status = ? ORDER BY scheduled_at ASC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM post_schedule ORDER BY scheduled_at ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_schedule_status(schedule_id: int, status: str,
                            error_message: str = None,
                            error_code: str = None,
                            execution_log: str = None,
                            local_post_id: int = None) -> None:
    """Update the status of a scheduled post.

    v2/v3 upgrade: supports error_code categorization and execution_log
    from ScriptExecutor for debugging failed posts.
    """
    conn = _get_db()
    _migrate_schedule_columns(conn)

    if status == "posted":
        conn.execute(
            """UPDATE post_schedule
               SET status = ?, actual_posted_at = datetime('now'),
                   local_post_id = ?, error_code = NULL, error_message = NULL,
                   execution_log = ?
               WHERE id = ?""",
            (status, local_post_id, execution_log, schedule_id),
        )
    elif status == "posted_no_url":
        conn.execute(
            """UPDATE post_schedule
               SET status = ?, actual_posted_at = datetime('now'),
                   local_post_id = ?, error_message = ?, execution_log = ?
               WHERE id = ?""",
            (status, local_post_id, error_message, execution_log, schedule_id),
        )
    elif status == "failed":
        conn.execute(
            """UPDATE post_schedule
               SET status = ?, error_code = ?, error_message = ?, execution_log = ?
               WHERE id = ?""",
            (status, error_code, error_message, execution_log, schedule_id),
        )
    else:
        conn.execute(
            "UPDATE post_schedule SET status = ? WHERE id = ?",
            (status, schedule_id),
        )
    conn.commit()
    conn.close()


def _migrate_schedule_columns(conn) -> None:
    """Add new columns to existing post_schedule tables (safe migration)."""
    for col, default in [
        ("retry_count", "INTEGER DEFAULT 0"),
        ("last_retry_at", "TEXT"),
        ("error_code", "TEXT"),
        ("execution_log", "TEXT"),
        ("max_retries", "INTEGER DEFAULT 3"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM post_schedule LIMIT 1")
        except Exception:
            conn.execute(f"ALTER TABLE post_schedule ADD COLUMN {col} {default}")
            conn.commit()


MAX_POST_RETRIES = 3


def classify_error(error_message: str) -> str:
    """Classify an error message into a categorized error code.

    v2/v3 upgrade: categorized errors drive retry vs. alert decisions.
    TIMEOUT/SELECTOR_FAILED → retry. AUTH_EXPIRED → alert user. RATE_LIMITED → backoff.
    """
    if not error_message:
        return "UNKNOWN"
    msg = error_message.lower()
    if "selector" in msg or "element_not_found" in msg or "all selectors failed" in msg:
        return "SELECTOR_FAILED"
    if "timeout" in msg or "timed out" in msg:
        return "TIMEOUT"
    if "auth" in msg or "login" in msg or "session" in msg or "401" in msg:
        return "AUTH_EXPIRED"
    if "rate" in msg or "429" in msg or "too many" in msg:
        return "RATE_LIMITED"
    return "UNKNOWN"


def requeue_failed_posts() -> int:
    """Re-queue failed posts for retry with exponential backoff.

    v2/v3 upgrade: backoff = 30min * 2^retry_count (30min, 60min, 120min).
    Only retries SELECTOR_FAILED, TIMEOUT, RATE_LIMITED, UNKNOWN.
    AUTH_EXPIRED errors are NOT retried (user must re-login).

    Returns the number of posts re-queued.
    """
    conn = _get_db()
    _migrate_schedule_columns(conn)

    from datetime import datetime, timedelta
    now = datetime.now()

    rows = conn.execute(
        """SELECT id, retry_count, last_retry_at, max_retries, error_code
           FROM post_schedule
           WHERE status = 'failed'
           AND (retry_count IS NULL OR retry_count < COALESCE(max_retries, ?))""",
        (MAX_POST_RETRIES,),
    ).fetchall()

    requeued = 0
    for row in rows:
        schedule_id = row[0]
        current_retries = row[1] or 0
        last_retry = row[2]
        error_code = row[4] or "UNKNOWN"

        # Don't retry AUTH_EXPIRED — user must re-login
        if error_code == "AUTH_EXPIRED":
            continue

        # Exponential backoff: 30min * 2^retry_count
        backoff_minutes = 30 * (2 ** current_retries)
        if last_retry:
            cutoff = (datetime.fromisoformat(last_retry) + timedelta(minutes=backoff_minutes))
            if now < cutoff:
                continue  # Not enough time has passed

        retry_time = (now + timedelta(minutes=5)).isoformat()
        conn.execute(
            """UPDATE post_schedule
               SET status = 'queued',
                   scheduled_at = ?,
                   retry_count = ?,
                   last_retry_at = datetime('now'),
                   error_message = NULL,
                   error_code = NULL
               WHERE id = ?""",
            (retry_time, current_retries + 1, schedule_id),
        )
        requeued += 1

    conn.commit()
    conn.close()
    return requeued


# ── Agent Pipeline: User Profiles ─────────────────────────────────


def upsert_user_profile(platform: str, bio: str, recent_posts: str,
                        style_notes: str, follower_count: int = 0) -> None:
    conn = _get_db()
    conn.execute("""
        INSERT INTO agent_user_profile (platform, bio, recent_posts, style_notes,
                                        follower_count, extracted_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(platform) DO UPDATE SET
            bio=excluded.bio, recent_posts=excluded.recent_posts,
            style_notes=excluded.style_notes, follower_count=excluded.follower_count,
            extracted_at=excluded.extracted_at
    """, (platform, bio, recent_posts, style_notes, follower_count))
    conn.commit()
    conn.close()


def get_user_profiles(platforms: list[str] = None) -> list[dict]:
    conn = _get_db()
    if platforms:
        placeholders = ",".join("?" for _ in platforms)
        rows = conn.execute(
            f"SELECT * FROM agent_user_profile WHERE platform IN ({placeholders})",
            platforms,
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM agent_user_profile").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_profile(platform: str) -> dict | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM agent_user_profile WHERE platform = ?", (platform,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Agent Pipeline: Research ──────────────────────────────────────


def add_research(campaign_id: int, research_type: str, content: str,
                 source_url: str = None) -> int:
    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO agent_research (campaign_id, research_type, content, source_url)
        VALUES (?, ?, ?, ?)
    """, (campaign_id, research_type, content, source_url))
    rid = cursor.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_research(campaign_id: int) -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM agent_research WHERE campaign_id = ? ORDER BY created_at DESC",
        (campaign_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Agent Pipeline: Drafts ────────────────────────────────────────


def add_draft(campaign_id: int, platform: str, draft_text: str,
              pillar_type: str = None, quality_score: float = 0,
              iteration: int = 1, image_path: str = None) -> int:
    conn = _get_db()
    # Migration: add image_path column if it doesn't exist (for existing DBs)
    try:
        conn.execute("SELECT image_path FROM agent_draft LIMIT 1")
    except Exception:
        conn.execute("ALTER TABLE agent_draft ADD COLUMN image_path TEXT")
        conn.commit()
    cursor = conn.execute("""
        INSERT INTO agent_draft (campaign_id, platform, draft_text, pillar_type,
                                 quality_score, iteration, image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (campaign_id, platform, draft_text, pillar_type, quality_score, iteration, image_path))
    did = cursor.lastrowid
    conn.commit()
    conn.close()
    return did


def get_drafts(campaign_id: int, platform: str = None) -> list[dict]:
    conn = _get_db()
    if platform:
        rows = conn.execute(
            "SELECT * FROM agent_draft WHERE campaign_id = ? AND platform = ? ORDER BY quality_score DESC",
            (campaign_id, platform),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_draft WHERE campaign_id = ? ORDER BY quality_score DESC",
            (campaign_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_draft(draft_id: int) -> None:
    conn = _get_db()
    conn.execute("UPDATE agent_draft SET approved = 1 WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()


def mark_draft_posted(draft_id: int) -> None:
    conn = _get_db()
    conn.execute("UPDATE agent_draft SET posted = 1 WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()


def get_todays_drafts(campaign_id: int) -> list[dict]:
    """Get all drafts created today for a campaign."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM agent_draft WHERE campaign_id = ? AND created_at LIKE ?",
        (campaign_id, f"{today}%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_todays_draft_count(campaign_id: int, platform: str) -> int:
    """Count how many drafts were generated today for this campaign+platform."""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = _get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM agent_draft WHERE campaign_id = ? AND platform = ? AND created_at LIKE ?",
        (campaign_id, platform, f"{today}%"),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_pending_drafts(campaign_id: int = None) -> list[dict]:
    """Get unapproved drafts (approved=0). If campaign_id given, filter by it."""
    conn = _get_db()
    if campaign_id:
        rows = conn.execute(
            "SELECT * FROM agent_draft WHERE approved = 0 AND campaign_id = ? ORDER BY created_at DESC",
            (campaign_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_draft WHERE approved = 0 ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reject_draft(draft_id: int) -> None:
    """Mark a draft as rejected (approved=-1)."""
    conn = _get_db()
    conn.execute("UPDATE agent_draft SET approved = -1 WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()


def get_draft(draft_id: int) -> dict | None:
    """Get a single draft by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM agent_draft WHERE id = ?", (draft_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_draft_text(draft_id: int, new_text: str) -> None:
    """Update draft text (user edited it)."""
    conn = _get_db()
    conn.execute("UPDATE agent_draft SET draft_text = ? WHERE id = ?", (new_text, draft_id))
    conn.commit()
    conn.close()


def get_all_drafts(campaign_id: int = None) -> list[dict]:
    """Get all drafts, optionally filtered by campaign. Include campaign title via JOIN."""
    conn = _get_db()
    if campaign_id:
        rows = conn.execute(
            """SELECT d.*, c.title as campaign_title
               FROM agent_draft d
               LEFT JOIN local_campaign c ON d.campaign_id = c.server_id
               WHERE d.campaign_id = ?
               ORDER BY d.created_at DESC""",
            (campaign_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT d.*, c.title as campaign_title
               FROM agent_draft d
               LEFT JOIN local_campaign c ON d.campaign_id = c.server_id
               ORDER BY d.created_at DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Agent Pipeline: Content Insights ──────────────────────────────


def upsert_content_insight(platform: str, pillar_type: str, hook_type: str,
                           avg_engagement_rate: float, sample_count: int,
                           best_performing_text: str = None) -> None:
    conn = _get_db()
    conn.execute("""
        INSERT INTO agent_content_insights (platform, pillar_type, hook_type,
                                            avg_engagement_rate, sample_count,
                                            best_performing_text, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT DO NOTHING
    """, (platform, pillar_type, hook_type, avg_engagement_rate,
          sample_count, best_performing_text))
    conn.commit()
    conn.close()


def get_content_insights(platform: str = None) -> list[dict]:
    conn = _get_db()
    if platform:
        rows = conn.execute(
            "SELECT * FROM agent_content_insights WHERE platform = ? ORDER BY avg_engagement_rate DESC",
            (platform,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_content_insights ORDER BY avg_engagement_rate DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Notifications ─────────────────────────────────────────────────


def add_notification(notification_type: str, title: str, message: str,
                     data: str = "{}") -> int:
    """Add a notification to the local feed."""
    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO local_notification (type, title, message, data)
        VALUES (?, ?, ?, ?)
    """, (notification_type, title, message, data))
    nid = cursor.lastrowid
    conn.commit()
    conn.close()
    return nid


def get_notifications(unread_only: bool = False, limit: int = 50) -> list[dict]:
    """Get notifications, optionally filtered to unread only."""
    conn = _get_db()
    if unread_only:
        rows = conn.execute(
            "SELECT * FROM local_notification WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM local_notification ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notifications_read(notification_ids: list[int]) -> None:
    """Mark notifications as read."""
    conn = _get_db()
    for nid in notification_ids:
        conn.execute("UPDATE local_notification SET read = 1 WHERE id = ?", (nid,))
    conn.commit()
    conn.close()
