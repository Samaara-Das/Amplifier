# Database Schema v2

**Status**: Draft — aligned with [Product Spec v2](./PRODUCT_SPEC_V2.md)
**Date**: 2026-03-24
**Previous version**: [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)

---

## Overview

Amplifier uses two separate databases:

| Database | Location | ORM / Driver | Tables (v1) | Tables (v2) |
|----------|----------|--------------|-------------|-------------|
| **Server-side** | `amplifier.db` (dev) or PostgreSQL (prod) | SQLAlchemy 2.0 async (aiosqlite / asyncpg) | 8 | 10 |
| **User-side** | `data/local.db` on the user's device | Python `sqlite3` stdlib (synchronous) | 9 | 11 |

Changes in v2 are driven by three product shifts:
1. **Invitation-based campaign flow** replaces auto-assignment
2. **Scraped profile data** replaces self-reported follower counts
3. **Content screening** for prohibited content on campaign creation

---

## 1. Current Schema Summary (v1)

### Server Tables (8)

| # | Table | Key Fields |
|---|-------|-----------|
| 1 | `companies` | id, name, email, password_hash, balance, created_at, updated_at |
| 2 | `campaigns` | id, company_id (FK), title, brief, assets (JSON), budget_total, budget_remaining, payout_rules (JSON), targeting (JSON), content_guidance, penalty_rules (JSON), status, start_date, end_date, created_at, updated_at |
| 3 | `users` | id, email, password_hash, device_fingerprint, platforms (JSON), follower_counts (JSON), niche_tags (JSON), audience_region, trust_score, mode, earnings_balance, total_earned, status, created_at, updated_at |
| 4 | `campaign_assignments` | id, campaign_id (FK), user_id (FK), status, content_mode, payout_multiplier, assigned_at, updated_at |
| 5 | `posts` | id, assignment_id (FK), platform, post_url, content_hash, posted_at, status, created_at |
| 6 | `metrics` | id, post_id (FK), impressions, likes, reposts, comments, clicks, scraped_at, is_final, created_at |
| 7 | `payouts` | id, user_id (FK), campaign_id (FK), amount, period_start, period_end, status, breakdown (JSON), created_at |
| 8 | `penalties` | id, user_id (FK), post_id (FK), reason, amount, description, appealed, appeal_result, created_at |

### Local DB Tables (9)

| # | Table | Key Fields |
|---|-------|-----------|
| 1 | `local_campaign` | server_id (PK), assignment_id, title, brief, assets, content_guidance, payout_rules, payout_multiplier, status, content, created_at, updated_at |
| 2 | `local_post` | id, campaign_server_id (FK), assignment_id, platform, post_url, content, content_hash, posted_at, server_post_id, synced |
| 3 | `local_metric` | id, post_id (FK), impressions, likes, reposts, comments, clicks, scraped_at, is_final, reported |
| 4 | `local_earning` | id, campaign_server_id, amount, period, status, updated_at |
| 5 | `settings` | key (PK), value |
| 6 | `agent_user_profile` | id, platform (UNIQUE), bio, recent_posts, style_notes, follower_count, extracted_at |
| 7 | `agent_research` | id, campaign_id, research_type, content, source_url, created_at |
| 8 | `agent_draft` | id, campaign_id, platform, draft_text, pillar_type, quality_score, iteration, approved, posted, created_at |
| 9 | `agent_content_insights` | id, platform, pillar_type, hook_type, avg_engagement_rate, sample_count, best_performing_text, last_updated |

---

## 2. Server Schema Changes

### 2.1 `campaign_assignments` — Invitation Flow

The current auto-assign model becomes an invitation. Status values change entirely. New timestamp fields track invitation lifecycle.

**Status transition:**

```
pending_invitation  ──→  accepted  ──→  content_generated  ──→  posted  ──→  paid
         │
         ├──→  rejected
         └──→  expired
```

**Changed columns:**

| Column | Old | New | Notes |
|--------|-----|-----|-------|
| `status` | Default `"assigned"`, values: `assigned \| content_generated \| posted \| metrics_collected \| paid \| skipped` | Default `"pending_invitation"`, values: `pending_invitation \| accepted \| content_generated \| posted \| paid \| rejected \| expired` | Full state machine rewrite. `metrics_collected` removed (redundant with `paid`). `skipped` replaced by `rejected`. |
| `payout_multiplier` | Numeric(3,2), default 1.5 | **DEPRECATED** — keep column, set default to `1.0`, stop reading it in billing | Product spec v2: earnings = pure metrics. No content-mode multiplier. Column retained for backward compat. |

