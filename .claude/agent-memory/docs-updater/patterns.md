---
name: Amplifier documentation patterns
description: Recurring sync patterns and gotchas observed across Amplifier doc update sessions
type: project
---

## Frequently Stale Docs

- `docs/PRD.md` — Implementation Status and model field tables drift quickly. Key things to check: DB model fields (new columns added incrementally), billing mechanics (hold period, tiers), route counts.
- `docs/AMPLIFIER-SPEC.md` — Sections 5.3 (image gen) and 6.1 (posting automation) closely mirror active code. Verify against `scripts/ai/` and `scripts/engine/` when these change.
- `CLAUDE.md` — Architecture section (engine, ai, utils modules) and services section drift on every feature sprint. Always re-read alongside the source directory listing.
- `Memory MEMORY.md` (at `C:/Users/dassa/.claude/projects/.../memory/MEMORY.md`) — Implementation Status block and Key Files section fall behind quickly. Update after every major sprint.

## New Modules Pattern (2026-04-03 sprint)

When a session adds abstraction layers (like `scripts/engine/` and `scripts/ai/`), check if the parent module it replaces (`post.py`, `content_generator.py`) now uses the new layer or still has the old logic hardcoded. In this case:
- `post.py` now tries `post_via_script()` first, falls back to legacy
- `content_generator.py` now delegates to `AiManager` + `ImageManager`
Document BOTH layers to avoid confusion.

## Vercel + Supabase Gotchas (discovered 2026-03-22)

- `rootDirectory` belongs in Vercel project settings, NOT in `vercel.json`. CLI rejects it if present in the file.
- Direct Supabase connection (`db.*.supabase.co:5432`) is unreachable from Vercel. Use transaction pooler: `aws-1-us-east-1.pooler.supabase.com:6543`.
- `echo` adds a trailing `\n` that corrupts Vercel env vars. Use `printf` instead when setting via CLI.
- PostgreSQL engine in `database.py` requires NullPool (serverless) + `prepared_statement_cache_size=0` (pgbouncer) + SSL context with `CERT_NONE`.
- Missing `DATABASE_URL` on Vercel causes silent fallback to ephemeral `/tmp/` SQLite — data lost on cold start, manifests as company login appearing broken.

## Doc Inventory Notes

- The doc inventory (`doc-inventory.md`) had stale Tier 2 entries pointing to files that don't exist (API_REFERENCE.md, DATABASE_SCHEMA.md, USER_FLOWS.md, SYSTEM_DESIGN.md, DEPLOYMENT.md). The real primary docs are `docs/PRD.md`, `docs/AMPLIFIER-SPEC.md`, `docs/pitch-deck.md`. Corrected 2026-04-04.
- `scripts/utils/content_generator.py` and `scripts/utils/metric_collector.py` are new MVP-phase modules. Both were missing from all docs before 2026-03-22 session.
- Route counts drift quickly. Verify against `grep -c "^@router"` on each router file. Admin had 34 → 36 routes due to 2 new financial endpoints. Always recount.
- Admin router file count: 11 files (login, overview, users, companies, campaigns, financial, fraud, analytics, review, audit, settings). Not 10.

## Image Generation Pattern (2026-04-04)

When ImageManager is updated, check these docs for the provider chain order:
- `CLAUDE.md` scripts/ai/ description
- `docs/PRD.md` Section 5 tech stack table + Section 6.6 image generation
- `docs/AMPLIFIER-SPEC.md` Section 5.3
- `docs/pitch-deck.md` Slide 9 AI Content row
- The chain is now: Gemini → Cloudflare → Together → Pollinations → PIL (Gemini was added first in 2026-04-03 session)

When `ImageManager` gains new methods, check: `docs/AMPLIFIER-SPEC.md` Section 5.3 uses method names (`transform()` for img2img, NOT `generate_variation()`). The `generate()` method is txt2img.

## Campaign Image Pipeline Pattern (2026-04-04)

`background_agent.py` has two new helpers that must be documented in all Architecture sections:
- `_download_campaign_product_images(campaign_data)` → `list[str]` (downloads ALL images, not just first)
- `_pick_daily_image(images, day_number)` → `str | None` (day-based rotation through image list)

The `agent_draft` table in `local_db.py` has an `image_path` column (added via migration for existing DBs). Document in CLAUDE.md local_db description and PRD.md local DB table.
