# Amplifier PRD

> **Implementation Note (2026-04-17):** This is the original planning PRD. The actual implementation has diverged in several areas. For current state, see `docs/PRD.md`.
>
> Key divergences from this document:
> - **Server hosting:** Vercel (not Railway). Supabase PostgreSQL (not Redis/ARQ — background jobs handled by user-side background_agent.py).
> - **AI generation:** AiManager (Gemini→Mistral→Groq Python SDK) replaces Claude CLI for campaign content. Claude CLI retained for personal brand engine only.
> - **Active platforms:** LinkedIn, Facebook, Reddit only. X disabled 2026-04-14 after account lockouts. Instagram/TikTok remain disabled.
> - **Implementation status:** 13 of 39 tasks done. Batch 1 (Money Loop) complete + verified. Batch 2 (AI Brain): AI matching + 3-tier profile scraping done, 4-phase content agent next.

## Overview

Build a two-sided marketplace where companies pay to promote products/campaigns, and users earn money by auto-posting campaign content to their 6 social media platforms using an AI-powered desktop application. The central server is a lightweight campaign marketplace. All AI generation, posting, and metric scraping happens on user devices.

Existing auto-poster codebase (Playwright posting, human emulation, image/video gen, Claude CLI content generation) is the engine that gets evolved into the campaign-aware user app.

## Tech Stack

- Server: Python FastAPI + PostgreSQL + Redis + ARQ (background jobs)
- Server hosting: Railway (MVP)
- User app: Python (evolved from existing auto-poster)
- User local DB: SQLite
- User dashboard: Flask (evolved from existing review_dashboard.py)
- Company dashboard: FastAPI + Jinja2 templates (MVP, no React)
- Browser automation: Playwright (existing)
- AI generation: Claude CLI (existing, on user device)
- Installer: PyInstaller + Inno Setup
- Payments: Stripe Connect

## Phase 1: Server Foundation

### Task: Set up FastAPI server project structure
Create the server project in a `server/` directory. Set up FastAPI app with proper project structure: app/, routers/, models/, schemas/, services/, core/ (config, security, database). Add requirements.txt with fastapi, uvicorn, sqlalchemy, asyncpg, alembic, python-jose, passlib, redis, arq. Add .env.example for database URL, Redis URL, JWT secret, Stripe keys.

### Task: Set up PostgreSQL database models with SQLAlchemy
Create all database models using SQLAlchemy ORM: Company, Campaign, User, CampaignAssignment, Post, Metric, Payout, Penalty. Use JSONB for flexible fields (assets, payout_rules, targeting, follower_counts, platforms). Set up proper foreign keys, indexes, and constraints. Include created_at/updated_at timestamps on all models.

### Task: Set up Alembic migrations
Initialize Alembic in the server project. Create the initial migration from the SQLAlchemy models. Configure alembic.ini to read database URL from environment variables. Verify migration runs cleanly against a fresh PostgreSQL database.

### Task: Implement JWT authentication system
Build auth for both users and companies. Endpoints: POST /api/auth/register (user), POST /api/auth/login (user), POST /api/auth/company/register, POST /api/auth/company/login. Use bcrypt for password hashing, JWT tokens with expiration. Create auth dependency for FastAPI routes that validates JWT and injects current user/company. Separate user and company auth flows.

### Task: Implement Campaign CRUD API for companies
Company-facing endpoints: POST /api/company/campaigns (create), GET /api/company/campaigns (list own), GET /api/company/campaigns/{id} (detail), PATCH /api/company/campaigns/{id} (update/pause/cancel). Campaign creation requires: title, brief, budget_total, payout_rules, targeting criteria, content_guidance, start_date, end_date. Validate budget against company balance. Campaign status transitions: draft → active → paused → completed → cancelled.

### Task: Implement User Profile API
User-facing endpoints: GET /api/users/me (profile), PATCH /api/users/me (update platforms, follower_counts, niche_tags, mode). Users can update their connected platforms, follower counts per platform, niche tags, and operating mode (full_auto, semi_auto, manual). Validate data types and ranges.

## Phase 2: Campaign Distribution