**New columns:**

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| `invited_at` | DateTime(tz) | NOT NULL | `func.now()` | When the invitation was sent to the user |
| `responded_at` | DateTime(tz) | NULLABLE | `None` | When the user accepted or rejected |
| `expires_at` | DateTime(tz) | NOT NULL | | 3 days after `invited_at` (set by server on creation) |

**Indexes:**

- Existing: `campaign_id`, `user_id`
- New: composite index on `(user_id, status)` for fast "get my pending invitations" queries
- New: index on `expires_at` for expiration cron job

**Updated SQLAlchemy model:**

```python
class CampaignAssignment(Base):
    __tablename__ = "campaign_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(30), default="pending_invitation")
    # pending_invitation | accepted | content_generated | posted | paid | rejected | expired

    content_mode: Mapped[str] = mapped_column(String(20), default="ai_generated")
    # ai_generated | user_customized | repost

    payout_multiplier: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    # DEPRECATED — kept for backward compat, always 1.0 in v2

    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Renamed from assigned_at for clarity (same column underneath after migration)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_assignment_user_status", "user_id", "status"),
        Index("ix_assignment_expires_at", "expires_at"),
    )
```

---

### 2.2 `users` — Scraped Profile Data

New fields store scraped social media profile data from the user's device. The existing `follower_counts` column is kept for backward compatibility but the server prefers `scraped_profiles` when available.

**New columns:**

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| `scraped_profiles` | JSON | NOT NULL | `{}` | Per-platform scraped data. See JSON structure below. |
| `ai_detected_niches` | JSON | NOT NULL | `[]` | AI-classified niches from scraped post content. JSON array of strings. |
| `last_scraped_at` | DateTime(tz) | NULLABLE | `None` | When the most recent profile scrape was uploaded to the server |

**`scraped_profiles` JSON structure:**

```jsonc
{
  "x": {
    "follower_count": 1500,
    "following_count": 420,
    "bio": "Trading insights & tech...",
    "display_name": "John Doe",
    "profile_pic_url": "https://pbs.twimg.com/...",
    "engagement_rate": 3.2,       // avg (likes+comments)/followers * 100, calculated from recent posts
    "posting_frequency": 1.4,     // avg posts per day over last 30-60 days
    "recent_post_count": 42       // how many posts were analyzed
  },
  "linkedin": {
    "follower_count": 500,
    "following_count": 200,
    "bio": "...",
    "display_name": "John Doe",
    "profile_pic_url": "https://media.licdn.com/...",
    "engagement_rate": 5.1,
    "posting_frequency": 0.3,
    "recent_post_count": 9
  }
  // One entry per connected platform
}
```

**`ai_detected_niches` JSON structure:**

```jsonc
["finance", "tech", "crypto"]
// Allowed values: finance, tech, beauty, fashion, fitness, gaming, food,
//                 travel, education, lifestyle, business, health, entertainment, crypto
```

**Existing columns — behavior changes (no schema change):**

| Column | Change |
|--------|--------|
| `follower_counts` | Still written on registration/update for backward compat. Matching algorithm prefers `scraped_profiles[platform].follower_count` when available. |
| `niche_tags` | Still writable by user (niche confirmation step). Matching uses `ai_detected_niches` as primary, falls back to `niche_tags`. |

---

### 2.3 `campaigns` — AI Wizard & Budget Exhaustion

New fields support the AI campaign creation wizard and invitation tracking.

**New columns:**

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| `company_urls` | JSON | NOT NULL | `[]` | URLs provided by company during wizard step 1. Scraped for enrichment. JSON array of strings. |
| `ai_generated_brief` | Boolean | NOT NULL | `False` | `True` if the brief was generated/enriched by AI from scraped URLs |
| `budget_exhaustion_action` | String(20) | NOT NULL | `"auto_pause"` | `auto_pause` (can top up and resume) or `auto_complete` (campaign ends) |
| `invitation_count` | Integer | NOT NULL | `0` | Denormalized: total invitations sent |
| `accepted_count` | Integer | NOT NULL | `0` | Denormalized: invitations accepted |
| `rejected_count` | Integer | NOT NULL | `0` | Denormalized: invitations rejected |
| `expired_count` | Integer | NOT NULL | `0` | Denormalized: invitations expired |

