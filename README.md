# Amplifier

**🌐 Live demo:** https://api.pointcapitalis.com


Two systems in one repo: a **personal social media automation engine** that generates content via Claude CLI and posts to 6 platforms using Playwright, and a **two-sided marketplace server** where companies create campaigns and users earn money by posting campaign content.

> **Start here for current state**: [`docs/STATUS.md`](docs/STATUS.md) — batches, every task's status, deferred reasons, AC/UAT workflow, server state. Read this **before** opening any spec file. Per-task specs live in [`docs/specs/`](docs/specs/).

## Architecture

```
+------------------+       +------------------+       +------------------+
|   Amplifier      |       |   Amplifier      |       |   Amplifier      |
|   Server         |<----->|   User App       |------>|   Engine         |
|                  |       |                  |       |                  |
| FastAPI + Supabase |       | FastAPI local    |       | Patchright       |
| Company dashboard|       | Background agent |       | Human emulation  |
| Admin dashboard  |       | Local SQLite     |       | Image gen        |
| Matching engine  |       | Metric scraper   |       | (Personal brand: |
+------------------+       +------------------+       |  Claude CLI)     |
  VPS (api.pointcapitalis.com)  User's desktop         +------------------+
                                                         User's desktop
```

**Key design principle:** User-side compute. All AI generation, browser automation, and credential handling happen on the user's device. The server never sees passwords or runs browsers.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Server | Python, FastAPI, SQLAlchemy, Supabase PostgreSQL (prod) / SQLite (dev), ARQ, Jinja2 |
| User App | Python, FastAPI (local), Patchright, AiManager (Gemini/Mistral/Groq), httpx, SQLite |
| Distribution | Nuitka + Inno Setup (Windows) + pkgbuild (Mac) — Phase D, see `docs/migrations/2026-04-28-migration-stealth-and-packaging.md` |
| Deployment | Hostinger KVM VPS + Supabase (server LIVE since 2026-04-25), GitHub Releases for installer auto-update (Phase D) |

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.11+
- Claude Code CLI (installed and authenticated)
- PowerShell 5.1+ (Windows default)

### Server Hosting

**Server is LIVE at https://api.pointcapitalis.com** — Hostinger KVM 1 VPS (Mumbai), Caddy + uvicorn + Supabase PostgreSQL. Migrated from Vercel on 2026-04-25 (Task #41). Full context: `docs/HOSTING-DECISION-RECORD.md`, `docs/MIGRATION-FROM-VERCEL.md`. Local dev still works:

### Server (local development)

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
python -m patchright install chromium
python scripts/onboarding.py               # first-time setup
python scripts/user_app.py                 # local FastAPI at localhost:5222 (drafts, connect, keys)
# Hosted creator dashboard: https://api.pointcapitalis.com/user/
```

### Personal Brand Engine

```bash
# X, TikTok, Instagram are currently disabled in config/platforms.json.
# Only LinkedIn, Facebook, and Reddit are active as of 2026-04-14.
python scripts/login_setup.py linkedin     # one-time login per active platform
python scripts/login_setup.py facebook
python scripts/login_setup.py reddit

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
  user_app.py              Entry point for local FastAPI on port 5222 (drafts, connect, keys)
  background_agent.py      Always-running async agent (posting, polling, content gen, metrics)
  onboarding.py            First-time user setup
  login_setup.py           One-time browser login helper
  app_entry.py             Packaged app entry point
  generate_campaign.ps1    Campaign content generation (preserved but unused — replaced by content_generator.py)
  setup_scheduler.ps1      Windows Task Scheduler setup
  utils/                   Shared modules
    local_server.py          Slim local FastAPI (~500 LOC) — drafts review, platform connect, API keys
    draft_manager.py         Draft lifecycle management
    human_behavior.py        Anti-detection (typing, scrolling, engagement)
    profile_scraper.py       Per-platform profile scraping (3-tier: text → CSS → Vision)
    ai_profile_scraper.py    AI-powered profile extraction (Tier 1 text + Tier 3 vision)
    browser_config.py        Patchright full-screen browser setup helper
    server_client.py         Server API client with retry (21 methods)
    local_db.py              Local SQLite database
    content_generator.py     Free AI API content gen (Gemini → Mistral → Groq fallback)
    metric_collector.py      Hybrid metric collection (APIs for X/Reddit, Browser Use for LinkedIn/Facebook)
    metric_scraper.py        Post engagement scraping (scheduling + local DB sync)
server/                  Amplifier Server (FastAPI)
  app/
    main.py                FastAPI entry point, route mounting
    core/                  Config, database, security
    models/                13 SQLAlchemy models
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
| X (Twitter) | Disabled | Disabled | **DISABLED 2026-04-14** — 2 account blocks by anti-bot detection. Re-enable only after finding a safe automation method (API v2, stealth browser). |
| LinkedIn | Yes | Yes | Shadow DOM — use `locator()` not `wait_for_selector()` |
| Facebook | Yes | Yes | Image upload via "Photo/video" button |
| Instagram | Disabled | Disabled | Disabled in `config/platforms.json` — code preserved |
| Reddit | Yes | Yes | Posts to random subreddit from configured list |
| TikTok | Disabled | Disabled | Disabled in `config/platforms.json` — VPN required in India; code preserved |

## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Developer reference — commands, architecture, platform gotchas |
| [PRD](docs/PRD.md) | Full product requirements: features, data models, API spec, billing, trust |
| [API Reference](docs/api-reference.md) | Server endpoints reference |
| [Technical Architecture](docs/technical-architecture.md) | Architecture overview, routes, services, models |
| [System Flow](docs/amplifier-flow.md) | E2E flow diagrams (Mermaid) |
| [Database Models](docs/database-models.md) | Server DB model field reference |
| [Local DB Schema](docs/local-database-schema.md) | User-side SQLite schema (12 tables — `agent_user_profile` dropped 2026-04-26) |
| [Deployment Guide](docs/deployment-guide.md) | Server deployment (VPS + Supabase), env vars |
| [Platform Posting Playbook](docs/platform-posting-playbook.md) | Platform-specific posting flows and gotchas |
| [Background Agent Reference](docs/background-agent-reference.md) | Background agent tasks, schedule, internals |

## Troubleshooting

### Session expired (redirected to login)
Re-run `python scripts/login_setup.py <platform>` for the affected platform.

### Selectors broken (can't find compose area)
Platform UI changed. Update the selector constants at the top of each platform function in `scripts/post.py`.

### No drafts being posted
Check `drafts/pending/` for files. Check `logs/poster.log` for errors.

### TikTok posting fails with proxy/network error
TikTok is blocked in some regions. Connect a VPN or configure a SOCKS proxy in `config/platforms.json` under `tiktok.proxy`.

### Generator producing invalid JSON (personal brand engine)
Check `logs/generator.log`. The generator strips markdown fences and validates JSON. If Claude's output format changes, check the prompt in `scripts/generate.ps1`. For campaign content, generation is handled by `scripts/utils/content_generator.py` via AiManager — check the log output in the background agent console.

### Server won't start (local)
Check `server/.env` exists and `DATABASE_URL` is valid. For local dev (SQLite), the DB file is auto-created on startup. For the VPS, `DATABASE_URL` must point to the Supabase transaction pooler URL — see `server/.env.example`.

### Campaign runner can't connect to server
Verify `CAMPAIGN_SERVER_URL` in `config/.env` points to a running server. Check `config/server_auth.json` has a valid token.

### Onboarding fails
Ensure the server is running and accessible. Re-run `python scripts/onboarding.py` to restart setup.