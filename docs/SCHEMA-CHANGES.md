# Amplifier — Schema Change Manifest

**Purpose**: Every database field that needs to be added or modified across ALL remaining tasks. Do these in one migration pass per database to avoid repeated ALTER TABLEs.

---

## Server Database (SQLAlchemy Models → Supabase PostgreSQL)

### Campaign Model (`server/app/models/campaign.py`)

| Field | Type | Default | Added By Task | Purpose |
|---|---|---|---|---|
| `campaign_goal` | String(30) | `"brand_awareness"` | #52/#63 | Drives content strategy: brand_awareness, leads, virality, engagement |
| `campaign_type` | String(20) | `"ai_generated"` | #68, Political | ai_generated, repost, political |
| `tone` | String(50) | `None` | #52/#63 | Content voice: professional, casual, edgy, educational, urgent |
| `preferred_formats` | JSONB | `{}` | #64 | Per-platform format preferences: `{"x": ["thread", "poll"], "linkedin": ["carousel"]}` |
| `disclaimer_text` | Text | `None` | FTC, Political | Appended to every post: "#ad" or "Paid for by [committee]" |

**Migration SQL:**
```sql
ALTER TABLE campaigns ADD COLUMN campaign_goal VARCHAR(30) DEFAULT 'brand_awareness';
ALTER TABLE campaigns ADD COLUMN campaign_type VARCHAR(20) DEFAULT 'ai_generated';
ALTER TABLE campaigns ADD COLUMN tone VARCHAR(50);
ALTER TABLE campaigns ADD COLUMN preferred_formats JSONB DEFAULT '{}';
ALTER TABLE campaigns ADD COLUMN disclaimer_text TEXT;
```

### User Model (`server/app/models/user.py`)

| Field | Type | Default | Added By Task | Purpose |
|---|---|---|---|---|
| `zip_code` | String(10) | `None` | Political | US zip code for geo-targeting |
| `state` | String(2) | `None` | Political | US state abbreviation |
| `political_campaigns_enabled` | Boolean | `False` | Political | Opt-in for political campaign matching |
| `subscription_tier` | String(20) | `"free"` | #62 | free or paid (orthogonal to reputation tier) |

**Migration SQL:**
```sql
ALTER TABLE users ADD COLUMN zip_code VARCHAR(10);
ALTER TABLE users ADD COLUMN state VARCHAR(2);
ALTER TABLE users ADD COLUMN political_campaigns_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free';
```

### New Table: `campaign_posts` (for repost campaigns)

| Field | Type | Purpose |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `campaign_id` | FK → campaigns.id | Parent campaign |
| `platform` | String(20) | x, linkedin, facebook, reddit |
| `content` | Text | Post text |
| `image_url` | Text | Optional image URL |
| `post_order` | Integer | Sequence within campaign |
| `scheduled_offset_hours` | Integer | Hours after campaign start to post |
| `created_at` | DateTime | Server default |

**Added by**: Task #68 (Repost campaign type)

### Payout Model — Already Updated

Fields added in session 26 (no further changes needed):
- `amount_cents` (Integer) — done
- `available_at` (DateTime) — done
- Expanded status lifecycle — done

### Existing Fields Already Added in Session 26

These are DONE — listed here for completeness:
- Company: `balance_cents` ✓
- User: `earnings_balance_cents`, `total_earned_cents`, `tier`, `successful_post_count` ✓
- Payout: `amount_cents`, `available_at` ✓
- Penalty: `amount_cents` ✓

---

## Local Database (SQLite — `scripts/utils/local_db.py`)

### `agent_draft` Table Additions

| Field | Type | Default | Added By Task | Purpose |
|---|---|---|---|---|
| `image_path` | TEXT | `None` | Done (session 26) | Path to generated image |
| `format_type` | TEXT | `"text"` | #64 | text, thread, poll, carousel, video, image_only |
| `variant_id` | INTEGER | `0` | #61 | A/B test variant tracking |

### New Table: `campaign_posts` (local mirror for repost campaigns)

```sql
CREATE TABLE IF NOT EXISTS campaign_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_server_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    content TEXT,
    image_url TEXT,
    post_order INTEGER DEFAULT 0,
    scheduled_offset_hours INTEGER DEFAULT 0,
    FOREIGN KEY (campaign_server_id) REFERENCES local_campaign(server_id)
);
```

**Added by**: Task #68

### `local_campaign` Table Additions

| Field | Type | Default | Added By Task | Purpose |
|---|---|---|---|---|
| `campaign_type` | TEXT | `"ai_generated"` | #68 | ai_generated, repost, political |
| `campaign_goal` | TEXT | `None` | #52/#63 | Content strategy driver |
| `tone` | TEXT | `None` | #52/#63 | Content voice |
| `disclaimer_text` | TEXT | `None` | FTC, Political | Appended to posts |

### `settings` Table Additions (key-value)

| Key | Value | Added By Task | Purpose |
|---|---|---|---|
| `zip_code` | String | Political | User's zip code |
| `state` | String | Political | User's US state |
| `political_campaigns_enabled` | "true"/"false" | Political | Opt-in flag |
| `subscription_tier` | "free"/"paid" | #62 | Subscription status |

---

## API Contract Changes

### Campaign Create Endpoint (`POST /api/company/campaigns`)

Add to accepted fields:
```python
campaign_goal: str = "brand_awareness"    # NEW
campaign_type: str = "ai_generated"       # NEW
tone: str | None = None                   # NEW
preferred_formats: dict = {}              # NEW
disclaimer_text: str | None = None        # NEW
```

### Campaign Wizard Endpoint (`POST /api/company/campaigns/ai-wizard`)

Already accepts `campaign_goal` — but currently does NOT persist it to Campaign. Fix: store `campaign_goal` on the Campaign record after wizard generates the brief.

### User Profile Endpoint (`PATCH /api/users/me`)

Add to accepted fields:
```python
zip_code: str | None = None               # NEW
state: str | None = None                   # NEW
political_campaigns_enabled: bool = False  # NEW
subscription_tier: str = "free"            # NEW (or managed via Stripe webhook)
```

### Campaign Poll Endpoint (`GET /api/campaigns/mine`)

CampaignBrief response must include new fields:
```python
campaign_type: str      # so user app knows if it's repost vs ai_generated
campaign_goal: str      # so content gen knows the strategy
tone: str | None        # so content gen knows the voice
disclaimer_text: str | None  # so content gen appends it
```

---

## Migration Strategy

### Server (Supabase PostgreSQL)

Option 1 (recommended for dev): Drop and recreate tables via `init_tables()` — SQLAlchemy `create_all()` handles new columns on fresh DB.

Option 2 (for production with existing data): Run ALTER TABLE statements manually via Supabase SQL Editor or add an Alembic migration.

### Local DB (SQLite)

Use the existing migration pattern in `local_db.py`: try SELECT on new column, if it fails run ALTER TABLE. This handles existing databases gracefully.

```python
def _migrate_campaign_columns(conn):
    for col, typedef in [
        ("campaign_type", "TEXT DEFAULT 'ai_generated'"),
        ("campaign_goal", "TEXT"),
        ("tone", "TEXT"),
        ("disclaimer_text", "TEXT"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM local_campaign LIMIT 1")
        except Exception:
            conn.execute(f"ALTER TABLE local_campaign ADD COLUMN {col} {typedef}")
            conn.commit()
```