### Task: Implement campaign matching algorithm
Build the matching engine that scores campaigns against user profiles. Hard filters: user has required platforms, meets minimum follower counts, not suspended, campaign has budget, not already assigned. Soft scoring: niche overlap (+30 per match), trust score (+0.5 per point), historical engagement rate (+20 per % above average). Return top N campaigns sorted by match score.

### Task: Implement campaign assignment API
Endpoint: GET /api/campaigns/mine — called by user app during polling. Runs matching algorithm, creates CampaignAssignment records for new matches, returns assigned campaigns with full brief, assets, content guidance, and payout rules. Endpoint: PATCH /api/campaigns/assignments/{id} — user app updates status (content_generated, posted, skipped). Include rate limiting (max 1 poll per 5 minutes per user).

### Task: Implement post registration API
Endpoint: POST /api/posts — user app registers posted content with the server. Accepts: assignment_id, platform, post_url, content_hash, posted_at. Server validates the assignment belongs to the user. Creates Post records. Updates assignment status.

## Phase 3: User App Evolution

### Task: Add server communication layer to user app
Create a new module `scripts/utils/server_client.py` that handles all server communication: registration, login (store JWT locally), poll for campaigns, report posts, report metrics, update profile. Handle auth token refresh. Store server URL and auth token in local config. Implement retry logic with exponential backoff for failed requests.

### Task: Add SQLite local database to user app
Create `scripts/utils/local_db.py` using SQLite. Tables: local_campaign, local_post, local_metric, local_earning, settings. Sync campaigns from server responses. Track which posts and metrics have been reported to server. Store user settings (mode, poll interval, platforms enabled). Use simple ORM or raw SQL.

### Task: Adapt content generation for campaign briefs
Modify `scripts/generate.ps1` (or create a new generation script) to accept a campaign brief as input instead of using the static content-templates.md. The prompt should combine: campaign brief + content guidance + platform formatting rules + user's niche context. Output format stays the same (JSON with per-platform content). Support all content modes: AI-generated (full generation from brief), user-customized (generate draft for editing), repost (use company-provided content directly).

### Task: Implement campaign polling loop
Create a background process in the user app that polls the server every 5-15 minutes (configurable). On each poll: fetch assigned campaigns, store in local SQLite, check for new campaigns to process. For full_auto mode: immediately queue new campaigns for content generation and posting. For semi_auto/manual: mark as pending review in local dashboard.

### Task: Update Flask dashboard for campaign management
Evolve the existing review_dashboard.py to show: active campaigns with briefs and payout info, generated content for review/editing (semi-auto and manual modes), posting status per platform, earnings per campaign, total earnings balance, trust score, mode selector. Keep the existing draft review functionality for non-campaign content.

### Task: Implement campaign content posting flow
Create the orchestration logic that takes a campaign + generated content and posts it through the existing platform posting functions. For each campaign: generate content (or use provided content for repost mode) → post to all 6 enabled platforms with existing human emulation → record post URLs → report posts to server. Reuse existing post.py functions. Handle partial failures (some platforms succeed, others fail).

## Phase 4: Metrics & Billing

### Task: Implement metric scraping
Create `scripts/utils/metric_scraper.py`. After posting, schedule scraping visits at T+1h, T+6h, T+24h, T+72h. Use existing Playwright browser profiles to visit post URLs and scrape: impressions/views, likes, reposts/shares, comments, clicks (where available). Store in local SQLite. Platform-specific scraping logic for each of the 6 platforms.

### Task: Implement metric reporting API
Server endpoint: POST /api/metrics — accepts batch metric submissions from user apps. Validates post ownership. Stores Metric records with timestamps. Marks metrics as is_final at T+72h. Deduplicates (same post_id + scraped_at window). User app reports metrics after each scrape cycle.

### Task: Build billing calculation engine
Server background job (ARQ): runs periodically (hourly), calculates earnings for all posts with new final metrics. Formula: post_cost = (impressions/1000 * rate_per_1k_imp) + (likes * rate_per_like) + (reposts * rate_per_repost) + (clicks * rate_per_click) * payout_multiplier. Deduct platform cut (configurable %). Credit user earnings_balance. Deduct from campaign budget_remaining. Auto-pause campaigns when budget < threshold. Create Payout records.

