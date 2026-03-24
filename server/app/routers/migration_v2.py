"""Temporary migration endpoint for v2 schema changes.

Runs ALTER TABLE / CREATE TABLE statements against PostgreSQL (Supabase).
All statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS for idempotency.
Remove this router after migration is confirmed on production.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()

# PostgreSQL migration statements — idempotent
_MIGRATION_SQL = [
    # ── campaign_assignments: invitation columns ──────────────────
    "ALTER TABLE campaign_assignments ADD COLUMN IF NOT EXISTS invited_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE campaign_assignments ADD COLUMN IF NOT EXISTS responded_at TIMESTAMPTZ",
    "ALTER TABLE campaign_assignments ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",

    # Backfill expires_at for existing rows (3 days after assigned_at)
    "UPDATE campaign_assignments SET expires_at = assigned_at + INTERVAL '3 days' WHERE expires_at IS NULL",

    # Change payout_multiplier default
    "ALTER TABLE campaign_assignments ALTER COLUMN payout_multiplier SET DEFAULT 1.0",

    # Migrate existing status values
    "UPDATE campaign_assignments SET status = 'accepted' WHERE status = 'assigned'",
    "UPDATE campaign_assignments SET status = 'paid' WHERE status = 'metrics_collected'",
    "UPDATE campaign_assignments SET status = 'rejected' WHERE status = 'skipped'",

    # Change default status
    "ALTER TABLE campaign_assignments ALTER COLUMN status SET DEFAULT 'pending_invitation'",

    # ── users: scraped profile columns ────────────────────────────
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS scraped_profiles JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_detected_niches JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_scraped_at TIMESTAMPTZ",

    # ── campaigns: wizard and invitation columns ──────────────────
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS company_urls JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS ai_generated_brief BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS budget_exhaustion_action VARCHAR(20) NOT NULL DEFAULT 'auto_pause'",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS invitation_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS accepted_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS rejected_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS expired_count INTEGER NOT NULL DEFAULT 0",

    # Backfill invitation counts for existing campaigns
    """UPDATE campaigns SET
        invitation_count = (
            SELECT COUNT(*) FROM campaign_assignments
            WHERE campaign_assignments.campaign_id = campaigns.id
        ),
        accepted_count = (
            SELECT COUNT(*) FROM campaign_assignments
            WHERE campaign_assignments.campaign_id = campaigns.id
            AND campaign_assignments.status IN ('accepted', 'content_generated', 'posted', 'paid')
        )
    WHERE invitation_count = 0""",

    # ── New table: campaign_invitation_log ─────────────────────────
    """CREATE TABLE IF NOT EXISTS campaign_invitation_log (
        id SERIAL PRIMARY KEY,
        campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        event VARCHAR(30) NOT NULL,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",

    # ── New table: content_screening_log ───────────────────────────
    """CREATE TABLE IF NOT EXISTS content_screening_log (
        id SERIAL PRIMARY KEY,
        campaign_id INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
        flagged BOOLEAN NOT NULL DEFAULT FALSE,
        flagged_keywords JSONB,
        screening_categories JSONB,
        reviewed_by_admin BOOLEAN NOT NULL DEFAULT FALSE,
        review_result VARCHAR(20),
        review_notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
]

# Indexes — CREATE INDEX IF NOT EXISTS is idempotent
_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_assignment_user_status ON campaign_assignments(user_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_assignment_expires_at ON campaign_assignments(expires_at)",
    "CREATE INDEX IF NOT EXISTS ix_invitation_log_campaign_id ON campaign_invitation_log(campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_invitation_log_user_id ON campaign_invitation_log(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_invitation_log_campaign_user ON campaign_invitation_log(campaign_id, user_id)",
    "CREATE INDEX IF NOT EXISTS ix_screening_campaign_id ON content_screening_log(campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_screening_review_queue ON content_screening_log(flagged, reviewed_by_admin)",
]


@router.post("/run-v2-migration")
async def run_v2_migration(db: AsyncSession = Depends(get_db)):
    """Run all v2 schema migration statements.

    Idempotent — safe to run multiple times. Uses IF NOT EXISTS and
    ADD COLUMN IF NOT EXISTS so re-runs don't fail.
    """
    results = []

    for stmt in _MIGRATION_SQL:
        try:
            await db.execute(text(stmt))
            results.append({"sql": stmt[:80] + "..." if len(stmt) > 80 else stmt, "status": "ok"})
        except Exception as e:
            results.append({"sql": stmt[:80] + "..." if len(stmt) > 80 else stmt, "status": f"error: {e}"})

    for stmt in _INDEX_SQL:
        try:
            await db.execute(text(stmt))
            results.append({"sql": stmt[:80] + "...", "status": "ok"})
        except Exception as e:
            results.append({"sql": stmt[:80] + "...", "status": f"error: {e}"})

    await db.commit()

    ok_count = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] != "ok")

    return {
        "message": f"Migration complete: {ok_count} ok, {err_count} errors",
        "details": results,
    }
