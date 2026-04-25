# 2026-04-25 — Schema fixes applied to Supabase prod (Task #41 post-deploy UAT)

Two production-blocking schema drift bugs found and fixed via direct `psql` against the Supabase production DB. Captured here so a future Alembic baseline revision can pick them up.

## 1. Missing column

```sql
ALTER TABLE campaign_assignments ADD COLUMN IF NOT EXISTS decline_reason TEXT;
```

Symptom: `GET /admin/` returned 500 — `column campaign_assignments.decline_reason does not exist`.

## 2. JSON → JSONB conversion (14 columns across 7 tables)

PostgreSQL plain `json` type has no equality operator — broke any `GROUP BY` on a json column.

Symptom: `GET /company/influencers` returned 500 — `could not identify an equality operator for type json`.

```sql
ALTER TABLE audit_log ALTER COLUMN details TYPE jsonb USING details::jsonb;
ALTER TABLE campaign_invitation_log ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb;
ALTER TABLE campaigns ALTER COLUMN assets TYPE jsonb USING assets::jsonb;
ALTER TABLE campaigns ALTER COLUMN payout_rules TYPE jsonb USING payout_rules::jsonb;
ALTER TABLE campaigns ALTER COLUMN penalty_rules TYPE jsonb USING penalty_rules::jsonb;
ALTER TABLE campaigns ALTER COLUMN targeting TYPE jsonb USING targeting::jsonb;
ALTER TABLE content_screening_log ALTER COLUMN flagged_keywords TYPE jsonb USING flagged_keywords::jsonb;
ALTER TABLE content_screening_log ALTER COLUMN screening_categories TYPE jsonb USING screening_categories::jsonb;
ALTER TABLE content_screening_logs ALTER COLUMN flagged_keywords TYPE jsonb USING flagged_keywords::jsonb;
ALTER TABLE content_screening_logs ALTER COLUMN screening_categories TYPE jsonb USING screening_categories::jsonb;
ALTER TABLE payouts ALTER COLUMN breakdown TYPE jsonb USING breakdown::jsonb;
ALTER TABLE users ALTER COLUMN follower_counts TYPE jsonb USING follower_counts::jsonb;
ALTER TABLE users ALTER COLUMN niche_tags TYPE jsonb USING niche_tags::jsonb;
ALTER TABLE users ALTER COLUMN platforms TYPE jsonb USING platforms::jsonb;
```

## Root cause

Alembic is configured (`server/alembic.ini`, `server/alembic/env.py`) but `server/alembic/versions/` is **empty** — no migrations have ever been generated. Models evolved without DB sync. Drift accumulated silently until UAT caught it.

## Follow-up

- Tracked as Task #11: Generate baseline Alembic revision + enforce migration policy for future model changes.
- Going forward: ALWAYS use `JSONB` (never `json`) for new columns. JSONB has equality operator + GIN-indexable + same Python interface.