**`company_urls` JSON structure:**

```jsonc
[
  "https://acme.com",
  "https://acme.com/product/widget"
]
```

**Existing columns — behavior changes (no schema change):**

| Column | Change |
|--------|--------|
| `status` | No new values. `auto_pause` → sets status to `"paused"` (can resume). `auto_complete` → sets status to `"completed"` (terminal). Previously always went to `"completed"`. |

---

### 2.4 New Table: `campaign_invitation_log`

Audit trail for invitation lifecycle events. Append-only log table.

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| `id` | Integer | PRIMARY KEY | auto | |
| `campaign_id` | Integer | FK(`campaigns.id`), INDEX, NOT NULL | | |
| `user_id` | Integer | FK(`users.id`), INDEX, NOT NULL | | |
| `event` | String(30) | NOT NULL | | `sent` \| `accepted` \| `rejected` \| `expired` \| `re_invited` |
| `metadata` | JSON | NULLABLE | `None` | Optional context (e.g., rejection reason, re-invite batch ID) |
| `created_at` | DateTime(tz) | NOT NULL | `func.now()` | Event timestamp |

**Indexes:**

- `campaign_id` (for "show all events for this campaign")
- `user_id` (for "show all invitations this user received")
- composite `(campaign_id, user_id)` for per-user-per-campaign event history

**SQLAlchemy model:**

```python
class CampaignInvitationLog(Base):
    __tablename__ = "campaign_invitation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    event: Mapped[str] = mapped_column(String(30))
    # sent | accepted | rejected | expired | re_invited

    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_invitation_log_campaign_user", "campaign_id", "user_id"),
    )
```

**Relationships:** Belongs to `campaigns` and `users` (no back_populates needed — read-only audit log).

---

### 2.5 New Table: `content_screening_log`

Tracks automated content screening results for campaign briefs at creation time. Flagged campaigns require admin review before activation.

| Column | Type | Constraints | Default | Notes |
|--------|------|-------------|---------|-------|
| `id` | Integer | PRIMARY KEY | auto | |
| `campaign_id` | Integer | FK(`campaigns.id`), INDEX, NOT NULL | | |
| `flagged` | Boolean | NOT NULL | `False` | Whether the automated screen flagged the campaign |
| `flagged_keywords` | JSON | NULLABLE | `None` | List of matched keywords/phrases that triggered the flag |
| `screening_categories` | JSON | NULLABLE | `None` | Which prohibited categories matched (e.g., `["gambling", "adult"]`) |
| `reviewed_by_admin` | Boolean | NOT NULL | `False` | Whether an admin has reviewed this flagged campaign |
| `review_result` | String(20) | NULLABLE | `None` | `approved` \| `rejected` (null until reviewed) |
| `review_notes` | Text | NULLABLE | `None` | Admin's notes on the review decision |
| `created_at` | DateTime(tz) | NOT NULL | `func.now()` | When screening was performed |

**`flagged_keywords` JSON structure:**

```jsonc
["get rich quick", "guaranteed returns", "miracle cure"]
```

**`screening_categories` JSON structure:**

```jsonc
["financial_fraud", "health_claims"]
// Allowed values: adult, gambling, drugs, weapons, financial_fraud, hate_speech, health_claims
```

**Indexes:**

- `campaign_id` (unique — one screening per campaign)
- composite `(flagged, reviewed_by_admin)` for admin review queue: `WHERE flagged = true AND reviewed_by_admin = false`

**SQLAlchemy model:**

```python
class ContentScreeningLog(Base):
    __tablename__ = "content_screening_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), unique=True, index=True)

    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    screening_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)

    reviewed_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    review_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # approved | rejected
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_screening_review_queue", "flagged", "reviewed_by_admin"),
    )
```

---

### 2.6 `payouts` — Remove Multiplier from Billing

No schema changes to the `payouts` table itself. The change is behavioral:

**Billing logic change (in `services/billing.py`):**

```python
# v1 — applies multiplier
earning = raw_earning * float(assignment.payout_multiplier)

# v2 — pure metrics, no multiplier
earning = raw_earning
```

The `breakdown` JSON in existing payout records will still contain `"multiplier"` for historical records. New v2 payouts will either omit the field or set it to `1.0`.

---

### 2.7 `companies` — No Schema Changes

No new columns needed for v2. The company model already supports balance management and campaign CRUD. The AI wizard and URL scraping are handled by new campaign columns (`company_urls`, `ai_generated_brief`).