### Task: Build company analytics dashboard
Server-rendered pages (Jinja2): campaign list with status and spend, campaign detail page with total reach/engagement/spend, per-user breakdown (anonymized), per-platform breakdown, daily metrics chart. Accessible via company auth. Keep it functional, not fancy — tables and basic charts.

### Task: Build user earnings API
Endpoint: GET /api/users/me/earnings — returns earnings summary (total earned, current balance, pending, per-campaign breakdown). Endpoint: GET /api/users/me/earnings/history — paginated history of payouts. User app displays this in the local dashboard.

## Phase 5: Trust & Quality

### Task: Implement trust score system
Server-side service that adjusts user trust scores based on events: post verified live at 24h (+1), above-average engagement (+2), campaign completed (+3), user customized content (+1), post deleted within 24h (-10), content flagged by platform (-15), metrics anomaly (-20), confirmed fake metrics (-50 + ban review). Trust score affects campaign matching priority. Store trust events as audit log.

### Task: Implement fraud detection background jobs
ARQ background jobs: (1) Spot-check scraping — randomly select 5% of post URLs, scrape independently, compare to user-reported metrics. Flag discrepancies > 20%. (2) Anomaly detection — flag users whose engagement/follower ratio is a statistical outlier. (3) Cross-user comparison — same campaign across many users should have proportional engagement, flag outliers. (4) Deletion monitoring — check if posts are still live at 24h and 72h.

### Task: Implement penalty system
When fraud detection or trust events trigger a penalty: create Penalty record, deduct from user earnings_balance, notify user via API (user app shows in dashboard). Penalty tiers: warning (no deduction), minor (-$X), major (-$XX + trust score hit), critical (suspension + manual review). Users can appeal via API endpoint. Admin reviews appeals.

## Phase 6: Distribution & Onboarding

### Task: Create user onboarding flow in desktop app
First-run experience: register account (email + password → server), set up platforms (run login_setup.py for each enabled platform), configure follower counts and niche tags, select operating mode (full_auto / semi_auto / manual), set poll interval. Store all config locally. Verify server connectivity.

### Task: Package user app with PyInstaller
Create PyInstaller spec file that bundles the entire user app: Python scripts, Playwright, Flask dashboard, local DB, all dependencies. Output a single directory (not single file — Playwright needs its browser binaries). Test on clean Windows 10 and 11 machines.

### Task: Create Windows installer with Inno Setup
Build an Inno Setup script that: installs the PyInstaller bundle, creates Start Menu shortcut, optionally adds to startup (for full_auto mode), creates desktop shortcut for dashboard, registers uninstaller. Include Playwright browser download as part of install or first-run.

### Task: Implement auto-update mechanism
User app checks server for new version on startup (GET /api/version). If newer version available: download installer in background, notify user, offer to install (or auto-install in full_auto mode). Server endpoint serves version info and download URL. Keep it simple — full installer replacement, not differential updates.

## Phase 7: Payments

### Task: Integrate Stripe Connect for user payouts
Set up Stripe Connect in Express mode. Users onboard to Stripe during setup (link Stripe account). Server initiates payouts via Stripe API on payout cycle (weekly/monthly). Handle payout failures gracefully. Store Stripe account IDs in User model. Company payments: companies top up balance via Stripe Checkout.

### Task: Implement payout cycle
ARQ background job: runs weekly. For each user with earnings_balance > minimum_payout threshold: create Payout record, initiate Stripe transfer, update earnings_balance. Handle partial payouts (if Stripe fails). Send payout summary to user via API. Company side: auto-recharge or manual top-up of campaign budgets.

## Admin

### Task: Build admin dashboard
Server-rendered admin pages: user list with trust scores and earnings, campaign list with budgets and status, fraud flags for review, penalty/appeal management, system metrics (active users, active campaigns, total spend, total payouts). Protected by admin auth (separate from user/company auth).

### Task: Implement admin API
Endpoints: GET /api/admin/users (list with filters), POST /api/admin/users/{id}/suspend, POST /api/admin/users/{id}/unsuspend, GET /api/admin/fraud/flags (pending fraud flags), POST /api/admin/fraud/flags/{id}/resolve (confirm or dismiss), GET /api/admin/stats (system-wide metrics).
