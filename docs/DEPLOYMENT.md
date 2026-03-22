# Deployment

## Server Deployment

### Local Development

**Prerequisites:**
- Python 3.11+
- pip

**Setup and run:**

```bash
cd server
pip install -r requirements.txt

# Start the server (SQLite database auto-created on first run)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- **Swagger docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **Company dashboard:** http://localhost:8000/company/login
- **Admin dashboard:** http://localhost:8000/admin/login (password: `admin`)

The SQLite database file `amplifier.db` is auto-created in the `server/` directory on first startup via `init_tables()` in the FastAPI lifespan handler. No manual migration step is needed for development.

---

### Vercel

The server is configured for Vercel serverless deployment via `vercel.json` in the project root.

**Configuration (`vercel.json`):**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

**Note:** `rootDirectory` is a Vercel **project-level** setting configured via the Vercel dashboard or CLI (`vercel link`). Do not include it in `vercel.json` — the Vercel CLI rejects it and the deployment fails. The `rootDirectory` for this project is set to `server/` at the project level.

**Entry point:** `server/api/index.py` imports the FastAPI `app` from `app.main` and adjusts `sys.path` so module imports resolve correctly in the serverless environment.

**Environment variables to set in Vercel dashboard:**

| Variable | Required | Value |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Supabase transaction pooler: `postgresql+asyncpg://postgres.PROJECT:PASS@aws-1-us-east-1.pooler.supabase.com:6543/postgres` |
| `JWT_SECRET_KEY` | Yes | A random 64-char secret string |
| `ADMIN_PASSWORD` | Yes | Strong password (not "admin") |
| `PLATFORM_CUT_PERCENT` | No | `20` (default) |
| `MIN_PAYOUT_THRESHOLD` | No | `10.00` (default) |
| `DEBUG` | No | `false` for production |

**Important:** Use `printf` (not `echo`) when setting env vars via CLI to avoid trailing newline corruption:
```bash
printf "value" | vercel env add DATABASE_URL production --cwd server
```

**Supabase connection requirements:**
- Use the **transaction pooler** at `aws-1-us-east-1.pooler.supabase.com:6543` (not direct connection — `db.*.supabase.co:5432` is unreachable from Vercel).
- `database.py` automatically applies NullPool (required for serverless) and `prepared_statement_cache_size=0` (required for pgbouncer) when the URL is PostgreSQL.
- SSL context is created automatically with `check_hostname=False` / `CERT_NONE` for Supabase compatibility.

**SQLite `/tmp/` limitation:** When the `VERCEL` environment variable is detected and `DATABASE_URL` starts with `sqlite`, the database path is automatically redirected to `sqlite+aiosqlite:////tmp/amplifier.db`. The `/tmp/` directory on Vercel is ephemeral -- data is lost between cold starts. This means:
- Tables are re-created on every cold start
- All data is lost when the function instance is recycled
- Acceptable only for demos or testing

**Recommendation:** Always set `DATABASE_URL` to a PostgreSQL connection string for any Vercel deployment beyond local testing.

---

### Production

For a production deployment, use PostgreSQL, Redis, and the ARQ background worker.

**Database:**

```bash
# PostgreSQL setup
createdb amplifier

# Set the connection string
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/amplifier"

# Run Alembic migrations (not auto-created like SQLite)
cd server
alembic upgrade head
```

**Redis + ARQ background worker:**

The ARQ worker runs two scheduled jobs defined in `server/app/services/background_jobs.py`:

| Job | Schedule | Description |
|-----|----------|-------------|
| `billing_cycle` | Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC) | Calculates earnings for posts with final metrics |
| `trust_check` | Twice daily (03:00, 15:00 UTC) | Runs fraud detection and trust score adjustments |

```bash
# Start Redis
redis-server

# Set Redis URL
export REDIS_URL="redis://localhost:6379/0"

# Start the ARQ worker
arq app.services.background_jobs.WorkerSettings
```

**Run the API server:**

```bash
cd server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**CORS:** The default configuration allows all origins (`allow_origins=["*"]`). Restrict this in production by modifying `server/app/main.py`.

---

## Environment Variables Reference

### Server (`server/.env`)

All variables are defined in `server/app/core/config.py` via Pydantic Settings. The `.env` file is loaded automatically from the `server/` working directory.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./amplifier.db` | Database connection string. Use `postgresql+asyncpg://...` for production. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for ARQ background job queue. |
| `JWT_SECRET_KEY` | `change-me-to-a-random-secret` | Secret key for JWT token signing. **Must be changed in production.** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token expiry (24 hours). |
| `PLATFORM_CUT_PERCENT` | `20.0` | Percentage of user earnings retained by Amplifier (0-100). |
| `MIN_PAYOUT_THRESHOLD` | `10.0` | Minimum balance (USD) before a payout can be requested. |
| `HOST` | `0.0.0.0` | Server bind address. |
| `PORT` | `8000` | Server bind port. |
| `DEBUG` | `true` | Enables SQLAlchemy echo logging. Set to `false` in production. |