---

### 2.8 Unchanged Tables

These tables have **no schema changes** in v2:

| Table | Reason |
|-------|--------|
| `posts` | Post model is already sufficient for v2 flows |
| `metrics` | Metric scraping model unchanged |
| `penalties` | Penalty model unchanged |

---

## 3. Local DB Schema Changes

### 3.1 New Table: `scraped_profile`

Stores detailed scraped profile data per platform on the user's device. This is the source of truth for profile data — a summary is uploaded to the server's `users.scraped_profiles` JSON field.

```sql
CREATE TABLE IF NOT EXISTS scraped_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL UNIQUE,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    bio TEXT,
    display_name TEXT,
    profile_pic_url TEXT,
    recent_posts TEXT,                     -- JSON array of {text, likes, comments, shares, posted_at}
    engagement_rate REAL DEFAULT 0.0,      -- calculated: avg (likes+comments)/followers * 100
    posting_frequency REAL DEFAULT 0.0,    -- avg posts per day
    ai_niches TEXT DEFAULT '[]',           -- JSON array of detected niche strings
    scraped_at TEXT NOT NULL               -- ISO 8601 timestamp
);
```

**`recent_posts` JSON structure (stored as TEXT):**

```jsonc
[
  {
    "text": "Thread on why RSI divergence...",
    "likes": 45,
    "comments": 12,
    "shares": 8,
    "posted_at": "2026-03-10T14:30:00Z"
  },
  // ... up to 60 posts
]
```

**Relationship to existing `agent_user_profile` table:**

The existing `agent_user_profile` table is used by the agent pipeline (personal brand content generation). The new `scraped_profile` table is for the campaign marketplace — different purpose, different data shape. Both can coexist. Over time, `agent_user_profile` may be merged or deprecated.

---

### 3.2 Modify: `local_campaign` — Invitation Fields

Add columns to support the invitation flow on the user's device.

**New columns:**

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `invitation_status` | TEXT | `'pending_invitation'` | `pending_invitation` \| `accepted` \| `rejected` \| `expired` — tracks the invitation state locally |
| `invited_at` | TEXT | `None` | ISO 8601, when the invitation was received from server |
| `expires_at` | TEXT | `None` | ISO 8601, invitation expiry deadline |
| `responded_at` | TEXT | `None` | ISO 8601, when user accepted/rejected |

**Updated `status` values:**

The existing `status` column tracks the content workflow *after* acceptance. The new `invitation_status` column tracks the invitation lifecycle *before* content generation.

```
invitation_status: pending_invitation → accepted / rejected / expired
status (post-acceptance): assigned → content_generated → posted → paid
```

**Updated CREATE TABLE:**

```sql
CREATE TABLE IF NOT EXISTS local_campaign (
    server_id INTEGER PRIMARY KEY,
    assignment_id INTEGER UNIQUE,
    title TEXT NOT NULL,
    brief TEXT NOT NULL,
    assets TEXT DEFAULT '{}',
    content_guidance TEXT,
    payout_rules TEXT DEFAULT '{}',
    payout_multiplier REAL DEFAULT 1.0,              -- changed default from 1.5 to 1.0
    status TEXT DEFAULT 'assigned',
    content TEXT,
    invitation_status TEXT DEFAULT 'pending_invitation',  -- NEW
    invited_at TEXT,                                       -- NEW
    expires_at TEXT,                                       -- NEW
    responded_at TEXT,                                     -- NEW
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

---

### 3.3 New Table: `post_schedule`

Manages the local posting schedule. When content is approved, the scheduler creates entries here. The background agent reads from this table to know when to post.

```sql
CREATE TABLE IF NOT EXISTS post_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_server_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,               -- ISO 8601, when to post
    content TEXT,                             -- post text (may reference agent_draft)
    image_path TEXT,                          -- local path to image file, if any
    draft_id INTEGER,                         -- FK to agent_draft.id, nullable
    status TEXT DEFAULT 'queued',             -- queued | posting | posted | failed | cancelled
    error_message TEXT,                       -- failure reason if status = failed
    actual_posted_at TEXT,                    -- ISO 8601, when actually posted
    local_post_id INTEGER,                   -- FK to local_post.id after posting
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_server_id) REFERENCES local_campaign(server_id)
);
```

**Status transitions:**

```
queued  ──→  posting  ──→  posted
                │
                └──→  failed  ──→  queued (retry)
