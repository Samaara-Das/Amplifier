# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 26-27)

## Current Task

**Task #28 — Verify: Scheduled Posting** (in-progress) — paused during Sessions 24-27 for co-founder docs, codebase audit, v2/v3 upgrade sprint, political campaigns strategy, and implementation planning.

Next session: Read 4 implementation docs and start Phase A (fix posting URL capture → verify metrics → verify billing).

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting (#27-#28), Metrics (#29-#30) | **#27 done, #28 in-progress** |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |
| Future | AI scrapers, content gen, video gen, tiers | #51-#80 | All pending |

**27 done, 1 in-progress, 52 pending. 80 total tasks.**

## Session 26-27 — What Was Done

### v2/v3 Upgrade Sprint (8 feature commits)

**Phase 1 — Declarative JSON Posting Engine** (`994adcf`)
- `scripts/engine/` — 6 modules: script_parser, selector_chain, human_timing, error_recovery, script_executor (13 action types)
- `config/scripts/` — 4 JSON scripts (x, linkedin, facebook, reddit)
- `post.py` refactored: script-first with legacy fallback

**Phase 2 — Financial Safety** (`019a667`)
- AES-256-GCM encryption (server + client), 7-day earning hold, integer cents
- Payout lifecycle: pending→available→processing→paid|voided|failed

**Phase 3+5 — Automation, AI, Tiers** (`4d085de`)
- AiManager with pluggable providers (Gemini→Mistral→Groq)
- Post lifecycle: error_code, execution_log, exponential backoff retry
- Payout automation: process_pending_payouts()
- Reputation tiers: seedling/grower/amplifier with auto-promotion

**Image Generation Upgrade** (`f840964`)
- ImageManager with 5 providers (Gemini primary, 500 free/day)
- UGC post-processing (grain, JPEG, EXIF injection)
- img2img from campaign product photos

**Campaign Image Pipeline Fix** (`168137d`)
- Critical gap found: product images stored but never used for generation
- Fixed: downloads all images, daily rotation, passes to img2img

**Modular Dashboard Refactor** (`ccf919e`)
- Admin: 11 routers (was 1 monolithic file), 14 pages, 36 routes
- Company: 7 routers, 10 pages

### Documentation Sprint (9 commits)
- `docs/AMPLIFIER-SPEC.md` — Complete multi-implementation system spec
- `docs/V2-V3-UPGRADE-PLAN.md` — 15 upgrades across 5 phases
- `docs/IMAGE-GENERATION-UPGRADE.md` — Image gen spec
- Rewrote `docs/concept.md` and `docs/technical-architecture.md` from scratch
- Updated 15 stale docs across 3 parallel agents
- Added 8 Mermaid diagrams (sequence, flowcharts, state machines)
- `docs/political-campaigns.md` — Full political vertical strategy

### Implementation Planning (final commits)
- `docs/REMAINING-WORK.md` (2,785 lines) — Every task with current state, implementation steps, data flow connections, verification criteria
- `docs/EXECUTION-ORDER.md` — 7 phases (A-G) with dependency chains, gate criteria, visual map
- `docs/SCHEMA-CHANGES.md` — All DB field additions in one manifest (Campaign: 5 new, User: 4 new, 1 new table)
- `docs/FILE-CHANGE-INDEX.md` — File-to-task mapping, conflict map, new files list

### Bug Found
- `get_cpm_multiplier()` in billing.py exists but is never called by `run_billing_cycle()` — amplifier tier's 2x CPM is defined but not applied. Documented in REMAINING-WORK.md for Phase A fix.

### Key Decisions
- local-dream rejected (CC-BY-NC-4.0 non-commercial, Android-only)
- Keep FastAPI + Playwright stack — adopt v2/v3 patterns only
- Gemini Flash Image as primary (500 free/day, img2img)
- Integer cents, 7-day hold, 3-tier reputation
- JSON scripts for posting (update JSON not Python when platforms change)
- AI browser automation deferred (JSON scripts handle 80%)
- Political campaigns: one app, not separate product (campaign_type field + user opt-in)
- Confirmed Tier 4 tasks: #51/59, #52/63, #58, #61, #62, #64, #65, #68, Political

## How to Start Next Session

Tell Claude:
> Read these 4 docs and start implementing:
> - `docs/REMAINING-WORK.md`
> - `docs/EXECUTION-ORDER.md`
> - `docs/SCHEMA-CHANGES.md`
> - `docs/FILE-CHANGE-INDEX.md`

Claude will: determine the phase from EXECUTION-ORDER.md, implement it, provide a step-by-step verification checklist, wait for results, fix failures, move to next phase automatically.

## Remaining Blockers (Priority Order)
1. Posting URL capture broken on LinkedIn/Facebook/Reddit (Task #28)
2. Metric scraping unverified E2E (Tasks #29-30)
3. Billing unverified E2E — plus get_cpm_multiplier() bug (Tasks #31-32)
4. X account detection risk (locked during testing)
5. Real Stripe payments (both sides)
6. FTC disclosure not in content generator
7. Distribution — no installable app yet

## Key Reference Files

### Implementation Planning
- `docs/REMAINING-WORK.md` — 58 tasks with implementation + verification specs
- `docs/EXECUTION-ORDER.md` — 7 phases, dependency chains, gate criteria
- `docs/SCHEMA-CHANGES.md` — All DB migrations in one manifest
- `docs/FILE-CHANGE-INDEX.md` — File-to-task mapping + conflict map

### Core Code
- `scripts/post.py` — Posting orchestrator (script-first, legacy fallback)
- `scripts/engine/` — JSON posting engine (6 modules, 13 action types)
- `config/scripts/` — Platform JSON scripts (x, linkedin, facebook, reddit)
- `scripts/ai/` — AiManager (text) + ImageManager (images, 5 providers, post-processing)
- `scripts/background_agent.py` — 6 async tasks, campaign image download + rotation
- `scripts/utils/content_generator.py` — Text+image gen via AiManager+ImageManager
- `scripts/utils/local_db.py` — 13 tables, encrypted keys, retry lifecycle
- `server/app/services/billing.py` — Cents math, hold periods, tier promotion
- `server/app/services/payments.py` — Stripe Connect + auto payout processing
- `server/app/services/matching.py` — AI scoring + tier-based limits

### Docs
- `docs/AMPLIFIER-SPEC.md` — Complete system spec (all 3 versions)
- `docs/concept.md` — Product concept (rewritten session 26)
- `docs/technical-architecture.md` — Architecture reference (rewritten session 26)
- `docs/political-campaigns.md` — Political vertical strategy
- `SLC.md` — SLC spec (outdated — needs rewrite after Phase E)

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222
- **GitHub**: https://github.com/Samaara-Das/Amplifier (private)

## Test Commands
```bash
python scripts/user_app.py
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
python scripts/tests/test_all_post_types.py
vercel deploy --yes --prod --cwd server
```
