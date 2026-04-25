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

## Server Deployment (Vercel)

```bash
# Deploy
vercel deploy --yes --prod --cwd server

# Set env vars
printf "value" | vercel env add VAR_NAME production --cwd server

# Current env vars on Vercel:
# DATABASE_URL - Supabase PostgreSQL connection string
# JWT_SECRET_KEY - JWT signing secret
# ADMIN_PASSWORD - Admin dashboard password
# GEMINI_API_KEY - Google Gemini API key
# SUPABASE_URL - https://ozkntsmomkrsnjziamkr.supabase.co
# SUPABASE_SERVICE_KEY - Supabase service role key
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

## Key URLs

| Environment | URL |
|-------------|-----|
| Company Dashboard (prod) | **Offline** — previous Vercel deployment taken down. See `docs/MIGRATION-FROM-VERCEL.md`. |
| Admin Dashboard (prod) | **Offline** — see above |
| Swagger Docs (prod) | **Offline** — see above |
| User App (local) | http://localhost:5222 |
| Server (local) | http://localhost:8000 |