### User App (`config/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POSTER_ROOT` | (set at runtime) | Absolute path to the project root directory. |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `GENERATE_COUNT` | `6` | Number of drafts to generate per run. |
| `POST_INTERVAL_MIN_SEC` | `30` | Minimum seconds between posting to consecutive platforms. |
| `POST_INTERVAL_MAX_SEC` | `90` | Maximum seconds between posting to consecutive platforms. |
| `PAGE_LOAD_TIMEOUT_SEC` | `30` | Playwright page load timeout. |
| `COMPOSE_FIND_TIMEOUT_SEC` | `15` | Timeout for finding the compose/post editor on a platform. |
| `BROWSE_MIN_DURATION_SEC` | `60` | Minimum pre/post browsing duration for human emulation (seconds). |
| `BROWSE_MAX_DURATION_SEC` | `300` | Maximum pre/post browsing duration for human emulation (seconds). |
| `BROWSE_POSTS_TO_VIEW_MIN` | `2` | Minimum posts to scroll through during browsing. |
| `BROWSE_POSTS_TO_VIEW_MAX` | `4` | Maximum posts to scroll through during browsing. |
| `BROWSE_PROFILES_TO_CLICK_MIN` | `1` | Minimum profiles to visit during browsing. |
| `BROWSE_PROFILES_TO_CLICK_MAX` | `2` | Maximum profiles to visit during browsing. |
| `HEADLESS` | `true` | Run Playwright browsers in headless mode. Set to `false` for debugging. |
| `FIRST_POST_DATE` | (empty) | Date of first real post (YYYY-MM-DD). Controls CTA rotation: Month 1 = 100% value, Month 2+ = 80% value / 15% soft CTA / 5% direct CTA. Defaults to today if unset. |
| `MAX_LIKES_X` | `15` | Daily like cap for X auto-engagement. |
| `MAX_RETWEETS_X` | `3` | Daily retweet cap for X. |
| `MAX_LIKES_LINKEDIN` | `8` | Daily like cap for LinkedIn. |
| `MAX_REPOSTS_LINKEDIN` | `2` | Daily repost cap for LinkedIn. |
| `MAX_LIKES_FACEBOOK` | `8` | Daily like cap for Facebook. |
| `MAX_SHARES_FACEBOOK` | `2` | Daily share cap for Facebook. |
| `MAX_LIKES_INSTAGRAM` | `15` | Daily like cap for Instagram. |
| `MAX_UPVOTES_REDDIT` | `15` | Daily upvote cap for Reddit. |
| `MAX_LIKES_TIKTOK` | `8` | Daily like cap for TikTok. |

---

## User App Development Setup

**Prerequisites:**
- Python 3.11+
- pip
- Playwright Chromium browser

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# One-time: log into each platform to establish browser profiles
python scripts/login_setup.py x
python scripts/login_setup.py linkedin
python scripts/login_setup.py facebook
python scripts/login_setup.py instagram
python scripts/login_setup.py reddit
python scripts/login_setup.py tiktok

# First-run setup: register with server, connect platforms, set mode
python scripts/onboarding.py

# Start the user dashboard
python scripts/campaign_dashboard.py
# Dashboard at http://localhost:5222

# Start the campaign polling loop
python scripts/campaign_runner.py          # continuous loop
python scripts/campaign_runner.py --once   # single poll + process

# Scrape engagement metrics from posted URLs
python scripts/utils/metric_scraper.py
```

**Browser profiles** are stored in `profiles/<platform>/` and persist login sessions. Each platform needs a one-time manual login via `login_setup.py`.

---

## User App Distribution

### PyInstaller Build

The build is configured in `amplifier.spec` at the project root.

```bash
pyinstaller amplifier.spec
```

**Entry point:** `scripts/app_entry.py` -- starts both the campaign dashboard (Flask, background thread) and the campaign runner (async loop, main thread) in a single process. On launch it:
1. Initializes the local SQLite database
2. Checks if the user is logged in; runs onboarding if not
3. Checks the server for available updates via `/api/version`
4. Starts the Flask dashboard on `localhost:5222` in a daemon thread
5. Opens the dashboard in the default browser
6. Runs the campaign polling loop in the main thread

**Bundled data files:**

| Source | Destination in bundle |
|--------|-----------------------|
| `config/platforms.json` | `config/` |
| `config/.env.example` | `config/` |
| `config/content-templates.md` | `config/` |
| `scripts/generate_campaign.ps1` | `scripts/` |
| `scripts/login_setup.py` | `scripts/` |

**Hidden imports** (not auto-detected by PyInstaller):
- `flask`, `playwright`, `playwright.async_api`, `dotenv`, `httpx`, `PIL`, `google.genai`, `groq`, `mistralai`, `browser_use`, `praw`

**Build output:** `dist/Amplifier/` directory containing the executable and all dependencies.

---

### Windows Installer (Inno Setup)

The installer script is `installer.iss` at the project root. Compile with Inno Setup 6.x.

| Setting | Value |
|---------|-------|
| **App name** | Amplifier |
| **Version** | 0.1.0 |
| **Install location** | `{autopf}\Amplifier` (Program Files) |
| **Architecture** | x64 only |
| **Compression** | LZMA, solid |
| **Output filename** | `Amplifier-Setup-0.1.0.exe` |

**Installer contents:**
- Full PyInstaller `dist/Amplifier/` output (recursive)
- `config/platforms.json` copied to `{app}\config\`
- `config/.env.example` copied as `{app}\config\.env` (only if `.env` does not already exist)

**Optional tasks during install:**
- Create desktop shortcut
- Auto-start with Windows (adds registry key at `HKCU\...\Run`)

**Start menu entries:**
- Amplifier (launches the exe)
- Amplifier Dashboard (opens `http://localhost:5222`)
- Uninstall