queued  ──→  cancelled (user cancelled before post time)
```

**Indexes (handled via CREATE INDEX):**

```sql
CREATE INDEX IF NOT EXISTS ix_post_schedule_status_time
    ON post_schedule(status, scheduled_at);
```

---

### 3.4 Modify: `settings` — New Setting Keys

No schema change to the table itself. New setting keys used by v2:

| Key | Example Value | Notes |
|-----|--------------|-------|
| `last_profile_scrape` | `2026-03-24T10:30:00Z` | When profiles were last scraped |
| `profile_scrape_interval_hours` | `168` | Hours between automatic re-scrapes (default: 168 = 7 days) |
| `max_active_campaigns` | `5` | Maximum concurrent active campaigns |
| `posting_window_start` | `08:00` | Earliest posting time in user's local timezone |
| `posting_window_end` | `22:00` | Latest posting time in user's local timezone |
| `min_post_spacing_minutes` | `30` | Minimum minutes between campaign posts |
| `notification_new_campaigns` | `true` | Toggle: alert on new campaign invitations |
| `notification_post_failures` | `true` | Toggle: alert on post failures |
| `notification_earnings` | `true` | Toggle: alert on earnings received |

---

## 4. Migration Plan

### 4.1 Server: ALTER Statements

Execute in order. These are PostgreSQL-compatible. For SQLite dev mode, tables are recreated by `init_tables()`.

**campaign_assignments — add invitation columns:**

```sql
-- Add new columns
ALTER TABLE campaign_assignments ADD COLUMN invited_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE campaign_assignments ADD COLUMN responded_at TIMESTAMPTZ;
ALTER TABLE campaign_assignments ADD COLUMN expires_at TIMESTAMPTZ;

-- Set expires_at for existing rows (3 days after assigned_at)
UPDATE campaign_assignments SET expires_at = assigned_at + INTERVAL '3 days';

-- Make expires_at NOT NULL after backfill
ALTER TABLE campaign_assignments ALTER COLUMN expires_at SET NOT NULL;

-- Change default for payout_multiplier
ALTER TABLE campaign_assignments ALTER COLUMN payout_multiplier SET DEFAULT 1.0;

-- Migrate existing status values
UPDATE campaign_assignments SET status = 'accepted' WHERE status = 'assigned';
UPDATE campaign_assignments SET status = 'paid' WHERE status = 'metrics_collected';
UPDATE campaign_assignments SET status = 'rejected' WHERE status = 'skipped';

-- Change default status
ALTER TABLE campaign_assignments ALTER COLUMN status SET DEFAULT 'pending_invitation';

-- Add indexes
CREATE INDEX ix_assignment_user_status ON campaign_assignments(user_id, status);
CREATE INDEX ix_assignment_expires_at ON campaign_assignments(expires_at);
```

**users — add scraped profile columns:**

```sql
ALTER TABLE users ADD COLUMN scraped_profiles JSONB NOT NULL DEFAULT '{}';
ALTER TABLE users ADD COLUMN ai_detected_niches JSONB NOT NULL DEFAULT '[]';
ALTER TABLE users ADD COLUMN last_scraped_at TIMESTAMPTZ;
```

**campaigns — add wizard and invitation columns:**

```sql
ALTER TABLE campaigns ADD COLUMN company_urls JSONB NOT NULL DEFAULT '[]';
ALTER TABLE campaigns ADD COLUMN ai_generated_brief BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campaigns ADD COLUMN budget_exhaustion_action VARCHAR(20) NOT NULL DEFAULT 'auto_pause';
ALTER TABLE campaigns ADD COLUMN invitation_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE campaigns ADD COLUMN accepted_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE campaigns ADD COLUMN rejected_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE campaigns ADD COLUMN expired_count INTEGER NOT NULL DEFAULT 0;
```

**Backfill invitation counts for existing campaigns:**

```sql
UPDATE campaigns SET
    invitation_count = (
        SELECT COUNT(*) FROM campaign_assignments
        WHERE campaign_assignments.campaign_id = campaigns.id
    ),
    accepted_count = (
        SELECT COUNT(*) FROM campaign_assignments
        WHERE campaign_assignments.campaign_id = campaigns.id
        AND campaign_assignments.status IN ('accepted', 'content_generated', 'posted', 'paid')
    );
