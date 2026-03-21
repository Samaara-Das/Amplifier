# Amplifier

Two systems in one repo: a **personal social media automation engine** that generates content via Claude CLI and posts to 6 platforms using Playwright, and a **two-sided marketplace server** where companies create campaigns and users earn money by posting campaign content.

## Architecture

```
+------------------+       +------------------+       +------------------+
|   Amplifier      |       |   Amplifier      |       |   Amplifier      |
|   Server         |<----->|   User App       |------>|   Engine         |
|                  |       |                  |       |                  |
| FastAPI + SQLite |       | Flask dashboard  |       | Playwright       |
| Company dashboard|       | Campaign runner  |       | Claude CLI       |
| Admin dashboard  |       | Local SQLite     |       | Human emulation  |
| Matching engine  |       | Metric scraper   |       | Image/video gen  |
+------------------+       +------------------+       +------------------+
     Vercel                   User's desktop             User's desktop
```

**Key design principle:** User-side compute. All AI generation, browser automation, and credential handling happen on the user's device. The server never sees passwords or runs browsers.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Server | Python, FastAPI, SQLAlchemy, SQLite/PostgreSQL, ARQ, Jinja2 |
| User App | Python, Flask, Playwright, Claude CLI, httpx, SQLite |
| Distribution | PyInstaller, Inno Setup |
| Deployment | Vercel (server), Windows installer (user app) |

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.11+
- Claude Code CLI (installed and authenticated)
- PowerShell 5.1+ (Windows default)

### Server

```bash
cd server
pip install -r requirements.txt
cp .env.example .env  # then configure
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Swagger docs: http://localhost:8000/docs
- Company dashboard: http://localhost:8000/company/login
- Admin dashboard: http://localhost:8000/admin/login (password: `admin`)

### User App (Campaign Mode)

```bash
pip install -r requirements.txt
playwright install chromium
python scripts/onboarding.py               # first-time setup
python scripts/campaign_dashboard.py        # dashboard at localhost:5222
python scripts/campaign_runner.py           # start polling loop
```

### Personal Brand Engine

```bash
python scripts/login_setup.py x            # one-time login per platform
python scripts/login_setup.py linkedin
python scripts/login_setup.py facebook
python scripts/login_setup.py instagram
python scripts/login_setup.py reddit
python scripts/login_setup.py tiktok

powershell scripts/generate.ps1            # generate drafts via Claude CLI
python scripts/review_dashboard.py         # review at localhost:5111
python scripts/post.py                     # post oldest approved draft
python scripts/post.py --slot 3            # post for specific time slot
powershell scripts/setup_scheduler.ps1     # set up Windows Task Scheduler
```

## Project Structure

```
config/                  Configuration (.env, platforms.json, content-templates.md)
docs/                    Documentation (architecture, API ref, schema, flows, design)
drafts/                  Draft lifecycle folders (review/, pending/, posted/, failed/)
profiles/                Persistent browser sessions per platform (gitignored)
scripts/                 Main scripts
  post.py                  Posting engine (6 platforms, human emulation)
  generate.ps1             Content generation (Claude CLI, pillar rotation)
  review_dashboard.py      Draft review dashboard (Flask, port 5111)
  campaign_runner.py       Campaign polling loop (poll → generate → post → report)
  campaign_dashboard.py    User campaign dashboard (Flask, port 5222)
  onboarding.py            First-time user setup
  login_setup.py           One-time browser login helper
  app_entry.py             Packaged app entry point
  generate_campaign.ps1    Campaign content generation
  setup_scheduler.ps1      Windows Task Scheduler setup
  utils/                   Shared modules
    draft_manager.py         Draft lifecycle management
    human_behavior.py        Anti-detection (typing, scrolling, engagement)
    image_generator.py       Branded image/video generation
    server_client.py         Server API client with retry
    local_db.py              Local SQLite database
    metric_scraper.py        Post engagement scraping
server/                  Amplifier Server (FastAPI)
  app/
    main.py                FastAPI entry point, route mounting
    core/                  Config, database, security
    models/                8 SQLAlchemy models
    routers/               API routes + web dashboard routes
    schemas/               Pydantic request/response schemas
    services/              Business logic (matching, billing, trust, payments)
    templates/             Jinja2 templates (admin + company dashboards)
logs/                    Log files (gitignored)
data/                    Local SQLite database (gitignored)
```

## Supported Platforms

| Platform | Engine | Campaign Mode | Notes |
|----------|--------|---------------|-------|
| X (Twitter) | Yes | Yes | `dispatch_event("click")` for overlay workaround |
| LinkedIn | Yes | Yes | Shadow DOM — use `locator()` not `wait_for_selector()` |
| Facebook | Yes | Yes | Image upload via "Photo/video" button |
| Instagram | Yes | Yes | Multi-step dialog, `force=True` for overlays |
| Reddit | Yes | Yes | Posts to random subreddit from configured list |
| TikTok | Yes | Yes | VPN required in some regions, Draft.js caption clearing |

## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Developer reference — commands, architecture, platform gotchas |
| [API Reference](docs/API_REFERENCE.md) | All 52+ server endpoints with request/response examples |
| [Database Schema](docs/DATABASE_SCHEMA.md) | All 13 tables with field-level detail + ERD |
| [User Flows](docs/USER_FLOWS.md) | Step-by-step user journeys with Mermaid diagrams |
| [System Design](docs/SYSTEM_DESIGN.md) | Architectural decisions with rationale |
| [Deployment Guide](docs/DEPLOYMENT.md) | Server deployment, user app distribution, env vars |
| [Campaign Architecture](docs/campaign-platform-architecture.md) | Server architecture deep dive |
| [Auto-Poster Workflow](docs/auto-poster-workflow.md) | Daily pipeline, scheduling, content strategy |
| [Brand Strategy](docs/brand-strategy.md) | Brand positioning, voice, audience, content pillars |

## Troubleshooting

### Session expired (redirected to login)
Re-run `python scripts/login_setup.py <platform>` for the affected platform.

### Selectors broken (can't find compose area)
Platform UI changed. Update the selector constants at the top of each platform function in `scripts/post.py`.

### No drafts being posted
Check `drafts/pending/` for files. Check `logs/poster.log` for errors.

### TikTok posting fails with proxy/network error
TikTok is blocked in some regions. Connect a VPN or configure a SOCKS proxy in `config/platforms.json` under `tiktok.proxy`.

### Generator producing invalid JSON
Check `logs/generator.log`. The generator strips markdown fences and validates JSON. If Claude's output format changes, check the prompt in `scripts/generate.ps1`.

### Server won't start
Check `server/.env` exists and `DATABASE_URL` is valid. For SQLite, the DB file is auto-created on startup.

### Campaign runner can't connect to server
Verify `CAMPAIGN_SERVER_URL` in `config/.env` points to a running server. Check `config/server_auth.json` has a valid token.

### Onboarding fails
Ensure the server is running and accessible. Re-run `python scripts/onboarding.py` to restart setup.
