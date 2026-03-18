# Amplifier — Task Context

**Last Updated**: 2026-03-18

## Current Task
- **Branch: `feat/campaign-architecture`** — Campaign platform fully built
- All 19 core tasks + 17 dashboard pages completed and E2E tested
- Next: Rename to "Amplifier" (task #23), Deploy to Vercel (task #25)

## Project Overview
Two interconnected systems:
1. **Amplifier** (main branch) — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** (feat/campaign-architecture) — Two-sided marketplace: companies create campaigns, users earn by posting via Amplifier

## Task Progress Summary

### Original Amplifier (main branch — 100% complete)
- [x] Tasks 1-17: Full MVP + workflow + all 6 platforms E2E verified
- [x] Brand strategy, content pillars, scheduling, auto-engagement

### Amplifier Server — Core (19/19 tasks complete)
- [x] Phase 1 (Tasks 1-8): Server foundation — FastAPI, 8 models, JWT auth, campaign CRUD, matching, APIs
- [x] Phase 2 (Tasks 9-14): User app — server client, local DB, campaign generation, polling/posting, dashboard, metrics
- [x] Phase 3 (Tasks 15-16): Billing engine, trust/fraud system
- [x] Phase 4 (Tasks 17-19): PyInstaller/Inno Setup, onboarding, Stripe Connect

### Amplifier Server — Dashboards (17/17 pages complete)
- [x] Task #20: Company Dashboard (6 pages) — login, campaigns, create, detail, billing, settings
- [x] Task #21: Admin Dashboard (6 pages) — overview, users, campaigns, fraud, payouts, login
- [x] Task #22: User App Dashboard (5 tabs) — campaigns, posts, earnings, settings, onboarding
- [x] Task #24: E2E tested all 17 pages via Chrome DevTools — 0 bugs found

### Pending
- [ ] **#23**: Rename project to "Amplifier" — ask user before proceeding
- [ ] **#25**: Host campaign server on Vercel

### Original System — Pending (from main branch)
- [ ] 18: Test Run, 19: Account Warmup, 20: Profile Revamps, 21: LinkedIn "I'm Back" Post
- [ ] 22-30: AI Video, Newsletters, Facebook Groups, TradingView, Analytics, A/B Testing, Email List, Competitor Analysis

## Session History

### Sessions 1-8 (2026-03-07 to 2026-03-18) — Original Amplifier
- Built entire system, 6 platforms E2E tested, brand strategy, Task 17 workflow

### Session 9 (2026-03-18) — Amplifier Server Architecture & Build
- Designed two-sided marketplace architecture (user-side compute, pull-based)
- Built 19 tasks: server (52 routes, 8 models), user app (7 new files), distribution
- E2E tested via Chrome DevTools: 21 API tests pass, 8 edge cases pass, trust system verified
- Fixed 4 bugs: passlib crash, matching duplicates, billing dedup, tab switching

### Session 10 (2026-03-18) — Dashboard Pages & E2E Testing
- Built 17 web pages using 3 parallel agents:
  - **Company dashboard** (Jinja2): login/register, campaigns list, create campaign form (brief/budget/targeting/dates), campaign detail (stats/budget bar/platform breakdown/actions), billing (top-up/allocations), settings
  - **Admin dashboard** (Jinja2): login, system overview (stats/activity), user management (trust bars/suspend), all campaigns, fraud detection (anomalies/deletions/penalties + Run Check), payouts (Run Billing Cycle/Run Payout Cycle)
  - **User app dashboard** (Flask): 5 tabs — campaigns (status strip/approve/skip), posts (platform filter/metrics), earnings (4 cards/per-campaign/per-platform), settings (mode/poll/platform connections), onboarding (4-step wizard)
- Shared base template with consistent dark theme, sidebar nav, responsive layout
- E2E tested all 17 pages: company register → create campaign → activate → admin billing cycle → payouts. 0 bugs found.
- Total: 52 API routes, 17 web pages, 3 dashboards

## Important Decisions Made
- **User-side compute** — AI generation, posting, scraping on user device
- **Pull-based polling** — every 5-15 min, no websockets
- **Credentials never leave device** — server never touches social media passwords
- **Content modes**: Full Auto (1.5x), Semi-Auto (2.0x), Manual (2.0x), Repost (1.0x)
- **Billing**: pay per impression/engagement, 20% platform cut, per-metric dedup
- **Trust**: 0-100 score, affects campaign priority
- **Tech stack**: FastAPI + SQLite (dev) / PostgreSQL (prod) + Redis + ARQ
- **Dashboards**: Jinja2 templates (server), inline HTML (Flask user app), shared dark theme
- **Admin auth**: simple password from env var, company auth via JWT cookies

## Key Reference Files

### Server
- `server/app/main.py` — Entry point (52 routes, lifespan, SQLite auto-init)
- `server/app/routers/company_pages.py` — Company dashboard (6 pages)
- `server/app/routers/admin_pages.py` — Admin dashboard (6 pages)
- `server/app/templates/base.html` — Shared Jinja2 base template
- `server/app/services/{matching,billing,trust,payments}.py` — Business logic

### User App
- `scripts/campaign_dashboard.py` — User dashboard (5 tabs, port 5222)
- `scripts/campaign_runner.py` — Campaign loop (poll → generate → post → report)
- `scripts/utils/{server_client,local_db,metric_scraper}.py` — Supporting modules

### Docs
- `docs/campaign-platform-architecture.md` — Full system design
- `.taskmaster/docs/campaign-platform-prd.md` — PRD for task breakdown

## Test Commands
```bash
# Amplifier Server
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# → Swagger: http://localhost:8000/docs
# → Company: http://localhost:8000/company/login
# → Admin: http://localhost:8000/admin/login (pw: admin)

# User App Dashboard
python scripts/campaign_dashboard.py  # http://localhost:5222

# Campaign Runner
python scripts/campaign_runner.py --once
python scripts/campaign_runner.py

# Original Amplifier
python scripts/post.py --slot 3
powershell -File scripts/generate.ps1
python scripts/review_dashboard.py  # http://localhost:5111
```
