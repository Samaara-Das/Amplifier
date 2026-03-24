# Amplifier — Task Context

**Last Updated**: 2026-03-24 (Session 18)

## Current Task
- **Branch: `main`** — Amplifier v2 built (29 tasks, 588 tests). UAT testing in progress.
- Company dashboard: 7/7 core features verified working on Vercel
- User app (Tauri): sidecar connection fixed, real data showing, testing accept/reject/approve flows
- Active bugs: accept/reject campaigns and approve/skip content failing in user app (server_client functions added, needs testing)

## Project Overview
Two-sided marketplace:
1. **Company Dashboard** (Web, Vercel) — Companies create campaigns, monitor performance, manage budgets
2. **User App** (Tauri Desktop) — Users earn money by posting campaign content to social media
3. **Admin Dashboard** (Web, Vercel) — Platform management, fraud detection, payouts
4. **Server API** (FastAPI, Vercel + Supabase PostgreSQL) — 82 routes, 10 models, matching, billing, trust

## Amplifier v2 — Build Summary (Session 18)

### What Was Built (29 tasks, all complete)
**Phase 1: Server Foundation (Tasks 1-6)**
- [x] DB schema migration (invitation states, scraped profiles, screening log, invitation log)
- [x] Campaign invitation system (replace auto-assign with accept/reject, 3-day expiry, max 5)
- [x] Removed payout multiplier (earnings = pure metrics)
- [x] Prohibited content screening (6 categories, admin review queue)
- [x] Campaign management (clone, delete, budget top-up, auto-pause/complete, $50 min, edit propagation)
- [x] Fixed user earnings endpoint (real per-campaign/platform breakdown, payout withdrawal)

**Phase 2: Profile Scraping (Tasks 7-8)**
- [x] Profile scraping system (X, LinkedIn, Facebook, Reddit scrapers)
- [x] AI niche classification (Gemini classifies from scraped posts)

**Phase 3: AI Features (Tasks 9-12)**
- [x] AI campaign creation wizard (URL scraping, Gemini generation, reach estimation)
- [x] AI-powered matching (LLM relevance scoring + caching)
- [x] Content quality improvements (brief adherence scoring)
- [x] CSV export for campaign reports

**Phase 4: Tauri Desktop App (Tasks 13-22)**
- [x] Tauri project setup + Python sidecar (JSON-RPC over stdin/stdout)
- [x] 7-step onboarding wizard
- [x] Home dashboard (stat cards, platform health, activity feed)
- [x] Campaigns tab (invitations, active pipeline, completed)
- [x] Posts tab (per-platform editing/regeneration, scheduled, posted, failed)
- [x] Earnings tab (breakdown, platform bars, withdraw modal)
- [x] Settings tab (mode, platforms, profile, stats, notifications)
- [x] Post scheduling engine (region-based, 30-min spacing)
- [x] Session health monitoring
- [x] Background agent (polling, posting, scraping, health checks, notifications)

**Phase 5-7: Dashboards + Integration (Tasks 23-29)**
- [x] AI campaign wizard UI (4-step wizard with AI generation)
- [x] Enhanced campaign detail page (invitation stats, per-user table, ROI, edit modal)
- [x] Company dashboard improvements (clone, delete, top-up, stats page, export)
- [x] Admin review queue + platform stats + blue theme
- [x] Blue/white theme across all apps
- [x] E2E integration tests (26 tests covering full lifecycle)
- [x] Bug fix and polish pass (588 tests, 0 failures)

### Production Bugs Found & Fixed During UAT
1. **Jinja2Templates crash on Vercel** — Switched company pages to raw Jinja2 (same as admin)
2. **pgbouncer prepared statement error** — Added `statement_cache_size=0`
3. **Payout FK constraint** — Made `campaign_id` nullable for aggregate payouts
4. **bcrypt crash on Vercel Lambda** — Switched to PBKDF2-SHA256 (pure Python)
5. **Missing Campaign columns on Supabase** — Migration endpoint didn't include Task 4+5 columns
6. **Admin password reset** — `ADMIN_PASSWORD` env var was wrong on Vercel
7. **AI wizard "Session expired"** — Cookie was httpOnly, JS couldn't read it. Added server-side proxy
8. **AI wizard not generating** — `google-genai` missing from server requirements.txt
9. **AI wizard wrong args** — `run_campaign_wizard()` called with positional args instead of kwargs
10. **Draft blocked by $0 balance** — Removed balance check for drafts, only check on activation
11. **Sidecar not connected** — `withGlobalTauri` missing, 14/28 Rust commands unregistered, `onboarding_done` use-after-close bug
12. **Accept/reject/approve failing** — `accept_invitation()`, `reject_invitation()` missing from server_client.py (JUST FIXED, needs testing)

