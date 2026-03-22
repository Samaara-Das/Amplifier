---
name: Amplifier documentation patterns
description: Recurring sync patterns and gotchas observed across Amplifier doc update sessions
type: project
---

## Frequently Stale Docs

- `docs/campaign-platform-architecture.md` — Tech Stack and Implementation Status sections fall out of sync quickly. Always verify these against `server/app/core/database.py` (DB choice) and `.claude/task-context.md` (phase status).
- `docs/DEPLOYMENT.md` — Vercel config block and env var table drift when database or deployment approach changes. Check against `vercel.json` and `database.py` every session.
- `docs/SYSTEM_DESIGN.md` — Decision 5 (content generation) and Decision 9 (matching algorithm) are tied to active code. Verify against `scripts/utils/content_generator.py` and `server/app/services/matching.py`.

## Vercel + Supabase Gotchas (discovered 2026-03-22)

- `rootDirectory` belongs in Vercel project settings, NOT in `vercel.json`. CLI rejects it if present in the file.
- Direct Supabase connection (`db.*.supabase.co:5432`) is unreachable from Vercel. Use transaction pooler: `aws-1-us-east-1.pooler.supabase.com:6543`.
- `echo` adds a trailing `\n` that corrupts Vercel env vars. Use `printf` instead when setting via CLI.
- PostgreSQL engine in `database.py` requires NullPool (serverless) + `prepared_statement_cache_size=0` (pgbouncer) + SSL context with `CERT_NONE`.
- Missing `DATABASE_URL` on Vercel causes silent fallback to ephemeral `/tmp/` SQLite — data lost on cold start, manifests as company login appearing broken.

## Doc Inventory Notes

- `mvp.md` at repo root is the MVP spec. Added to inventory Tier 5. Cross-check against task-context.md for phase completion status.
- `scripts/utils/content_generator.py` and `scripts/utils/metric_collector.py` are new MVP-phase modules. Both were missing from all docs before 2026-03-22 session.