```

### 4.2 Server: New Table CREATE Statements

**campaign_invitation_log:**

```sql
CREATE TABLE campaign_invitation_log (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    event VARCHAR(30) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_invitation_log_campaign_id ON campaign_invitation_log(campaign_id);
CREATE INDEX ix_invitation_log_user_id ON campaign_invitation_log(user_id);
CREATE INDEX ix_invitation_log_campaign_user ON campaign_invitation_log(campaign_id, user_id);
```

**content_screening_log:**

```sql
CREATE TABLE content_screening_log (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    flagged_keywords JSONB,
    screening_categories JSONB,
    reviewed_by_admin BOOLEAN NOT NULL DEFAULT FALSE,
    review_result VARCHAR(20),
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_screening_campaign_id ON content_screening_log(campaign_id);
CREATE INDEX ix_screening_review_queue ON content_screening_log(flagged, reviewed_by_admin);
```

### 4.3 Server: Data Migration Notes

| Scenario | Action |
|----------|--------|
| Existing assignments with `status='assigned'` | Migrate to `status='accepted'` — these users already had campaigns, treat them as accepted |
| Existing assignments with `status='metrics_collected'` | Migrate to `status='paid'` — redundant state |
| Existing assignments with `status='skipped'` | Migrate to `status='rejected'` |
| `payout_multiplier` in existing assignments | Leave as-is (historical). New assignments default to 1.0. |
| Billing service | Remove `multiplier` from earnings calculation. Set `multiplier: 1.0` in new payout breakdowns. |
| `follower_counts` on existing users | Keep. Matching algorithm checks `scraped_profiles` first, falls back to `follower_counts`. |
| Budget exhaustion | Existing campaigns default to `auto_pause`. Billing service must check `budget_exhaustion_action` to decide whether to set status to `"paused"` or `"completed"`. |
| Existing campaigns with no screening record | No action needed — screening only applies to newly created campaigns |

### 4.4 Server: Billing Service Changes

```python
# v1: earning = raw_earning * float(assignment.payout_multiplier)
# v2: earning = raw_earning (multiplier removed)

# v1: campaign auto-completes when budget < $1.00
# v2: check campaign.budget_exhaustion_action
if float(campaign.budget_remaining) < 1.0:
    if campaign.budget_exhaustion_action == "auto_complete":
        campaign.status = "completed"
    else:  # auto_pause
        campaign.status = "paused"
```

### 4.5 Local DB: Migration via `init_db()`

Local DB uses `CREATE TABLE IF NOT EXISTS`, so new tables are added automatically. For existing tables that need new columns, use `ALTER TABLE` with error suppression (column may already exist on re-runs).

Add to `init_db()` after the `executescript` block:

```python
# Add new columns to existing tables (idempotent — catches "duplicate column" errors)
_safe_alter_columns = [
    "ALTER TABLE local_campaign ADD COLUMN invitation_status TEXT DEFAULT 'pending_invitation'",
    "ALTER TABLE local_campaign ADD COLUMN invited_at TEXT",
    "ALTER TABLE local_campaign ADD COLUMN expires_at TEXT",
    "ALTER TABLE local_campaign ADD COLUMN responded_at TEXT",
]
for stmt in _safe_alter_columns:
    try:
        conn.execute(stmt)
    except sqlite3.OperationalError:
        pass  # Column already exists
```

New tables (`scraped_profile`, `post_schedule`) are added to the existing `executescript` block as `CREATE TABLE IF NOT EXISTS`.

---

## 5. Schema Diagram

### Server-Side ERD (v2)

```
┌─────────────────────┐        ┌──────────────────────────────────┐
│     companies        │        │           campaigns               │
├─────────────────────┤        ├──────────────────────────────────┤
│ id (PK)             │───┐    │ id (PK)                          │
│ name                │   │    │ company_id (FK) ─────────────────│───┘
│ email (UNIQUE)      │   │    │ title                            │
│ password_hash       │   │    │ brief                            │
│ balance             │   │    │ assets (JSON)                    │
│ created_at          │   └───→│ budget_total                     │
│ updated_at          │        │ budget_remaining                 │
└─────────────────────┘        │ payout_rules (JSON)              │
                               │ targeting (JSON)                 │
                               │ content_guidance                 │
                               │ penalty_rules (JSON)             │
                               │ status                           │
                               │ start_date                       │
                               │ end_date                         │
                               │ company_urls (JSON)        [NEW] │
                               │ ai_generated_brief         [NEW] │
                               │ budget_exhaustion_action   [NEW] │
                               │ invitation_count           [NEW] │
                               │ accepted_count             [NEW] │
                               │ rejected_count             [NEW] │
                               │ expired_count              [NEW] │
                               │ created_at                       │
                               │ updated_at                       │
                               └──────┬───────────────────────────┘
                                      │ 1:N
                          ┌───────────┴───────────┐
                          │                       │
                          ▼                       ▼
┌──────────────────────────────────┐  ┌─────────────────────────────┐
│    campaign_assignments          │  │  content_screening_log [NEW] │
├──────────────────────────────────┤  ├─────────────────────────────┤
│ id (PK)                          │  │ id (PK)                     │
│ campaign_id (FK) ────────────────│  │ campaign_id (FK, UNIQUE)    │
│ user_id (FK) ────────────────┐   │  │ flagged                     │
│ status                       │   │  │ flagged_keywords (JSON)     │
│ content_mode                 │   │  │ screening_categories (JSON) │
│ payout_multiplier [DEPR]     │   │  │ reviewed_by_admin           │
│ invited_at              [NEW]│   │  │ review_result               │
│ responded_at            [NEW]│   │  │ review_notes                │
│ expires_at              [NEW]│   │  │ created_at                  │
│ assigned_at                  │   │  └─────────────────────────────┘
│ updated_at                   │   │
└───────────┬──────────────────┘   │
            │ 1:N                  │
            ▼                      │
┌──────────────────────────┐       │
│         posts             │       │
├──────────────────────────┤       │
│ id (PK)                  │       │
│ assignment_id (FK)       │       │
│ platform                 │       │
│ post_url                 │       │
│ content_hash             │       │
│ posted_at                │       │
│ status                   │       │
│ created_at               │       │
└───────────┬──────────────┘       │
            │ 1:N                  │
            ▼                      │
┌──────────────────────────┐       │
│        metrics            │       │
├──────────────────────────┤       │
│ id (PK)                  │       │
│ post_id (FK)             │       │
│ impressions              │       │
│ likes                    │       │
│ reposts                  │       │
│ comments                 │       │
│ clicks                   │       │
│ scraped_at               │       │
│ is_final                 │       │
│ created_at               │       │
└──────────────────────────┘       │
                                   │
┌──────────────────────────────────┘
│
▼
┌──────────────────────────────────────────┐
│                users                      │
├──────────────────────────────────────────┤
│ id (PK)                                  │
│ email (UNIQUE)                           │
│ password_hash                            │
│ device_fingerprint                       │
│ platforms (JSON)                         │
│ follower_counts (JSON)                   │
│ niche_tags (JSON)                        │
│ audience_region                          │
│ trust_score                              │
│ mode                                     │
│ earnings_balance                         │
│ total_earned                             │
│ status                                   │
│ scraped_profiles (JSON)            [NEW] │
│ ai_detected_niches (JSON)          [NEW] │
│ last_scraped_at                    [NEW] │
│ created_at                               │
│ updated_at                               │
└──────────┬───────────────────────────────┘
           │ 1:N
           ├─────────────────────────┐
           ▼                         ▼
┌────────────────────────┐  ┌──────────────────────┐
│       payouts           │  │      penalties        │
├────────────────────────┤  ├──────────────────────┤
│ id (PK)                │  │ id (PK)              │
│ user_id (FK)           │  │ user_id (FK)         │
│ campaign_id (FK)       │  │ post_id (FK)         │
│ amount                 │  │ reason               │
│ period_start           │  │ amount               │
│ period_end             │  │ description          │
│ status                 │  │ appealed             │
│ breakdown (JSON)       │  │ appeal_result        │
│ created_at             │  │ created_at           │
└────────────────────────┘  └──────────────────────┘

┌─────────────────────────────────────────┐
│    campaign_invitation_log [NEW]         │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ campaign_id (FK → campaigns.id)         │
│ user_id (FK → users.id)                │
│ event                                   │
│ metadata (JSON)                         │
│ created_at                              │
└─────────────────────────────────────────┘
```

### Local DB ERD (v2)

```
┌─────────────────────────────────────┐
│          local_campaign              │
├─────────────────────────────────────┤
│ server_id (PK)                      │
│ assignment_id (UNIQUE)              │
│ title                               │
│ brief                               │
│ assets (JSON text)                  │
│ content_guidance                    │
│ payout_rules (JSON text)            │
│ payout_multiplier                   │
│ status                              │
│ content                             │
│ invitation_status             [NEW] │
│ invited_at                    [NEW] │
│ expires_at                    [NEW] │
│ responded_at                  [NEW] │
│ created_at                          │
│ updated_at                          │
└───────────┬─────────────────────────┘
            │ 1:N
            ├────────────────┐
            ▼                ▼
┌────────────────────┐  ┌──────────────────────────────┐
│    local_post       │  │     post_schedule [NEW]       │
├────────────────────┤  ├──────────────────────────────┤
│ id (PK)            │  │ id (PK)                      │
│ campaign_server_id │  │ campaign_server_id (FK)      │
│ assignment_id      │  │ platform                     │
│ platform           │  │ scheduled_at                 │
│ post_url           │  │ content                      │
│ content            │  │ image_path                   │
│ content_hash       │  │ draft_id                     │
│ posted_at          │  │ status                       │
│ server_post_id     │  │ error_message                │
│ synced             │  │ actual_posted_at             │
└───────┬────────────┘  │ local_post_id                │
        │ 1:N           │ created_at                   │
        ▼               └──────────────────────────────┘
┌────────────────────┐
│   local_metric      │
├────────────────────┤
│ id (PK)            │
│ post_id (FK)       │
│ impressions        │
│ likes              │
│ reposts            │
│ comments           │
│ clicks             │
│ scraped_at         │
│ is_final           │
│ reported           │
└────────────────────┘

┌────────────────────┐  ┌──────────────────────────────┐  ┌─────────────────────┐
│   local_earning     │  │    scraped_profile [NEW]      │  │      settings        │
├────────────────────┤  ├──────────────────────────────┤  ├─────────────────────┤
│ id (PK)            │  │ id (PK)                      │  │ key (PK)            │
│ campaign_server_id │  │ platform (UNIQUE)            │  │ value               │
│ amount             │  │ follower_count               │  └─────────────────────┘
│ period             │  │ following_count              │
│ status             │  │ bio                          │
│ updated_at         │  │ display_name                 │
└────────────────────┘  │ profile_pic_url              │
                        │ recent_posts (JSON text)     │
                        │ engagement_rate              │
                        │ posting_frequency            │
                        │ ai_niches (JSON text)        │
                        │ scraped_at                   │
                        └──────────────────────────────┘

Agent pipeline tables (unchanged):
┌─────────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────┐
│  agent_user_profile      │  │  agent_research     │  │    agent_draft        │  │  agent_content_insights       │
├─────────────────────────┤  ├────────────────────┤  ├──────────────────────┤  ├──────────────────────────────┤
│ id, platform (UNIQUE)   │  │ id, campaign_id    │  │ id, campaign_id      │  │ id, platform, pillar_type    │
│ bio, recent_posts       │  │ research_type      │  │ platform, draft_text │  │ hook_type                    │
│ style_notes             │  │ content, source_url│  │ pillar_type          │  │ avg_engagement_rate          │
│ follower_count          │  │ created_at         │  │ quality_score        │  │ sample_count                 │
│ extracted_at            │  │                    │  │ iteration, approved  │  │ best_performing_text         │
└─────────────────────────┘  └────────────────────┘  │ posted, created_at   │  │ last_updated                 │
                                                     └──────────────────────┘  └──────────────────────────────┘
```

---

## Change Summary

| Area | Change Type | What Changed |
|------|------------|-------------|
| `campaign_assignments` | Modified | New status values (invitation flow), new columns: `invited_at`, `responded_at`, `expires_at`. `payout_multiplier` deprecated. |
| `users` | Modified | New columns: `scraped_profiles` (JSON), `ai_detected_niches` (JSON), `last_scraped_at` |
| `campaigns` | Modified | New columns: `company_urls`, `ai_generated_brief`, `budget_exhaustion_action`, invitation counters (4 columns) |
| `campaign_invitation_log` | **New table** | Audit trail for invitation events |
| `content_screening_log` | **New table** | Campaign content screening results |
| `payouts` | Behavioral | Multiplier removed from billing calculation |
| `companies` | No change | |
| `posts` | No change | |
| `metrics` | No change | |
| `penalties` | No change | |
| `scraped_profile` (local) | **New table** | Full scraped profile data per platform |
| `post_schedule` (local) | **New table** | Scheduled posts queue for background agent |
| `local_campaign` (local) | Modified | New columns: `invitation_status`, `invited_at`, `expires_at`, `responded_at` |
| `settings` (local) | Behavioral | New setting keys for scraping, scheduling, notifications |
