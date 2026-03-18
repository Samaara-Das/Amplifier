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
            payout_multiplier REAL DEFAULT 1.5,
            status TEXT DEFAULT 'assigned',
            content TEXT,
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
    """)
    conn.commit()
    conn.close()
    logger.info("Local database initialized at %s", DB_PATH)


# ── Settings ───────────────────────────────────────────────────────


def get_setting(key: str, default: str = None) -> str | None:
    conn = _get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = _get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


# ── Campaigns ──────────────────────────────────────────────────────


def upsert_campaign(campaign: dict) -> None:
    """Insert or update a campaign from server response."""
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO local_campaign
        (server_id, assignment_id, title, brief, assets, content_guidance,
         payout_rules, payout_multiplier, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        campaign["campaign_id"],
        campaign["assignment_id"],
        campaign["title"],
        campaign["brief"],
        json.dumps(campaign.get("assets", {})),
        campaign.get("content_guidance"),
        json.dumps(campaign.get("payout_rules", {})),
        campaign.get("payout_multiplier", 1.5),
        "assigned",
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
    """Get posts that need metric scraping (have URLs, posted within last 72h)."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT * FROM local_post
        WHERE post_url IS NOT NULL
        AND posted_at > datetime('now', '-3 days')
        ORDER BY posted_at ASC
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