**Post-install actions:**
1. Runs `playwright install chromium` as a post-install step (fixed in Phase 7 — previous `--install-browsers` flag was invalid)
2. Optionally launches Amplifier

**Uninstall cleanup:** Deletes `data/`, `logs/`, and `profiles/` directories.

---

### Auto-Update

The server exposes a version check endpoint at `GET /api/version`:

```json
{
  "version": "0.1.0",
  "download_url": "",
  "changelog": "Initial release"
}
```

On startup, `scripts/app_entry.py` calls this endpoint and compares the response `version` against the hardcoded `current_version = "0.1.0"`. If they differ, a log message and console notification are displayed with the download URL. The user must manually download and install the update -- there is no automatic in-place upgrade.

---

## User App Configuration

### config/platforms.json

Defines platform URLs, timeouts, enable/disable flags, and platform-specific settings.

```json
{
  "x": {
    "name": "X (Twitter)",
    "compose_url": "https://x.com/compose/post",
    "home_url": "https://x.com/home",
    "timeout_seconds": 30,
    "enabled": true
  },
  "linkedin": {
    "name": "LinkedIn",
    "home_url": "https://www.linkedin.com/feed/",
    "timeout_seconds": 30,
    "enabled": true
  },
  "reddit": {
    "name": "Reddit",
    "home_url": "https://www.reddit.com/",
    "timeout_seconds": 30,
    "enabled": true,
    "subreddits": ["Daytrading", "Forex", "StockMarket", "SwingTrading", "AlgoTrading"]
  },
  "tiktok": {
    "name": "TikTok",
    "home_url": "https://www.tiktok.com/",
    "upload_url": "https://www.tiktok.com/creator#/upload?scene=creator_center",
    "timeout_seconds": 30,
    "enabled": true,
    "note": "TikTok is blocked in India. Connect VPN before running."
  }
}
```

To disable a platform, set `"enabled": false`. Per-platform proxy can also be configured here for geo-restricted platforms.

### server_auth.json

Created by `scripts/onboarding.py` during first-run setup. Stores server URL and JWT token for API authentication. Located in the project root or `config/` directory.

### Browser Profiles

Stored in `profiles/<platform>/` (e.g., `profiles/x/`, `profiles/linkedin/`). Each directory contains a full Chromium user data directory with cookies and session state. Created by `scripts/login_setup.py` during one-time manual login.

---

## Platform-Specific Notes

### X (Twitter)
- An overlay div intercepts pointer events on the post button. The poster uses `dispatch_event("click")` instead of `.click()` to bypass this.
- Image upload is done via a hidden `input[data-testid="fileInput"]` element.

### LinkedIn
- Uses Shadow DOM components. Playwright's `page.locator().wait_for()` pierces shadow DOM automatically, but `page.wait_for_selector()` does **not**. Always use locators.
- Image upload via file input or `expect_file_chooser`.

### Facebook
- Image upload is done via a "Photo/video" button that reveals a hidden file input.

### Reddit
- Uses Shadow DOM (faceplate web components). Playwright locators pierce these automatically -- no special handling needed.
- Posts to one random subreddit per run from the list configured in `platforms.json` under `reddit.subreddits`.

### Instagram
- Multi-step dialog flow: Create > Post submenu > Upload > Next > Next > Caption > Share.
- All buttons require `force=True` due to overlay elements intercepting clicks.

### TikTok
- **VPN required** in regions where TikTok is blocked (e.g., India). Configure a VPN connection before running the poster.
- Uses a Draft.js editor. The poster must send `Ctrl+A` then `Backspace` to clear the pre-filled filename before typing the caption.
- Per-platform proxy support is available in `platforms.json` for routing TikTok traffic through a specific server.
