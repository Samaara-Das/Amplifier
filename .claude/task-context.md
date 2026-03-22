# Amplifier — Task Context

**Last Updated**: 2026-03-22

## Current Task
- **Branch: `feat/campaign-architecture`** — Campaign platform fully built, renamed, and deployed
- All tasks complete: 19 core + 17 dashboard pages + rename + Vercel deploy
- No pending tasks on this branch

## Project Overview
Two interconnected systems:
1. **Amplifier Engine** (main branch) — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** (feat/campaign-architecture) — Two-sided marketplace: companies create campaigns, users earn by posting via Amplifier

## Task Progress Summary

### Amplifier Engine (main branch — 100% complete)
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

### Completed — Final Tasks
- [x] **#23**: Renamed entire project to "Amplifier" (35 files, GitHub repo, all branding)
- [x] **#25**: Deployed to Vercel — live at https://server-five-omega-23.vercel.app

### Post-MVP Tasks
- [ ] 31: Migrate social media posting from raw Playwright to AI-powered Browser Use + free Gemini API. Replace 500+ lines of hardcoded CSS selectors in post.py with self-healing AI agent-based posting. Migrate one platform at a time. Keep current Playwright as fallback during transition.
- [ ] 32: Add website-to-API tool (Firecrawl/Apify) as insurance — if any free AI API gets shut down or goes paid, use web scraping to still access the service through its web interface. Keeps the content generation chain resilient.
- [ ] 33: Expand free API fallback chain — add Cerebras, SambaNova, OpenRouter, GitHub Models, Cohere for text; AI Horde, Freepik Mystic, Leonardo AI for images.
- [ ] 34: LinkedIn/Facebook official API migration for metric collection (when developer app approvals come through).
- [ ] 35: Write tests — ~50 focused pytest tests covering: (1) billing calculation + earnings + platform cut, (2) API contract tests for all 47 routes (200/401/422), (3) matching algorithm (region + categories + followers), (4) content generation fallback chain logic. Use httpx.AsyncClient, SQLite in-memory fixtures, mock only external APIs. Do AFTER MVP ships, BEFORE scaling to >5 users.
- [ ] 36: Consider adding a campaign marketplace/browse view — let users discover and opt into campaigns beyond what the matching algorithm pushes to them. Currently server-driven; this would add user-driven discovery.
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
- Built 17 web pages using 3 parallel agents (company 6, admin 6, user 5)
- Shared base template with consistent dark theme, sidebar nav
- E2E tested all 17 pages via Chrome DevTools — 0 bugs found
- Total: 52 API routes, 17 web pages, 3 dashboards

