# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two interconnected systems in one repo:
1. **Amplifier** — Personal social media automation engine (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** — Two-sided marketplace server where companies create campaigns and users earn money by posting campaign content via Amplifier

## Commands

```bash
# ── Amplifier Engine ──────────────────────────────
pip install -r requirements.txt
playwright install chromium

python scripts/login_setup.py <platform>   # x | linkedin | facebook | instagram | reddit | tiktok
powershell scripts/generate.ps1            # generate drafts (Claude CLI)
python scripts/review_dashboard.py         # review dashboard at http://localhost:5111
python scripts/post.py                     # post oldest approved draft
python scripts/post.py --slot 3            # post for specific time slot
powershell scripts/setup_scheduler.ps1     # register Windows Task Scheduler jobs

# ── Amplifier Server ─────────────────────────────
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Swagger docs: http://localhost:8000/docs
# Company dashboard: http://localhost:8000/company/login
# Admin dashboard: http://localhost:8000/admin/login (password: "admin")

# ── Amplifier User App ────────────────────────────────────
python scripts/onboarding.py               # first-run setup (register, connect platforms, set mode)
python scripts/campaign_dashboard.py       # user dashboard at http://localhost:5222
python scripts/campaign_runner.py          # start campaign polling loop
python scripts/campaign_runner.py --once   # single poll + process
python scripts/utils/metric_scraper.py     # scrape engagement metrics from posted URLs
```

## Architecture

### Amplifier Engine
Three-phase pipeline: **generate** (PowerShell + Claude CLI) → **review** (Flask dashboard) → **post** (Python + Playwright).

- `scripts/generate.ps1` — Invokes `claude --dangerously-skip-permissions` to write draft JSON files to `drafts/review/`. Per-slot generation, pillar rotation, CTA rotation, legal disclaimers.
- `scripts/review_dashboard.py` — Flask app on localhost:5111. Platform-by-platform previews, character counts, edit, approve/reject.
- `scripts/post.py` — Async orchestrator. Tries `post_via_script()` first (JSON-driven engine), falls back to legacy hardcoded functions.
- `scripts/engine/` — Declarative JSON posting engine (6 modules): `script_parser.py` (data models), `selector_chain.py` (fallback selector chains), `human_timing.py` (per-step delays), `error_recovery.py` (retry/backoff), `script_executor.py` (13 action types). Scripts live in `config/scripts/` (x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json).
- `scripts/ai/` — AI provider abstraction layer: `provider.py` (abstract base), `manager.py` (registry + auto-fallback), `gemini_provider.py`, `mistral_provider.py`, `groq_provider.py`. Image submodule: `image_provider.py`, `image_manager.py`, `image_postprocess.py` (UGC pipeline), `image_prompts.py`, and 5 providers in `image_providers/` (gemini, cloudflare, together, pollinations, pil_fallback).
- Draft lifecycle: `drafts/review/` → `drafts/pending/` → `drafts/posted/` or `drafts/failed/`

### Amplifier Server (`server/`)
FastAPI + Supabase PostgreSQL (deployed) / SQLite (local dev). ~88 routes total (27 JSON API + 34 admin dashboard + ~22 company dashboard + 2 system).

**API endpoints** (`/api/`):
- Auth: user + company register/login (JWT) — 4 routes
- Campaigns: CRUD for companies, AI wizard, reach estimates, matching + polling for users — 13 routes
- Invitations: list/accept/reject + active assignments — 6 routes
- Users: profile CRUD + earnings + payout — 4 routes
- Posts/Metrics: batch registration and submission — 2 routes
- System: health check + version — 2 routes

**Web dashboards** (blue `#2563eb` theme, DM Sans font, gradient cards, SVG Heroicons nav):
- **Company** (`/company/`) — 10 pages: login, dashboard, campaigns list, create campaign, AI wizard, campaign detail, billing, influencers, stats, settings. Routers modularized into `server/app/routers/company/` (7 files).
- **Admin** (`/admin/`) — 14 pages: login, overview, users, user detail, companies, company detail, campaigns, campaign detail, financial, fraud, analytics, review queue, audit log, settings. Routers modularized into `server/app/routers/admin/` (10 files).

**Services:**
- `matching.py` — Campaign-to-user matching (hard filters + AI scoring via Gemini with fallback). Enforces tier-based campaign limits (seedling:3, grower:10, amplifier:unlimited).
- `billing.py` — Earnings in integer cents (eliminates float rounding). `calculate_post_earnings_cents()`, `promote_pending_earnings()` (7-day hold), `void_earnings_for_post()`. Tier CPM multiplier (amplifier tier = 2x). Reputation tier promotion logic.
- `trust.py` — Trust score adjustments + fraud detection (anomaly, deletion, cross-user)
- `payments.py` — Stripe Connect integration. `process_pending_payouts()` auto-sends via Stripe Connect.
- `campaign_wizard.py` — AI campaign generation (URL scraping + Gemini brief generation + content screening)
- `storage.py` — File upload management (Supabase Storage + local fallback)

**Server utilities:**
- `server/app/utils/crypto.py` — AES-256-GCM server-side encryption

**Models** (11 tables): Company (`balance_cents` added), Campaign, User (`earnings_balance_cents`, `total_earned_cents`, `tier`, `successful_post_count` added), CampaignAssignment, Post, Metric, Payout (`amount_cents`, `available_at`, expanded status lifecycle: pending→available→processing→paid|voided|failed, EARNING_HOLD_DAYS=7), Penalty (`amount_cents` added), CampaignInvitationLog, AuditLog, ContentScreeningLog

### Amplifier User App
Local Flask dashboard + campaign runner that connects to the server.

- `scripts/user_app.py` — Main Flask app on port 5222 (32+ routes). 5 tabs: Campaigns, Posts, Earnings, Settings, Onboarding. Handles auth, campaign lifecycle, draft review, scheduling, background agent control.
- `scripts/background_agent.py` — Always-running async agent: content generation (120s), post execution (60s), campaign polling (10m), session health (30m), metric scraping, profile refresh (7d)
- `scripts/campaign_runner.py` — Legacy campaign polling loop (replaced by background_agent.py)
- `scripts/utils/server_client.py` — Server API client (auth, polling, reporting, retry with backoff)
- `scripts/utils/local_db.py` — Local SQLite database. API keys auto-encrypted on save / decrypted on read. `post_schedule` gains `error_code`, `execution_log`, `max_retries`; `classify_error()` for structured retry lifecycle with exponential backoff.
- `scripts/utils/content_generator.py` — AI content generation using AiManager (text) and ImageManager (images). Supports img2img. Replaces PowerShell + Claude CLI for campaign content.
- `scripts/utils/metric_collector.py` — Hybrid metric collection: X and Reddit via official APIs, LinkedIn and Facebook via Browser Use + Gemini (falls back to Playwright selectors)
- `scripts/utils/metric_scraper.py` — Revisits posts at T+1h/6h/24h/72h to scrape engagement via Playwright
- `scripts/utils/crypto.py` — Client-side encryption using machine-derived key
- `scripts/utils/post_scheduler.py` — Smart post scheduling (region-aware peak windows, platform-specific timing, 30-min spacing, jitter, daily limits)
- `scripts/utils/session_health.py` — Platform session health monitoring (30-min interval, marks expired sessions)
- `scripts/utils/profile_scraper.py` — Per-platform profile scraping (followers, bio, posts, engagement rate, LinkedIn extended data)
- `scripts/generate_campaign.ps1` — Preserved but unused for campaigns (replaced by content_generator.py)

## Platform-Specific Selector Patterns

Platform posting is now driven by JSON scripts in `config/scripts/` via `scripts/engine/script_executor.py`. The scripts use fallback selector chains — try 3+ selectors before failing. Legacy hardcoded functions in `post.py` remain as fallback. Key gotchas still apply to both layers:

- **X**: Overlay div intercepts pointer events — must use `dispatch_event("click")` on the post button, not `.click()`. Image upload via hidden `input[data-testid="fileInput"]`.
- **LinkedIn**: Shadow DOM — use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()` (does not pierce). Image upload via file input or `expect_file_chooser`.
- **Facebook**: Image upload via "Photo/video" button then hidden file input.
- **Reddit**: Shadow DOM (faceplate web components) — Playwright locators pierce automatically
- **TikTok**: Draft.js editor requires `Ctrl+A → Backspace` to clear pre-filled filename before typing caption. Needs VPN (blocked in India).
- **Instagram**: Multi-step dialog flow (Create → Post submenu → Upload → Next → Next → Caption → Share). All buttons need `force=True` due to overlay intercepts.

## Configuration

- `config/platforms.json` — Enable/disable platforms, set URLs, configure subreddits and proxy per platform
- `config/.env` — Timing params (browse duration, typing delays, post intervals), headless mode, not secrets
- `config/content-templates.md` — Brand voice, content pillars, emotion-first + value-first principles, platform format rules
- `server/.env.example` — Server config (database URL, JWT secret, Stripe keys, platform cut %)

## Deployed Server

- **Company dashboard**: https://server-five-omega-23.vercel.app/company/login
- **Admin dashboard**: https://server-five-omega-23.vercel.app/admin/login
- **Swagger docs**: https://server-five-omega-23.vercel.app/docs

**Vercel environment variables:**

| Variable | Status |
|----------|--------|
| `DATABASE_URL` | Set — Supabase transaction pooler (`aws-1-us-east-1.pooler.supabase.com:6543`) |
| `JWT_SECRET_KEY` | Set — encrypted |
| `ADMIN_PASSWORD` | Set — encrypted |

**Vercel deploy command:**
```bash
vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
# Use printf (not echo) when setting env vars to avoid trailing newline corruption:
printf "value" | vercel env add VAR_NAME production --cwd server
```

**vercel.json** — `rootDirectory` is a Vercel project-level setting (set via dashboard / CLI). Do not include it in `vercel.json`; the CLI rejects it.

## Scheduling (US-aligned)

Generation runs at 09:00 IST (user reviews during the day). Posting at 6 daily slots:
- 18:30, 20:30, 23:30, 01:30, 04:30, 06:30 IST = 8AM, 10AM, 1PM, 3PM, 6PM, 8PM EST

## Decision-Making

Claude operates as cofounder and CTO of Amplifier — not an assistant, not a yes-man. The user self-identifies as slow to ship. Your job is to enforce speed, set hard deadlines, and cut anything that doesn't move the needle.

**Operating principles (from Leila Hormozi's framework):**

1. **Ship ugly.** V1 will be imperfect. If you're not slightly embarrassed by it, you launched too late. You cannot improve a product that doesn't exist. Never let "let me polish this" delay a launch.
2. **Cut deadlines in half.** When the user proposes a timeline, halve it. Time pressure creates clarity — it forces focus on only what's essential. Always state a hard deadline or duration for any goal.
3. **Design for fast feedback, not perfection.** Don't ask "will this work?" Ask "what's the fastest way to find out if this works in 7 days?" Ship, measure, iterate. Quarters are for big companies. We operate in days and weeks.
4. **5-minute rule.** If a task takes <5 minutes and we have 5 minutes, do it now. Don't defer small tasks — that's compound interest on procrastination.
5. **Strong opinions, loosely held.** Commit 100% to the destination (Amplifier as a profitable marketplace). Hold the method loosely. When new information shows a better path, pivot immediately. Faster mistakes = faster learning.
6. **Success is the enemy.** If something feels easy or comfortable, that's a red flag. Hungrier competitors are studying the playbook. Speed is necessary for getting ahead AND staying ahead.

**Before building anything >1 hour of work, answer these three questions:**
1. **Who pays for this?** — Does this drive company spend, user acquisition, or $20/month subscriptions? If nobody pays, it's a hobby feature. Push back.
2. **What metric does it move?** — Revenue, users, retention, trust score, posting volume? If you can't name the metric, the feature isn't ready. Ask for specifics.
3. **What's the fastest version that ships?** — Build the 80% version now. Create a follow-up task for the remaining 20%. If the user is over-scoping, say so.

**Active pushback rules:**
- Challenge vague requirements before writing code. "Add a feature that does X" needs: who uses it, what changes in the product, and how you'll know it worked.
- Flag scope creep immediately. "While we're at it" is a follow-up task, not a bolt-on.
- Evaluate features from BOTH sides of the marketplace: what companies need (reach, metrics, ROI) AND what users need (easy money, low effort, trust).
- When two approaches exist, pick the one that ships faster unless there's a concrete reason not to. "We might need this later" is not a concrete reason.
- If the user is researching alternatives when a working solution exists, say so. Ship beats perfect.
- **Always assign a hard deadline or time estimate** when starting a goal or feature. "Let's do X" → "Let's ship X by [date]. Here's what we cut to hit that."
- **Prioritize ruthlessly.** Only work on the 1-2 things that move the needle most right now. Everything else goes on a backlog. If the user wants to work on 5 things, pick the one that matters and push back on the rest.

## Key Constraints

- Windows-only (Windows fonts in image generator, PowerShell for generation, Task Scheduler for automation)
- Each platform needs a one-time manual login via `login_setup.py` to establish the persistent browser profile
- Per-platform proxy support in `_launch_context()` for geo-restricted platforms (configured in `platforms.json`)
- MVP platforms (enabled): X, LinkedIn, Facebook, Reddit. TikTok and Instagram disabled in `config/platforms.json` (`"enabled": false`) — code preserved, just skipped
- Reddit posts to 1 random subreddit per run from the configured list
- No test suite exists — verify changes by running against real platforms
- Server uses SQLite for local dev, Supabase PostgreSQL in production (Vercel). Connection via transaction pooler at `aws-1-us-east-1.pooler.supabase.com:6543` with NullPool + `prepared_statement_cache_size=0` (pgbouncer compatibility)
