# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two interconnected systems in one repo:
1. **Auto-Poster** — Personal social media automation engine (6 platforms, Playwright, Claude CLI)
2. **Campaign Platform** — Two-sided marketplace server where companies create campaigns and users earn money by posting campaign content via the auto-poster

## Commands

```bash
# ── Auto-Poster (original) ──────────────────────────────
pip install -r requirements.txt
playwright install chromium

python scripts/login_setup.py <platform>   # x | linkedin | facebook | instagram | reddit | tiktok
powershell scripts/generate.ps1            # generate drafts (Claude CLI)
python scripts/review_dashboard.py         # review dashboard at http://localhost:5111
python scripts/post.py                     # post oldest approved draft
python scripts/post.py --slot 3            # post for specific time slot
powershell scripts/setup_scheduler.ps1     # register Windows Task Scheduler jobs

# ── Campaign Platform Server ─────────────────────────────
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Swagger docs: http://localhost:8000/docs
# Company dashboard: http://localhost:8000/company/login
# Admin dashboard: http://localhost:8000/admin/login (password: "admin")

# ── Campaign User App ────────────────────────────────────
python scripts/onboarding.py               # first-run setup (register, connect platforms, set mode)
python scripts/campaign_dashboard.py       # user dashboard at http://localhost:5222
python scripts/campaign_runner.py          # start campaign polling loop
python scripts/campaign_runner.py --once   # single poll + process
python scripts/utils/metric_scraper.py     # scrape engagement metrics from posted URLs
```

## Architecture

### Auto-Poster Engine
Three-phase pipeline: **generate** (PowerShell + Claude CLI) → **review** (Flask dashboard) → **post** (Python + Playwright).

- `scripts/generate.ps1` — Invokes `claude --dangerously-skip-permissions` to write draft JSON files to `drafts/review/`. Per-slot generation, pillar rotation, CTA rotation, legal disclaimers.
- `scripts/review_dashboard.py` — Flask app on localhost:5111. Platform-by-platform previews, character counts, edit, approve/reject.
- `scripts/post.py` — Async orchestrator. Picks pending draft, posts via Playwright to enabled platforms with human behavior emulation.
- Draft lifecycle: `drafts/review/` → `drafts/pending/` → `drafts/posted/` or `drafts/failed/`

### Campaign Platform Server (`server/`)
FastAPI + SQLite (dev) / PostgreSQL (prod). 52 API routes total.

**API endpoints** (`/api/`):
- Auth: user + company register/login (JWT)
- Campaigns: CRUD for companies, matching + polling for users
- Posts/Metrics: batch registration and submission
- Admin: user management, system stats
- Version: auto-update endpoint

**Web dashboards:**
- **Company** (`/company/`) — 6 pages: login, campaigns list, create campaign, campaign detail, billing, settings
- **Admin** (`/admin/`) — 6 pages: overview, users, campaigns, fraud detection, payouts, login

**Services:**
- `matching.py` — Campaign-to-user matching (hard filters + soft scoring)
- `billing.py` — Earnings calculation from metrics + payout rules
- `trust.py` — Trust score adjustments + fraud detection (anomaly, deletion, cross-user)
- `payments.py` — Stripe Connect integration (user payouts, company top-ups)
- `background_jobs.py` — ARQ worker (billing every 6h, trust checks 2x/day)

**Models** (8 tables): Company, Campaign, User, CampaignAssignment, Post, Metric, Payout, Penalty

### Campaign User App
Local Flask dashboard + campaign runner that connects to the server.

- `scripts/campaign_dashboard.py` — Flask on port 5222. 5 tabs: Campaigns, Posts, Earnings, Settings, Onboarding
- `scripts/campaign_runner.py` — Polls server for campaigns, generates content via Claude CLI, posts via existing Playwright engine, reports metrics
- `scripts/utils/server_client.py` — Server API client (auth, polling, reporting, retry with backoff)
- `scripts/utils/local_db.py` — Local SQLite database for offline campaign/post/metric tracking
- `scripts/utils/metric_scraper.py` — Revisits posts at T+1h/6h/24h/72h to scrape engagement
- `scripts/generate_campaign.ps1` — Content generation from campaign briefs via Claude CLI

## Platform-Specific Selector Patterns

Each platform function in `post.py` has selector constants at the top. Key gotchas:

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

## Scheduling (US-aligned)

Generation runs at 09:00 IST (user reviews during the day). Posting at 6 daily slots:
- 18:30, 20:30, 23:30, 01:30, 04:30, 06:30 IST = 8AM, 10AM, 1PM, 3PM, 6PM, 8PM EST

## Key Constraints

- Windows-only (Windows fonts in image generator, PowerShell for generation, Task Scheduler for automation)
- Each platform needs a one-time manual login via `login_setup.py` to establish the persistent browser profile
- Per-platform proxy support in `_launch_context()` for geo-restricted platforms (configured in `platforms.json`)
- All 6 platforms enabled: X, LinkedIn, Facebook, Instagram, Reddit, TikTok
- Reddit posts to 1 random subreddit per run from the configured list
- No test suite exists — verify changes by running against real platforms
- Server uses SQLite for dev/testing, PostgreSQL for production