### Key Decisions (Session 18)
- **No payout multiplier** — Earnings = pure engagement metrics. Mode only affects workflow.
- **Amplifier provides API keys** — Users don't need to create Gemini keys
- **Campaign invitations** — Users accept/reject (not auto-assigned). 3-day expiry. Max 5 active.
- **AI matching is core** — Campaign brief + user profile fed to LLM for relevance scoring
- **Draft without balance** — Companies can save drafts with $0, only need balance to activate
- **Post timing = campaign region** — Not hardcoded US timezone
- **30-min minimum spacing** between posts
- **Personal brand engine is separate** — Not part of the user-facing Amplifier app
- **Tauri over Flask+pystray** — Full desktop app, not a workaround
- **Blue/white theme** — Primary #2563eb, replaces emerald green

## Core Features for Testing

### User App Core
1. Register + login
2. Connect platforms (browser login)
3. Profile scraping (followers, bio, engagement)
4. AI niche detection
5. Receive campaign invitations (AI matched)
6. Accept/reject invitations (3-day expiry, max 5)
7. Content generated per platform
8. Review + edit content per platform, approve
9. Post scheduled and executed (headless, region-based)
10. Metrics scraped and synced
11. Earnings visible (balance, per-campaign)
12. Withdraw earnings

### Company Dashboard Core
1. Register + login ✅
2. Create campaign (form with targeting) ✅
3. Campaign lifecycle (draft → active → pause) ✅
4. Campaign list with stats ✅
5. Campaign detail with per-user data ✅
6. Billing (balance, add funds) ✅
7. Edit active campaign ✅

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **Swagger**: https://server-five-omega-23.vercel.app/docs

## Test Accounts
- **Company**: `testcorp@gmail.com` / `TestPass123!`
- **User**: `testuser_e2e@gmail.com` / `TestPass123!`
- **Admin**: password `admin`

## Key Reference Files

### Tauri App
- `tauri-app/src/index.html` — Frontend (onboarding + all tabs)
- `tauri-app/src/main.js` — Frontend logic (~3000 lines)
- `tauri-app/src/styles.css` — Blue/white theme (~1500 lines)
- `tauri-app/src-tauri/src/lib.rs` — App setup, 28 commands registered
- `tauri-app/src-tauri/src/sidecar.rs` — Python sidecar manager (JSON-RPC)
- `tauri-app/src-tauri/src/commands/` — Rust command handlers
- `scripts/sidecar_main.py` — Python sidecar (34 handlers)

### Server
- `server/app/main.py` — 82 routes
- `server/app/routers/invitations.py` — Campaign invitation endpoints
- `server/app/routers/campaigns.py` — Campaign CRUD + clone/delete/export/wizard
- `server/app/routers/company_pages.py` — Company web dashboard
- `server/app/services/campaign_wizard.py` — AI wizard (Gemini)
- `server/app/services/matching.py` — AI matching (Gemini relevance scoring)
- `server/app/services/billing.py` — Earnings calculation (pure metrics)
- `server/app/services/content_screening.py` — Prohibited content detection

### New Modules
- `scripts/utils/profile_scraper.py` — 4 platform scrapers
- `scripts/utils/niche_classifier.py` — Gemini niche detection
- `scripts/utils/post_scheduler.py` — Region-based scheduling
- `scripts/utils/session_health.py` — Platform session monitoring
- `scripts/utils/content_quality.py` — Brief adherence scoring
- `scripts/background_agent.py` — Always-running automation

### Tests (588 total)
- `tests/test_schema_v2.py` (71), `tests/test_invitations.py` (43), `tests/test_billing_v2.py` (12)
- `tests/test_screening.py` (24), `tests/test_campaign_mgmt.py` (26), `tests/test_earnings_v2.py` (19)
- `tests/test_profile_scraper.py` (35), `tests/test_niche_classifier.py` (39)
- `tests/test_ai_wizard.py` (57), `tests/test_ai_matching.py` (34)
- `tests/test_scheduling.py` (41), `tests/test_session_health.py` (30)
- `tests/test_background_agent.py` (43), `tests/test_content_quality.py` (22)
- `tests/test_export.py` (10), `tests/test_e2e_integration.py` (26)

## Test Commands
```bash
# Run all tests
cd C:/Users/dassa/Work/Auto-Posting-System && python -m pytest tests/ -v

# Run Tauri app
cd tauri-app && $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH" && npm run tauri dev

# Deploy to Vercel
vercel deploy --yes --prod --cwd server

# Run v2 migration on Supabase
curl -X POST https://server-five-omega-23.vercel.app/api/admin/run-v2-migration
```

## Noted for Later (Post-MVP)
- Campaign exclusivity (competing brands)
- Influencer/company search & discovery (both sides find each other)
- Dynamic niche evolution tracking (AI monitors content shifts)
- Stripe payment integration
- Web dashboard split (separate from desktop app)
- TikTok and Instagram posting
- Auto-update mechanism for desktop app
