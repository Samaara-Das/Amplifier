# Auto-Posting System — Task Context

**Last Updated**: 2026-03-18

## Current Task
- **Branch: `feat/campaign-architecture`** — New campaign platform architecture
- All 19 campaign platform tasks completed and E2E tested
- 4 bugs found and fixed during UAT testing
- Ready for user manual testing

## Project Overview
Two interconnected systems:
1. **Original Auto-Poster** (main branch) — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Campaign Platform** (feat/campaign-architecture branch) — Two-sided marketplace where companies pay users to promote campaigns via the auto-poster

## Task Progress Summary

### Original Auto-Poster (main branch — 100% complete)
- [x] Tasks 1-17: Full MVP + workflow + all 6 platforms E2E verified
- [x] All brand strategy, content pillars, scheduling, auto-engagement

### Campaign Platform (feat/campaign-architecture — 19/19 tasks complete)

**Phase 1: Server Foundation (Tasks 1-8)**
- [x] FastAPI project structure (`server/`)
- [x] PostgreSQL models (8 tables: Company, Campaign, User, Assignment, Post, Metric, Payout, Penalty)
- [x] Alembic migrations setup
- [x] JWT auth (separate user/company flows)
- [x] Campaign CRUD API for companies
- [x] User profile API
- [x] Campaign matching algorithm (hard filters + soft scoring)
- [x] Assignment + post registration APIs

**Phase 2: User App (Tasks 9-14)**
- [x] Server communication layer (`scripts/utils/server_client.py`)
- [x] SQLite local database (`scripts/utils/local_db.py`)
- [x] Campaign content generation via Claude CLI (`scripts/generate_campaign.ps1`)
- [x] Campaign polling loop + posting flow (`scripts/campaign_runner.py`)
- [x] Campaign dashboard — Flask UI (`scripts/campaign_dashboard.py`, port 5222)
- [x] Metric scraping for all 6 platforms (`scripts/utils/metric_scraper.py`)

**Phase 3: Server Services (Tasks 15-16)**
- [x] Billing engine + company analytics dashboard
- [x] Trust score system + fraud detection + penalties

**Phase 4: Distribution & Payments (Tasks 17-19)**
- [x] PyInstaller spec + Inno Setup installer
- [x] Auto-update + user onboarding flow
- [x] Stripe Connect integration (user payouts + company top-ups)

## Session History

### Sessions 1-8 (2026-03-07 to 2026-03-18) — Original Auto-Poster
- Built entire auto-posting system from scratch through Task 17
- All 6 platforms E2E tested, brand strategy, scheduling, auto-engagement
- See previous context for full session-by-session details

### Session 9 (2026-03-18) — Campaign Platform Architecture & Build

**Architecture Discussion:**
- User proposed: companies create campaigns, users earn by auto-posting campaign content
- Key decision: **user-side compute** — AI generation, posting, and scraping all happen on user's device
- Server is lightweight marketplace: campaign distribution, matching, billing, analytics
- Pull-based communication (user app polls server every 5-15 min)
- Social media credentials never leave user's device

**Server Built (27 API endpoints):**
- Auth: register/login for users and companies (JWT)
- Campaigns: CRUD for companies, matching + polling for users
- Posts/Metrics: batch registration and submission
- Admin: user management, system stats
- Company dashboard: HTML analytics with per-campaign breakdowns
- Version endpoint for auto-updates

**User App Built (7 new files):**
- `server_client.py` — Auth, polling, reporting with exponential backoff retry
- `local_db.py` — SQLite for campaigns, posts, metrics, earnings (5 tables)
- `generate_campaign.ps1` — Claude CLI content gen from campaign briefs
- `campaign_runner.py` — Main loop: poll → generate → post → report (supports full_auto/semi_auto/manual)
- `campaign_dashboard.py` — Flask UI with campaigns, earnings, trust score, settings tabs
- `metric_scraper.py` — Revisit posts at T+1h/6h/24h/72h, scrape engagement per platform
- `onboarding.py` — First-run: register, connect platforms, set niches/followers, choose mode

**E2E Testing via Chrome DevTools MCP (21 tests, all pass):**

API Tests:
1. Company register → 200
2. User register → 200
3. User profile update → 200
4. Campaign creation (budget validation) → 200
5. Campaign activation → 200
6. Campaign matching + polling → 200, correct match
7. Assignment status update → 200
8. Post registration (3 posts) → 200
9. Metric submission (3 metrics) → 200
10. Billing cycle → $31.20 earned across 3 posts
11. User earnings → $31.20
12. Admin stats → correct
13. Version endpoint → 0.1.0

Edge Cases:
- User token on company endpoint → 403
- Company token on user endpoint → 403
- Invalid status transition → 400
- Post to invalid assignment → 0 created
- Duplicate registration → 400
- Suspended user access → 403
- Unsuspend then access → 200
- Wrong password → 401

Trust System:
- campaign_completed: +3 (50→53)
- above_avg_engagement: +2 (53→55)
- post_deleted_24h: -10 + penalty (55→45)

