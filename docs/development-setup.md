# Amplifier -- Development Setup

## Prerequisites

- Python 3.12+
- Node.js (for Supabase CLI via npx)
- Git
- Windows (required for Task Scheduler, Windows fonts in image gen)

## Quick Start

### 1. Install Dependencies

```bash
# Server
cd server
pip install -r requirements.txt

# User app / scripts
pip install -r requirements.txt
playwright install chromium
```

Notable dependencies beyond the standard web stack: `numpy>=1.24.0` (image processing), `piexif>=1.1.3` (EXIF metadata for UGC image pipeline).

### 2. Server (Local)

```bash
cd server
# Create .env with Supabase Storage keys (optional for local)
# Server uses SQLite by default for local dev

GEMINI_API_KEY=your_key python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Server runs at http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Company dashboard: http://localhost:8000/company/login
- Admin dashboard: http://localhost:8000/admin/login (password: "admin")

### 3. User App (Local)

```bash
python scripts/user_app.py
```

User app runs at http://localhost:5222

### 4. Platform Login

Each platform needs a one-time manual login:

```bash
cd scripts
python login_setup.py x
python login_setup.py linkedin
python login_setup.py facebook
python login_setup.py reddit
```

Browser profiles saved to `profiles/{platform}-profile/`.

Platform posting is driven by JSON scripts in `config/scripts/` (e.g., `x_post.json`, `linkedin_post.json`, `facebook_post.json`, `reddit_post.json`) via the declarative posting engine in `scripts/engine/`.

## Server Deployment (Hostinger KVM VPS)

Production server is **LIVE at `https://api.pointcapitalis.com`** (Hostinger KVM 1, Mumbai, since 2026-04-25). See `docs/HOSTING-DECISION-RECORD.md` and `docs/MIGRATION-FROM-VERCEL.md` for full runbooks.

```bash
# SSH into VPS
ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162

# Deploy: pull latest + restart systemd service
git pull && sudo systemctl restart amplifier-web.service

# Check status
sudo systemctl status amplifier-web.service
journalctl -u amplifier-web.service -n 50
```

## Supabase

Project: "amplifier" (Point Capitalis org, East US)

```bash
# CLI (always use npx supabase, never the dashboard)
npx supabase projects list
npx supabase projects api-keys --project-ref ozkntsmomkrsnjziamkr

# Storage bucket: campaign-assets (public)
# Created via REST API, not CLI (CLI doesn't support bucket creation)
```

## Testing

```bash
# Server unit tests (19 tests)
cd server && python -m pytest tests/ -v

# Scripts unit tests (13 tests)
cd scripts && python -m pytest tests/ -v

# Test a specific scraper
cd scripts && python -c "
import asyncio, sys; sys.path.insert(0, '.')
from utils.profile_scraper import scrape_linkedin_profile
from playwright.async_api import async_playwright
async def t():
    async with async_playwright() as pw:
        r = await scrape_linkedin_profile(pw)
        print(f'{r[\"display_name\"]}: {r[\"follower_count\"]} followers')
asyncio.run(t())
"
```

## Task Management

```bash
# View current tasks
task-master list --with-subtasks

# Get next task
task-master next

# Update task status
task-master set-status --id=19 --status=done
```

## UAT Testing

The `/uat-task <id>` skill runs end-to-end acceptance tests against real product flows. UAT helpers live in `scripts/uat/`. See `docs/uat/AC-FORMAT.md` for the AC table format and verification procedure block spec.

**UAT test-mode env flags** (real production code, gated by env vars — default behaviour preserved when unset):

| Variable | Where Read | Effect |
|----------|-----------|--------|
| `AMPLIFIER_UAT_INTERVAL_SEC` | `content_agent.py`, `background_agent.py` | Shortens content-gen loop interval and research/strategy cache TTL (e.g. set to `30` for fast cache-hit/miss testing) |
| `AMPLIFIER_UAT_BYPASS_AI` | `content_agent.py` | Forces ContentAgent to raise immediately, exercising the ContentGenerator fallback path (`1` or `true` to enable) |
| `AMPLIFIER_UAT_FORCE_DAY` | `background_agent.py` | Overrides `day_number` in `generate_daily_content()` — use to test hook diversity across days |
| `AMPLIFIER_UAT_POST_NOW` | `user_app.py` | Schedules approved drafts ~1 min out instead of the next peak-window slot |

## Key URLs

| Environment | URL |
|-------------|-----|
| Company Dashboard (prod) | https://api.pointcapitalis.com/company/login |
| Admin Dashboard (prod) | https://api.pointcapitalis.com/admin/login |
| Swagger Docs (prod) | https://api.pointcapitalis.com/docs |
| User App (local) | http://localhost:5222 |
| Server (local) | http://localhost:8000 |