### Session 11 (2026-03-18 to 2026-03-21) — Rename to Amplifier & Vercel Deploy
- **Rename** (Task #23): Renamed from "Auto-Posting-System" / "Campaign Platform" to "Amplifier"
  - 35 files renamed using 3 parallel agents (server, scripts, docs)
  - GitHub repo renamed: `Samaara-Das/Auto-Posting-System` → `Samaara-Das/Amplifier`
  - Git remote updated to new URL
  - Branding: "Amplifier for Business" (company), "Amplifier Admin" (admin), "Amplifier" (user app)
  - Spec file renamed: `campaign_poster.spec` → `amplifier.spec`
  - DB name: `campaign_platform.db` → `amplifier.db`
  - Local folder rename still pending (user will do manually: `ren "Auto-Posting-System" "Amplifier"`)

- **Vercel Deploy** (Task #25): Deployed server to Vercel autonomously
  - Created `vercel.json` at repo root with `rootDirectory: server`
  - Created `server/api/index.py` entry point for Vercel's @vercel/python
  - Fixed template path in company_pages.py (use `__file__`-relative instead of relative)
  - SQLite uses `/tmp/` on Vercel (ephemeral — for demo/testing)
  - Added `aiosqlite` to requirements, removed test-only deps
  - Auto-init tables on Vercel startup via lifespan event
  - Deployed via `vercel deploy --yes --prod`
  - **Live URL**: https://server-five-omega-23.vercel.app
  - Verified: health, version, Swagger docs, company login, admin login, registration, admin stats — all working
  - Note: SQLite on Vercel resets between cold starts. For production, set `DATABASE_URL` env var to PostgreSQL (Neon/Supabase)

## Important Decisions Made
- **User-side compute** — AI generation, posting, scraping on user device
- **Pull-based polling** — every 5-15 min, no websockets
- **Credentials never leave device** — server never touches social media passwords
- **Content modes**: Full Auto (1.5x), Semi-Auto (2.0x), Manual (2.0x), Repost (1.0x)
- **Billing**: pay per impression/engagement, 20% platform cut, per-metric dedup
- **Trust**: 0-100 score, affects campaign priority
- **Tech stack**: FastAPI + SQLite (dev/Vercel) / PostgreSQL (prod) + Redis + ARQ
- **Dashboards**: Jinja2 templates (server), inline HTML (Flask user app), shared dark theme
- **Admin auth**: simple password from env var (default "admin"), company auth via JWT cookies
- **Vercel deployment**: rootDirectory=server, @vercel/python, SQLite in /tmp/, auto-init tables
- **Deploy autonomously**: user wants Vercel deployment done without intervention (feedback memory saved)

## Key Reference Files

### Server
- `server/app/main.py` — Entry point (52 routes, lifespan, SQLite auto-init)
- `server/app/routers/company_pages.py` — Company dashboard (6 pages)
- `server/app/routers/admin_pages.py` — Admin dashboard (6 pages)
- `server/app/templates/base.html` — Shared Jinja2 base template
- `server/app/services/{matching,billing,trust,payments}.py` — Business logic
- `server/api/index.py` — Vercel serverless entry point
- `vercel.json` — Vercel deployment config (at repo root)

### User App
- `scripts/campaign_dashboard.py` — User dashboard (5 tabs, port 5222)
- `scripts/campaign_runner.py` — Campaign loop (poll → generate → post → report)
- `scripts/utils/{server_client,local_db,metric_scraper}.py` — Supporting modules

### Distribution
- `amplifier.spec` — PyInstaller build spec
- `installer.iss` — Inno Setup Windows installer

### Docs
- `docs/campaign-platform-architecture.md` — Full system design
- `.taskmaster/docs/campaign-platform-prd.md` — PRD for task breakdown

## Deployed URLs
- **Swagger docs**: https://server-five-omega-23.vercel.app/docs
- **Company dashboard**: https://server-five-omega-23.vercel.app/company/login
- **Admin dashboard**: https://server-five-omega-23.vercel.app/admin/login (pw: `admin`)
- **Health check**: https://server-five-omega-23.vercel.app/health
- **API base**: https://server-five-omega-23.vercel.app/api/

## Test Commands
```bash
# === Deployed Server ===
# Company: https://server-five-omega-23.vercel.app/company/login (register new account)
# Admin: https://server-five-omega-23.vercel.app/admin/login (pw: admin)
# Swagger: https://server-five-omega-23.vercel.app/docs

# === Local Development ===
# Amplifier Server
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# User App Dashboard
python scripts/campaign_dashboard.py  # http://localhost:5222

# Campaign Runner
python scripts/campaign_runner.py --once
python scripts/campaign_runner.py

# Original Amplifier Engine
python scripts/post.py --slot 3
powershell -File scripts/generate.ps1
python scripts/review_dashboard.py  # http://localhost:5111

# Rename local folder (user pending):
# ren "C:\Users\dassa\Work\Auto-Posting-System" "Amplifier"
```

### Session 12 (2026-03-22) — MVP Build (Ralph autonomous agent)
Ralph script executed 6 iterations, completing Phases 1-7 of the MVP spec. Phase 8 (Integration Testing) not completed.

- **Phase 1** (commit 7200492): Critical Fixes — added httpx, google-genai, mistralai, groq, praw, browser-use, langchain-google-genai to requirements.txt. Made server URL configurable in server_client.py (defaults to Vercel URL). Disabled TikTok + Instagram in platforms.json. Added API key fields to config/.env.
- **Phase 2** (commit 81e3043): PostgreSQL Support — updated database.py with SSL support for Supabase/cloud PostgreSQL (ssl context, connection pooling, pool_pre_ping). Updated main.py to always init tables (idempotent for both SQLite and PostgreSQL). Updated server/.env.example with Supabase connection string format.
- **Phase 3** (commit 5fbc51d): Content Generation via Free AI APIs — new `scripts/utils/content_generator.py` with fallback chain (Gemini → Mistral → Groq). Updated campaign_runner.py to use ContentGenerator instead of PowerShell.
- **Phase 4** (commit c54cdee): Region + Category Matching — added audience_region to User model, updated matching algorithm with region filter, updated company dashboard campaign creation form with targeting fields, updated onboarding + user profile endpoint.
- **Phase 5** (commit 11cfa34): Hybrid Metric Collection — new `scripts/utils/metric_collector.py` with X API + Reddit API + Browser Use for LinkedIn/Facebook. Updated metric_scraper.py to use MetricCollector.
- **Phase 6** (commit b38e180): Dashboard Polish — user dashboard UI improvements (cards, spacing, typography, status badges), post editing flow (edit text/hashtags/image per platform before approving), company dashboard influencer visibility (assigned users, handles, engagement stats per user).
- **Phase 7** (commit f23293b): Installer Fixes — fixed Playwright install command in installer.iss, updated PyInstaller spec with new hidden imports, improved installer (icon, don't delete user data on uninstall).

- **Phase 8** (session 13): Integration Testing via Chrome DevTools — full E2E flow verified on deployed server.

**MVP spec finalized**: `mvp.md` at repo root is the source of truth for MVP scope and implementation plan.

### Session 13 (2026-03-22) — Integration Testing (Phase 8)
Tested the full MVP cycle on the deployed Vercel server via Chrome DevTools MCP.

**What was tested (all PASSED):**
- Company registration + login (web dashboard)
- Company billing top-up ($500 added)
- Campaign creation with title, brief, content guidance, budget, dates, payout rules, targeting (US region, finance+tech categories, X platform required)
- Campaign activation (draft → active)
- User registration via API
- User profile update (platforms with `connected: true`, follower_counts, niche_tags, audience_region)
- Campaign matching — user polled `/api/campaigns/mine`, got matched with 2.0x multiplier
- Post registration — 2 posts (X + LinkedIn) registered via `/api/posts`
- Metric submission — impressions, likes, reposts, comments, clicks via `/api/metrics`
- Billing cycle — triggered via admin, calculated $49.76 user earnings from 12,700 impressions + 249 engagement
- User earnings API — confirmed $49.76 total_earned
- Company campaign detail — shows 12,700 impressions, 249 engagement, $62.20 spent, 62.2% budget used
- Platform breakdown table — per-platform posts, impressions, likes, reposts, comments, clicks
- Creators section — shows creator email, platform handles, connected platforms, assignment status, clickable post URLs, per-user impressions + engagement
- Admin dashboard — overview (1 user, 1 campaign, 2 posts), users page (trust score, mode, platforms, earnings), payouts page (billing cycle results)

**Bugs found and fixed:**
1. **vercel.json rootDirectory removed** — Ralph agent accidentally deleted `rootDirectory: "server"` which would break deployment. Reverted. (commit d4150e0)
2. **content_generator.py PIL import** — `generate_branded_image` → `generate_landscape_image` fix. (commit d4150e0)
3. **Stale Vercel deployment** — Phase 4-7 template changes (Target Regions, Categories, Creators section) weren't deployed. Redeployed.

**Issues found (not fixed — need user action):**
1. **Company login fails after registration** — registering works and redirects to dashboard, but logging in with the same credentials fails ("Invalid email or password"). Password hashing or verification issue. Needs investigation.
2. **Database still using SQLite in /tmp/** — data is lost on every Vercel redeploy/cold start. The `DATABASE_URL` env var may not be set on Vercel, or the Supabase connection isn't working. User said Supabase is set up but data doesn't persist.
3. **Admin password changed** — `ADMIN_PASSWORD` env var is set on Vercel (encrypted) but the value is unknown. Default "admin" no longer works.
4. **Niche Tags field redundant** — campaign form has both "Niche Tags" (free text, old) and "Categories" (checkboxes, new from Phase 4). Should remove the old Niche Tags field to avoid confusion.