**4 Bugs Found & Fixed:**
1. **passlib bcrypt crash on Python 3.14** — `ValueError: password cannot be longer than 72 bytes`. Replaced `passlib.CryptContext` with direct `bcrypt.hashpw/checkpw` in `server/app/core/security.py`
2. **Campaign matching returned duplicates** — New assignments were created then re-fetched by the "existing assignments" query. Fixed by tracking `newly_created_ids` and excluding them in `server/app/services/matching.py`
3. **Billing only processed 1 of N posts per campaign** — Dedup was per (user_id, campaign_id) which blocked all posts after the first. Changed to per `metric_id` tracking in `server/app/services/billing.py`
4. **Dashboard tab switching broken** — `event.target` on text node has no `classList`. Fixed with `event.target.closest('.nav-tab')` in `scripts/campaign_dashboard.py`

**Additional: SQLite dev mode** — Server models switched from PostgreSQL-specific JSONB/ARRAY to portable JSON type. Added `init_tables()` for auto table creation with SQLite. StaticPool for async SQLite compatibility.

## Important Decisions Made

### Campaign Platform Architecture
- **User-side compute** — AI generation, browser automation, metric scraping all on user device
- **Pull-based polling** — User app polls server every 5-15 min (no websockets at 100K+ scale)
- **Credentials never leave device** — Server never touches social media passwords/cookies
- **Content modes**: Full Auto (1.5x), Semi-Auto (2.0x), Manual (2.0x), Repost (1.0x)
- **Billing**: pay per impression/engagement, 20% platform cut, auto-pause at low budget
- **Trust score**: 0-100, starts 50, adjusts on events, affects campaign priority
- **Fraud detection**: spot-check 5% of post URLs, anomaly detection, deletion monitoring
- **Tech stack**: FastAPI + PostgreSQL (prod) / SQLite (dev) + Redis + ARQ for server
- **Distribution**: PyInstaller + Inno Setup Windows installer
- **Payments**: Stripe Connect Express for user payouts

### Original System Decisions
- ALL 6 platforms enabled, auto-engagement during browse_feed, no commenting (manual only)
- Content voice: "I learnt this, maybe you can try this too" — never claiming trading experience
- CTA rotation: month 1 = 100% value, month 2+ = 80/15/5 split

## Key Reference Files

### Campaign Platform (new)
- `docs/campaign-platform-architecture.md` — Full system design document
- `.taskmaster/docs/campaign-platform-prd.md` — PRD for task breakdown
- `server/` — FastAPI server (27 endpoints, 8 models, matching, billing, trust, analytics)
- `server/app/main.py` — Server entry point with lifespan + SQLite auto-init
- `server/app/services/matching.py` — Campaign matching algorithm
- `server/app/services/billing.py` — Earnings calculation engine
- `server/app/services/trust.py` — Trust score + fraud detection
- `server/app/services/payments.py` — Stripe Connect integration
- `server/app/routers/company_dashboard.py` — Company analytics HTML dashboard
- `scripts/campaign_runner.py` — Main campaign loop (poll → generate → post → report)
- `scripts/campaign_dashboard.py` — User campaign dashboard (Flask, port 5222)
- `scripts/onboarding.py` — First-run user setup
- `scripts/generate_campaign.ps1` — Campaign content generator (Claude CLI)
- `scripts/utils/server_client.py` — Server API client with retry
- `scripts/utils/local_db.py` — Local SQLite database
- `scripts/utils/metric_scraper.py` — Post engagement scraping
- `scripts/app_entry.py` — Packaged app entry point
- `campaign_poster.spec` — PyInstaller build spec
- `installer.iss` — Inno Setup Windows installer

### Original Auto-Poster
- `scripts/post.py` — Main poster + 6 platform functions + slot scheduling
- `scripts/generate.ps1` — Content generator (pillar rotation, CTA, legal disclaimers)
- `scripts/review_dashboard.py` — Draft review dashboard (port 5111)
- `scripts/utils/draft_manager.py` — Draft lifecycle + slot filtering
- `scripts/utils/human_behavior.py` — Anti-detection + auto-engagement
- `config/platforms.json` — Platform config, subreddits, proxy
- `config/content-templates.md` — Brand voice, content pillars

## Test Commands
```bash
# === Campaign Platform ===
# Start server (from server/ directory)
cd server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Swagger docs: http://localhost:8000/docs

# Start user campaign dashboard
python scripts/campaign_dashboard.py  # http://localhost:5222

# Run onboarding
python scripts/onboarding.py

# Run campaign runner (once or loop)
python scripts/campaign_runner.py --once
python scripts/campaign_runner.py

# Run metric scraping
python scripts/utils/metric_scraper.py

# === Original Auto-Poster ===
python scripts/post.py
python scripts/post.py --slot 3
powershell -File scripts/generate.ps1
python scripts/review_dashboard.py  # http://localhost:5111
```
