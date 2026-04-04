# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 28-29)

## Current Task

**Phase A+B COMPLETE.** Moving to Phase C (Schema Extensions) then Phase D (Tier 4 Features).

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting, Metrics | #27-#34 | All done |
| 4 Money | Stripe, Campaign Detail | #35-#38 | All done |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | Pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | Pending |
| Security | CSRF, Lockout, Reset, Encryption | #66-#76 | All done |
| Future | AI scrapers, content gen, video gen | #51-#65 | Pending |

**44 done, 0 in-progress, 36 pending. 80 total tasks.**

## Session 28-29 — What Was Done

### Phase A Complete (Tasks #28-#38) — 7 commits

**Task #28 — URL Capture (3 commits):**
- Fixed all 4 platforms: X (relative href), LinkedIn (dispatch_event + activity page fallback), Facebook (permalink selectors), Reddit (legacy poster)
- Added `optional` field to ScriptStep, fixed `aria-label` exact matching, Chrome/137 UA consistency
- Reddit body/title fix: click `#post-composer_bodytext` directly (JS focus didn't transfer keyboard focus)

**Tasks #29-#32 — Metrics + Billing:**
- All 4 platform scrapers verified (X aria-labels, LinkedIn body text, Reddit shreddit-post attrs, Facebook selectors)
- Fixed metric scraper: Chrome/137 UA, headless=false default
- Fixed post sync: assignment_id resolved from local_campaign (was hardcoded 0, server silently skipped all posts)
- Fixed server_post_id mapping back to local posts after sync
- Fixed CPM multiplier bug: `get_cpm_multiplier()` now called in billing cycle (amplifier tier 2x verified)
- E2E billing verified: 1000 imp + 10 likes → seedling $4.80, amplifier $9.60

**Tasks #33-#34 — Earnings:**
- Server earnings API verified ($14.40 total, per-campaign/platform breakdown)
- Dashboard card fixed to use server API instead of empty local_earning table

**Tasks #35-#38 — Stripe + Campaign Detail:**
- Stripe test mode verified ($0→$50 instant credit)
- Campaign detail API returns correct data (budget, remaining, status)

### Phase B Complete (Tasks #66-#76) — 6 commits

- **#72 CSRF**: Flask-WTF CSRFProtect + auto-inject via base.html JS
- **#66 X lockout**: Lockout indicators + check before auth/login in session_health.py
- **#67 Session health**: Retry logic, posting success shortcut (skip browser if posted < 24h), Chrome/137 UA
- **#70 Draft count**: Filter by last 24h (was showing all-time stale drafts)
- **#71 Password reset**: POST /api/auth/reset-password for users + companies
- **#73 Encrypt auth**: Already implemented — re-encrypted current token
- **#74 Campaign search**: Search bar on campaigns page, defaults to Active tab when searching
- **#75 Draft UX**: Already implemented — char counts with platform limits
- **FTC disclosure**: Already implemented — `_append_ftc_disclosure()` with X 280-char handling

### Bug Fixes
- Reddit 335 impressions on all posts: generic `/comments/` URLs (no post ID) → scraper visited same listing page. Fixed: filter out generic URLs from scraping
- Facebook profile.php URLs excluded from scraping (not real post permalinks)
- Cleaned up 23 incorrect metrics from generic URLs
- Campaign search redirected to Invitations tab. Fixed: default to Active tab when `?q=` present

### Server Auth Restored
- Old user password found: `dassamaara@gmail.com` / `1304sammy#` (user ID 15)
- 46 posts synced to deployed server with server_post_ids mapped back
- Secondary test account: `amplifier.test@gmail.com` / `Amplifier2026!` (user ID 16, no assignments)

### Key Decisions
- Use Chrome DevTools MCP for self-verification of UI changes
- Rate limiting deferred to Phase G (Vercel has built-in DDoS protection)
- Invitation UX (#76) deferred to Phase F (low-priority polish)
- Reddit JSON script Post button still not working — using legacy poster

## What's Next: Phase C (Schema Extensions)

Per `docs/EXECUTION-ORDER.md`, Phase C is a one-day migration pass before Phase D features. Add all schema fields at once to avoid repeated ALTER TABLEs.

### Server Models (one migration):
- Campaign: `campaign_goal`, `campaign_type`, `tone`, `preferred_formats`, `disclaimer_text`
- User: `zip_code`, `state`, `political_campaigns_enabled`, `subscription_tier`

### Local DB:
- agent_draft: `format_type`, `variant_id`
- local_campaign: `campaign_type`, `campaign_goal`, `tone` (disclaimer_text already added)
- New table: `campaign_posts` (for repost campaigns)

### Then Phase D (largest block):
#68 Repost campaigns → #51/#59 AI profile scraping → #58 Quality gate → #52/#63 4-phase content agent → #64 All content formats → #65 Preview UI → #61 Self-learning → #62 Free/paid tiers → Political

## Key Reference Files

### Implementation Planning
- `docs/REMAINING-WORK.md` — Task specs
- `docs/EXECUTION-ORDER.md` — Phase ordering
- `docs/SCHEMA-CHANGES.md` — All DB field additions
- `docs/FILE-CHANGE-INDEX.md` — File-to-task mapping

### Core Code
- `scripts/post.py` — Posting orchestrator
- `scripts/engine/` — JSON posting engine
- `scripts/utils/metric_scraper.py` — Per-platform scrapers
- `scripts/utils/content_generator.py` — AI content gen + FTC disclosure
- `scripts/utils/local_db.py` — Local SQLite (13 tables)
- `scripts/utils/server_client.py` — Server API client (encrypted auth)
- `server/app/services/billing.py` — Billing with CPM multiplier fix
- `server/app/routers/auth.py` — Auth + password reset

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login
- **User App**: http://localhost:5222

## Server Auth
- Primary: `dassamaara@gmail.com` / `1304sammy#` (ID 15)
- Test: `amplifier.test@gmail.com` / `Amplifier2026!` (ID 16)
- Auth file: `config/server_auth.json` (encrypted)
