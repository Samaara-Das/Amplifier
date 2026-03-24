# Amplifier Technical Architecture v2

**Status**: Draft
**Date**: 2026-03-24
**Companion doc**: [Product Spec v2](./PRODUCT_SPEC_V2.md)

---

## 1. System Overview

Amplifier is a two-sided marketplace: companies pay to have campaigns promoted on social media, users earn money by posting that content. The system consists of five deployed components:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AMPLIFIER SERVER                              │
│            (Vercel — FastAPI + Supabase PostgreSQL)                   │
│                                                                      │
│  REST API (/api/)          Company Dashboard (/company/)             │
│  - Auth (JWT)              - Campaign creation (AI wizard)           │
│  - Campaigns               - Campaign management                    │
│  - Posts / Metrics          - Budget & billing                       │
│  - Users / Earnings         - Analytics & export                     │
│  - Admin                                                             │
│                            Admin Dashboard (/admin/)                 │
│  AI Services               - Campaign review queue                   │
│  - Campaign wizard         - User management                        │
│  - Matching scorer         - Fraud detection                        │
│  - Content screening       - Payouts                                │
│                                                                      │
│  Services: matching, billing, trust, payments                        │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
              HTTPS (pull-based polling, every 10 min)
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
  ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
  │  Tauri  │       │  Tauri  │       │  Tauri  │     x N users
  │ Desktop │       │ Desktop │       │ Desktop │
  │  App    │       │  App    │       │  App    │
  │         │       │         │       │         │
  │ WebView │       │ WebView │       │ WebView │  ← UI (HTML/CSS/JS)
  │ Rust    │       │ Rust    │       │ Rust    │  ← Core (IPC, tray, scheduling)
  │ Python  │       │ Python  │       │ Python  │  ← Sidecar (Playwright, AI, scraping)
  │ SQLite  │       │ SQLite  │       │ SQLite  │  ← Local database
  └─────────┘       └─────────┘       └─────────┘
```

### Component Summary

| Component | Technology | Hosting | Purpose |
|-----------|-----------|---------|---------|
| **User App** | Tauri 2 (Rust + WebView + Python sidecar) | Desktop (Windows, macOS, Linux) | Campaign management, content review, background posting |
| **Company Dashboard** | FastAPI + Jinja2 templates | Vercel (SSR) | Campaign creation, performance monitoring, budgets |
| **Admin Dashboard** | FastAPI + Jinja2 templates | Vercel (SSR) | Campaign review, user management, fraud detection, payouts |
| **Server API** | FastAPI (Python) | Vercel (serverless) | REST API for all three apps |
| **Database** | Supabase PostgreSQL (prod) / SQLite (dev) | Supabase cloud | Authoritative data store |

### Key Architectural Principle: User-Side Compute

All AI content generation, browser automation, and metric scraping run on the user's device. The server is a lightweight coordination layer. This means:
- Social media credentials never leave the user's device
- No browser instances or AI inference on the server
- Scaling is distributed — each user is their own compute node
- Server costs stay low regardless of user count

---

## 2. Tauri Desktop App Architecture

The Tauri app is the biggest new piece. It replaces the current Flask dashboard (`campaign_dashboard.py` on port 5222) and the CLI-based `campaign_runner.py` with a native desktop application.

### 2.1 Why Tauri

The current user app is a Python process running a Flask server plus a campaign runner loop plus Playwright browsers — stitched together with Windows Task Scheduler. This has several problems: no system tray, no native notifications, requires Python installed, and the Flask UI must be accessed through a browser. Tauri solves all of these while reusing the entire existing Python codebase as a sidecar process.

| Concern | Current (Flask + scripts) | Tauri v2 |
|---------|--------------------------|----------|
| UI | Flask on localhost:5222, opened in browser | Native WebView window, feels like a real app |
| Background agent | `campaign_runner.py` loop + Task Scheduler | System tray icon, runs continuously |
| Notifications | None | Native OS notifications (new campaigns, post failures, earnings) |
| Distribution | PyInstaller + Inno Setup | Tauri bundler (MSI/NSIS on Windows, DMG on macOS, AppImage on Linux) |
| Python dependency | User must have Python installed | Bundled Python sidecar — no user setup |
| Startup | User manually launches scripts | Auto-start on login (optional), system tray |

### 2.2 Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     WEBVIEW (UI Layer)                    │
│  HTML / CSS / JS (vanilla JS + lit-html for templating)  │
│                                                          │
│  Pages: Dashboard, Campaigns, Posts, Earnings, Settings  │
│  Theme: Blue (#2563eb) / white, DM Sans font             │
│  Communication: Tauri invoke() + listen() to Rust        │
└───────────────────────┬─────────────────────────────────┘
                        │ Tauri IPC (invoke / events)
┌───────────────────────▼─────────────────────────────────┐
│                    RUST CORE (Backend)                    │
│                                                          │
│  Tauri Commands:                                         │
│  - get_dashboard_data() → JSON                           │
│  - get_campaigns() → JSON                                │
│  - accept_campaign(id) → Result                          │
│  - reject_campaign(id) → Result                          │
│  - approve_content(id, platform) → Result                │
│  - regenerate_content(id, platform) → Result             │
│  - get_earnings() → JSON                                 │
│  - get_settings() → JSON                                 │
│  - update_settings(mode, schedule) → Result              │
│  - connect_platform(name) → Result                       │
│  - refresh_profile(platform) → Result                    │
│  - withdraw_earnings() → Result                          │
│                                                          │
│  System Tray: icon + context menu (Show/Hide, Quit)      │
│  Scheduler: tokio cron for posting, scraping, polling     │
│  SQLite: rusqlite for direct DB reads (fast UI queries)   │
│  Sidecar Manager: spawn/monitor Python process            │
│  Notification: tauri-plugin-notification                  │
└───────────────────────┬─────────────────────────────────┘
                        │ stdin/stdout JSON-RPC + events
┌───────────────────────▼─────────────────────────────────┐
│                 PYTHON SIDECAR (Worker)                   │
│                                                          │
│  Reused from existing codebase:                          │
│  - scripts/post.py → posting engine (Playwright)         │
│  - scripts/utils/human_behavior.py → anti-detection      │
│  - scripts/utils/content_generator.py → AI generation    │
│  - scripts/agents/pipeline.py → LangGraph pipeline       │
│  - scripts/agents/{profile,research,draft,quality}_node  │
│  - scripts/utils/metric_scraper.py → engagement scraping │
│  - scripts/utils/metric_collector.py → hybrid collection │
│  - scripts/utils/server_client.py → server API client    │
│  - scripts/utils/local_db.py → SQLite operations         │
│  - scripts/utils/image_generator.py → image creation     │
│  - scripts/login_setup.py → platform authentication      │
│                                                          │
│  New:                                                    │
│  - sidecar/main.py → JSON-RPC command dispatcher         │
│  - sidecar/profile_scraper.py → platform profile scraper │
│  - sidecar/session_health.py → session validity checker  │
│  - sidecar/scheduler.py → posting schedule calculator    │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Rust ↔ Python Sidecar Communication

The Python sidecar runs as a long-lived child process managed by Rust. Communication uses **JSON-RPC over stdin/stdout** — the same pattern Tauri's sidecar API supports natively.

**Protocol:**

```
Rust → Python (stdin):  {"jsonrpc": "2.0", "method": "generate_content", "params": {...}, "id": 1}
Python → Rust (stdout): {"jsonrpc": "2.0", "result": {...}, "id": 1}
Python → Rust (stdout): {"jsonrpc": "2.0", "method": "event", "params": {"type": "post_success", ...}}
```

**Command types (Rust calls Python):**

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `generate_content` | `{campaign_id, platforms[]}` | `{platform: content}` | Run agent pipeline or content_generator |
| `post_content` | `{platform, content, image_path?}` | `{post_url, success}` | Post via Playwright (post.py) |
| `scrape_metrics` | `{post_url, platform}` | `{impressions, likes, ...}` | Scrape engagement (metric_collector) |
| `connect_platform` | `{platform}` | `{success}` | Launch login_setup browser |
| `scrape_profile` | `{platform}` | `{followers, bio, posts[], niches[]}` | Scrape user profile data |
| `check_session` | `{platform}` | `{status: green/yellow/red}` | Test session validity |
| `poll_server` | `{}` | `{campaigns[], earnings}` | Fetch from server API |
| `report_metrics` | `{metrics[]}` | `{success}` | Send metrics to server |
| `report_posts` | `{posts[]}` | `{success}` | Register posts with server |
| `sync_earnings` | `{}` | `{balance, pending, history[]}` | Fetch earnings from server |

**Event types (Python notifies Rust, unsolicited):**

| Event | Payload | UI Action |
|-------|---------|-----------|
| `post_success` | `{platform, post_url, campaign_id}` | Update Posts tab, show notification |
| `post_failure` | `{platform, error, campaign_id}` | Show error notification, mark failed |
| `session_expired` | `{platform}` | Show re-auth alert on Dashboard |
| `new_campaigns` | `{count}` | Badge on Campaigns tab |
| `earnings_updated` | `{balance, pending}` | Update Earnings display |
| `content_ready` | `{campaign_id, platforms[]}` | Badge on Posts tab (pending review) |
| `scrape_complete` | `{post_id, metrics}` | Update metrics in Posts tab |

**Lifecycle:**

1. Tauri app starts → Rust spawns Python sidecar as a child process
2. Python sidecar initializes: loads `.env`, inits local DB, connects Playwright
3. Rust sends commands via stdin, Python responds via stdout
4. Python can also emit unsolicited events (progress, errors) via stdout
5. If sidecar crashes, Rust restarts it automatically (3 retries with backoff)
6. On app quit, Rust sends `shutdown` command, Python closes browsers and exits

### 2.4 System Tray Integration

The Tauri app runs as a system tray icon when the window is closed. The background agent continues running:

```
System Tray Icon (blue Amplifier logo)
├── Show Dashboard          → opens/focuses the WebView window
├── ─────────────
├── Active Campaigns: 3     → informational
├── Next Post: 2:30 PM      → informational
├── ─────────────
├── Pause Posting           → toggles posting on/off
├── ─────────────
└── Quit Amplifier          → stops sidecar, exits
```

**Background tasks running while minimized to tray:**
- Campaign polling (every 10 minutes)
- Post scheduling and execution (at scheduled times)
- Metric scraping (T+1h, 6h, 24h, 72h after each post)
- Session health checks (every 2 hours)
- Profile refresh (weekly)

### 2.5 Local SQLite Database

The existing `data/local.db` schema (from `scripts/utils/local_db.py`) is reused with additions for v2:

**Existing tables (unchanged):**
- `local_campaign` — synced campaigns from server
- `local_post` — posts created locally
- `local_metric` — scraped engagement data
- `local_earning` — earnings cache from server
- `settings` — key/value user preferences

**New tables for v2:**

```sql
-- Campaign invitations (new: invitation system)
CREATE TABLE invitation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_campaign_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    brief TEXT,
    payout_summary TEXT,         -- JSON: estimated earnings, rates
    platforms_required TEXT,      -- JSON: ["x", "linkedin"]
    deadline TEXT,                -- ISO datetime (3 days from receipt)
    status TEXT DEFAULT 'pending', -- pending | accepted | rejected | expired
    received_at TEXT DEFAULT (datetime('now'))
);

-- User profile data per platform (new: scraped profiles)
CREATE TABLE user_profile (
    platform TEXT PRIMARY KEY,
    username TEXT,
    display_name TEXT,
    bio TEXT,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    recent_posts TEXT,           -- JSON: [{content, likes, comments, date}, ...]
    posting_frequency REAL,      -- posts per week
    engagement_rate REAL,        -- avg engagement / followers
    ai_niches TEXT,              -- JSON: ["finance", "tech"]
    profile_picture_url TEXT,
    extracted_at TEXT,           -- ISO datetime
    synced_to_server INTEGER DEFAULT 0
);

-- Post schedule queue (new: scheduling engine)
CREATE TABLE schedule_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_server_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    content TEXT NOT NULL,
    image_path TEXT,
    scheduled_at TEXT NOT NULL,   -- ISO datetime
    status TEXT DEFAULT 'queued', -- queued | posting | posted | failed | cancelled
    post_id INTEGER,              -- FK to local_post after posting
    created_at TEXT DEFAULT (datetime('now'))
);

-- Session health tracking (new: per-platform session status)
CREATE TABLE session_health (
    platform TEXT PRIMARY KEY,
    status TEXT DEFAULT 'unknown', -- green | yellow | red | unknown
    last_checked TEXT,
    last_successful_post TEXT,
    error_message TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

**Database access pattern:**
- **Rust** reads the SQLite database directly via `rusqlite` for fast UI queries (dashboard stats, campaign lists, post statuses). Read-only from Rust.
- **Python** owns all writes to the database via `scripts/utils/local_db.py`. All mutations go through Python.
- No concurrent write conflicts because only one process writes.

### 2.6 Tauri Project File Structure

```
amplifier-desktop/
├── src-tauri/                     # Rust backend
│   ├── Cargo.toml
│   ├── tauri.conf.json            # App config: name, window, permissions
│   ├── icons/                     # App icons (all sizes)
│   ├── src/
│   │   ├── main.rs                # Entry point, setup tray, spawn sidecar
│   │   ├── commands/              # Tauri command handlers
│   │   │   ├── mod.rs
│   │   │   ├── campaigns.rs       # get_campaigns, accept, reject
│   │   │   ├── content.rs         # approve, regenerate, edit
│   │   │   ├── earnings.rs        # get_earnings, withdraw
│   │   │   ├── platforms.rs       # connect, disconnect, refresh_profile
│   │   │   ├── settings.rs        # get/update settings
│   │   │   └── dashboard.rs       # get_dashboard_data
│   │   ├── sidecar.rs             # Python process manager (spawn, restart, IPC)
│   │   ├── db.rs                  # rusqlite read-only queries
│   │   ├── scheduler.rs           # tokio cron task dispatcher
│   │   ├── tray.rs                # System tray setup and handlers
│   │   └── state.rs               # Shared app state (sidecar handle, DB path)
│   └── sidecar/                   # Python sidecar (bundled)
│       ├── main.py                # JSON-RPC dispatcher (stdin/stdout loop)
│       ├── profile_scraper.py     # Platform profile scraping logic
│       ├── session_health.py      # Session validity checker
│       ├── scheduler.py           # Optimal posting time calculator
│       └── requirements.txt       # Python dependencies
│
├── src/                           # WebView frontend
│   ├── index.html                 # Shell HTML (loads app.js)
│   ├── styles/
│   │   ├── main.css               # Global styles, theme variables
│   │   ├── components.css         # Reusable component styles
│   │   └── pages.css              # Page-specific styles
│   ├── js/
│   │   ├── app.js                 # Router, page lifecycle, Tauri bridge
│   │   ├── api.js                 # Tauri invoke() wrappers
│   │   ├── components/            # Reusable UI components
│   │   │   ├── campaign-card.js
│   │   │   ├── post-preview.js
│   │   │   ├── platform-badge.js
│   │   │   ├── metric-chart.js
│   │   │   ├── notification.js
│   │   │   └── modal.js
│   │   ├── pages/                 # Page modules
│   │   │   ├── dashboard.js
│   │   │   ├── campaigns.js
│   │   │   ├── posts.js
│   │   │   ├── earnings.js
│   │   │   ├── settings.js
│   │   │   └── onboarding.js
│   │   └── utils/
│   │       ├── format.js          # Date, currency, number formatting
│   │       └── theme.js           # Theme constants
│   └── assets/
│       ├── fonts/                 # DM Sans woff2
│       └── icons/                 # SVG platform icons, status icons
│
├── scripts/                       # Existing Python codebase (symlinked or copied)
│   ├── post.py
│   ├── login_setup.py
│   ├── utils/
│   │   ├── content_generator.py
│   │   ├── human_behavior.py
│   │   ├── metric_scraper.py
│   │   ├── metric_collector.py
│   │   ├── server_client.py
│   │   ├── local_db.py
│   │   ├── image_generator.py
│   │   └── draft_manager.py
│   └── agents/
│       ├── pipeline.py
│       ├── state.py
│       ├── profile_node.py
│       ├── research_node.py
│       ├── draft_node.py
│       └── quality_node.py
│
├── config/                        # App configuration
│   ├── platforms.json
│   ├── .env
│   └── content-templates.md
│
├── profiles/                      # Playwright browser profiles (per-platform)
│   ├── x-profile/
│   ├── linkedin-profile/
│   ├── facebook-profile/
│   └── reddit-profile/
│
├── data/
│   └── local.db                   # SQLite database
│
└── package.json                   # Frontend tooling (if using a build step)
```

### 2.7 Frontend Technology Choice

**Vanilla JS + lit-html** (no framework, no build step). Rationale:
- The UI is data-display heavy (tables, cards, metrics) with minimal interactivity
- No complex state management needed — Tauri commands return fresh data on each page load
- Zero build step means faster development iteration
- The entire frontend is < 20 pages with simple CRUD patterns
- `lit-html` provides just enough templating (`html` tagged templates + efficient re-renders) without a framework overhead

If the UI complexity grows beyond what vanilla JS handles cleanly, Svelte is the fallback choice — it compiles to vanilla JS with minimal runtime, and Tauri has first-class Svelte support.

### 2.8 Python Sidecar Bundling

The Python sidecar is bundled as a standalone executable using PyInstaller (Windows) or similar:

```
# Build sidecar binary
pyinstaller --onefile --name amplifier-sidecar src-tauri/sidecar/main.py \
  --add-data "scripts:scripts" \
  --add-data "config:config" \
  --hidden-import playwright \
  --hidden-import langgraph
```

The resulting `amplifier-sidecar.exe` is placed in `src-tauri/binaries/` and Tauri bundles it automatically. The sidecar binary includes:
- All Python scripts from `scripts/` (post.py, utils/*, agents/*)
- Configuration files (platforms.json, content-templates.md)
- Pre-downloaded Playwright Chromium browser (via `playwright install chromium` in the build)

Users install the Tauri app and get everything — no Python installation, no `pip install`, no Playwright setup.

---

## 3. Server Architecture

The server is a FastAPI application deployed on Vercel. It serves three roles: REST API for the user app, SSR web dashboard for companies, and SSR web dashboard for admins.

### 3.1 API Layer

**Base path**: `/api/`

**Existing endpoints (unchanged from v1):**

| Group | Endpoints | Auth |
|-------|-----------|------|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/company/register`, `POST /auth/company/login` | None |
| Campaigns (user) | `GET /campaigns/mine`, `PATCH /campaigns/assignments/{id}` | User JWT |
| Posts | `POST /posts` (batch register) | User JWT |
| Metrics | `POST /metrics` (batch submit) | User JWT |
| Users | `GET /users/me`, `PATCH /users/me`, `GET /users/me/earnings` | User JWT |
| Company | `POST /company/campaigns`, `GET /company/campaigns`, `GET /company/campaigns/{id}`, `PATCH /company/campaigns/{id}`, `GET /company/campaigns/{id}/analytics` | Company JWT |
| Admin | `GET /admin/users`, `POST /admin/users/{id}/suspend`, `GET /admin/campaigns`, `GET /admin/fraud/flags` | Admin cookie |

**New endpoints for v2:**

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/campaigns/invitations` | `GET` | User JWT | Get pending invitations (separate from active assignments) |
| `/api/campaigns/invitations/{id}/accept` | `POST` | User JWT | Accept a campaign invitation |
| `/api/campaigns/invitations/{id}/reject` | `POST` | User JWT | Reject a campaign invitation |
| `/api/users/me/profile` | `PATCH` | User JWT | Update scraped profile data (followers, niches, engagement rates) |
| `/api/users/me/sessions` | `PATCH` | User JWT | Report platform session health statuses |
| `/api/company/campaigns/{id}/reach-estimate` | `GET` | Company JWT | Estimate reach before activating (count matching users) |
| `/api/company/campaigns/wizard` | `POST` | Company JWT | AI-assisted campaign creation (step-by-step) |
| `/api/company/campaigns/{id}/clone` | `POST` | Company JWT | Clone a campaign with new dates/budget |
| `/api/admin/campaigns/review-queue` | `GET` | Admin | Flagged campaigns pending review |
| `/api/admin/campaigns/{id}/approve` | `POST` | Admin | Approve a flagged campaign |
| `/api/admin/campaigns/{id}/reject` | `POST` | Admin | Reject a flagged campaign |

### 3.2 Service Layer

```
server/app/services/
├── matching.py          # Campaign-to-user matching (updated for AI scoring)
├── billing.py           # Earnings calculation from metrics + payout rules
├── trust.py             # Trust score adjustments + fraud detection
├── payments.py          # Stripe Connect integration
├── background_jobs.py   # ARQ worker definitions
├── ai_services.py       # NEW: AI-powered server-side features
└── content_screening.py # NEW: Prohibited content detection
```

**`matching.py` — Updated for v2:**
The current matching algorithm runs on every poll and auto-assigns campaigns. In v2, matching produces *invitations* instead of *assignments*. Assignments are created only when users accept.

**`ai_services.py` — New:**
Server-side AI for features that require centralized data (matching scores, campaign creation, content screening). Uses the same Gemini/Mistral/Groq fallback chain as the user app, with Amplifier's own API keys stored server-side in environment variables.

**`content_screening.py` — New:**
Keyword-based screening at campaign creation time. Campaigns containing prohibited terms are flagged for admin review before activation.

### 3.3 AI Services (Server-Side)

Three server-side AI features, all using the same free API fallback chain (Gemini → Mistral → Groq):

**1. Campaign Creation Wizard**

The company fills out a multi-step form. At each step, the server calls an LLM to assist:
- Step 1: Company provides product URL → server scrapes it (using httpx, not Playwright) → LLM extracts product details, brand voice, key selling points
- Step 4: LLM suggests budget and payout rates based on targeting scope and industry averages
- Step 5: LLM generates the full campaign (title, description, content guidance) from the structured inputs

This is a synchronous request-response flow. The company dashboard shows a loading spinner while the AI generates. Timeout: 30 seconds per step.

**2. AI Matching Scorer**

When the server matches campaigns to users, the final scoring step feeds the campaign brief + user profile (scraped posts, bio, niches) to an LLM and asks for a relevance score 0-100. This replaces the simple niche-overlap point system for the soft scoring stage.

```
Prompt: "Score how well this user matches this campaign (0-100).
Campaign: {title, brief, target audience}
User: {bio, recent posts, niches, engagement rate}
Respond with just the integer score."
```

This runs server-side because it needs access to multiple user profiles in a single matching batch. The LLM call is cached per (campaign_id, user_id) pair for 24 hours to avoid redundant calls.

Hard filters (platforms, followers, region) still run first to eliminate non-candidates before the expensive AI scoring step.

**3. Content Screening**

At campaign creation, the brief and content guidance are checked against prohibited categories:
- Keyword matching (fast, runs first): list of ~200 banned terms across prohibited categories (adult, gambling, drugs, weapons, financial fraud, hate speech)
- If keyword match: campaign is flagged and added to admin review queue
- No LLM call for screening — keyword matching is sufficient for MVP and avoids false positives from model hallucination

### 3.4 Background Jobs

For MVP, background jobs are triggered manually from the admin dashboard. No Redis, no ARQ worker, no cron. This keeps Vercel deployment simple (serverless-compatible).

| Job | Trigger | What It Does |
|-----|---------|--------------|
| Billing Cycle | Admin clicks "Run Billing" | Processes final metrics → calculates earnings → decrements budgets |
| Payout Cycle | Admin clicks "Run Payouts" | Creates payout records for users with balance > $10 |
| Fraud Check | Admin clicks "Run Check" | Anomaly detection + deletion monitoring |
| Invitation Expiry | On each poll request | Lazy: expires invitations older than 3 days when queried |

Post-MVP, billing and fraud checks move to a scheduled worker (Vercel Cron or external trigger hitting an admin endpoint with a shared secret).

### 3.5 Database Changes (Server)

**Modified tables:**

`campaign_assignments` — new statuses for invitation flow:
```
status: invited | accepted | content_generated | posted | metrics_collected | paid | rejected | expired | skipped
```

Added fields:
- `invited_at` (DateTime) — when the invitation was sent
- `expires_at` (DateTime) — 3 days after invited_at
- `responded_at` (DateTime, nullable) — when user accepted/rejected

**New table:**

```sql
-- Campaign review queue (flagged campaigns)
CREATE TABLE campaign_review (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    flagged_terms TEXT[],          -- which terms triggered the flag
    reviewer_id TEXT,              -- admin who reviewed
    decision TEXT,                 -- pending | approved | rejected
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Modified `users` table — new fields:**

```sql
-- Scraped profile data (synced from user app)
engagement_rates JSONB DEFAULT '{}',    -- {"x": 0.032, "linkedin": 0.054}
posting_frequency JSONB DEFAULT '{}',   -- {"x": 12.5, "linkedin": 3.2} (posts/week)
bio_texts JSONB DEFAULT '{}',           -- {"x": "...", "linkedin": "..."}
profile_pictures JSONB DEFAULT '{}',    -- {"x": "url", "linkedin": "url"}
session_health JSONB DEFAULT '{}',      -- {"x": "green", "linkedin": "red"}
last_profile_sync TIMESTAMP WITH TIME ZONE
```

---

## 4. Profile Scraping System

When a user connects a platform, the desktop app scrapes their public profile to extract data for matching. This replaces self-reported information with verified data.

### 4.1 Scraping Flow

```
User connects platform (login_setup.py)
        │
        ▼
Profile scraper runs (Playwright, reuses logged-in session)
        │
        ▼
Raw data extracted: followers, bio, recent posts, engagement
        │
        ▼
AI niche classification: feed scraped posts to LLM → get niche tags
        │
        ▼
Store in local DB (user_profile table)
        │
        ▼
Sync to server (PATCH /api/users/me/profile)
```

### 4.2 Per-Platform Scraping

**X (Twitter)**:
- Navigate to `https://x.com/{username}`
- Extract: display name, bio, follower count, following count, profile picture
- Scroll profile timeline, extract last 30-60 tweets: content text, like count, retweet count, reply count, timestamp
- Calculate: avg engagement per tweet, posting frequency (tweets/week)
- Selectors: `[data-testid="UserName"]`, `[data-testid="UserDescription"]`, follower/following links, tweet articles in timeline

**LinkedIn**:
- Navigate to `https://www.linkedin.com/in/{username}`
- Extract: display name, headline (acts as bio), follower count, profile picture
- Navigate to activity page, extract last 30 posts: content text, like count, comment count
- Note: LinkedIn uses Shadow DOM — use `page.locator()` which pierces shadow roots automatically
- Selectors: `.text-heading-xlarge` (name), `.text-body-medium` (headline), follower count from profile header

**Facebook**:
- Navigate to user's profile page
- Extract: display name, bio/intro, friend count (Facebook doesn't show follower count for personal profiles; fan pages show it)
- Scroll timeline, extract recent posts: content text, like/reaction count, comment count, share count
- Image upload uses "Photo/video" button then hidden file input
- Facebook's DOM is heavily obfuscated — selectors need frequent updates

**Reddit**:
- Navigate to `https://www.reddit.com/user/{username}`
- Extract: display name, karma (post + comment), cake day
- Scroll post history, extract last 30-60 posts: title, subreddit, score (upvotes), comment count
- Reddit uses Shadow DOM (faceplate components) — Playwright locators pierce automatically
- Additional data: most active subreddits (from post history)

### 4.3 AI Niche Classification

After scraping, the collected post content and bio are fed to an LLM for niche classification:

```
Prompt: "Based on this user's social media content, classify their niche(s).
Bio: {bio}
Recent posts: {last 20 posts, concatenated}

Choose from: finance, tech, beauty, fashion, fitness, gaming, food, travel,
education, lifestyle, business, health, entertainment, crypto

Return a JSON array of 1-5 matching niches, most relevant first.
Example: ["finance", "tech", "education"]"
```

Uses the same Gemini → Mistral → Groq fallback chain. The user sees the AI's classification and can confirm or adjust via checkboxes in the onboarding flow.

### 4.4 Storage and Sync

**Local (user_profile table):** Full scraped data including raw post content, used for local display and AI pipeline personalization (the `profile_node` in the agent pipeline reads from this table).

**Server sync (PATCH /api/users/me/profile):** Only summary data is sent to the server:
- `follower_counts`: `{"x": 1500, "linkedin": 500, ...}`
- `niche_tags`: `["finance", "tech"]`
- `engagement_rates`: `{"x": 0.032, "linkedin": 0.054}`
- `posting_frequency`: `{"x": 12.5, "linkedin": 3.2}`
- `bio_texts`: `{"x": "Trading algo builder...", ...}`

Raw post content stays on the user's device. The server only gets aggregated metrics needed for matching.

### 4.5 Frequency

| Trigger | When |
|---------|------|
| On connect | Immediately after login_setup.py completes for a platform |
| Weekly refresh | Background agent runs every 7 days per platform |
| Manual refresh | User clicks "Refresh" in Settings > Profile |

---

## 5. Content Generation Pipeline

When a user accepts a campaign, content is generated locally on their device using AI. The pipeline produces per-platform content adapted to each platform's format and character limits.

### 5.1 Pipeline Overview

```
Campaign brief (from server)
        │
        ▼
┌─────────────────────────────────────────────────┐
│         LangGraph Agent Pipeline                 │
│  (scripts/agents/pipeline.py)                    │
│                                                  │
│  profile_node → research_node → draft_node       │
│       │              │              │             │
│  Read cached    (future:        Generate per-    │
│  user profiles  web research)   platform content │
│  from local DB                                   │
│       │              │              │             │
│       └──────────────┘──────────────┘             │
│                      │                            │
│                      ▼                            │
│                quality_node                       │
│                      │                            │
│              Banned phrase check                  │
│              Length validation                    │
│              Emotion hook check                  │
│              Value delivery check                │
│              Brief adherence check               │
│              Score 0-100 per platform             │
│                      │                            │
│                      ▼                            │
│                output_node                        │
│                      │                            │
│              Format for UI display                │
└─────────────────────────────────────────────────┘
        │
        ▼
Image generation (if campaign has visual component)
        │
        ▼
Content displayed in Posts tab (pending review)
```

### 5.2 Text Generation

**Provider fallback chain** (same as existing `content_generator.py`):

| Priority | Provider | Model | Free Tier |
|----------|----------|-------|-----------|
| 1 | Google Gemini | `gemini-2.5-flash-lite` | 1500 RPD |
| 2 | Mistral | `mistral-small-latest` | Generous free tier |
| 3 | Groq | `llama-3.3-70b` | 14.4K tokens/min |

API keys are **bundled with the app** (Amplifier's own keys, not the user's). Stored in `config/.env`. If one provider is rate-limited, the next is tried automatically.

**Per-platform adaptation:**

The prompt (defined in `content_generator.py`) instructs the LLM to generate genuinely different content per platform:

| Platform | Format | Length | Style |
|----------|--------|--------|-------|
| X | Single tweet | 20-280 chars | Punchy, contrarian, 1-3 hashtags |
| LinkedIn | Narrative post | 200-1500 chars | Professional, story format, aggressive line breaks, 3-5 hashtags |
| Facebook | Conversational post | 50-800 chars | Community-oriented, discussion question, 0-2 hashtags |
| Reddit | Title + body | Title 20-120, body 200-1500 chars | Community member sharing knowledge, no self-promotion, methodology-heavy |

### 5.3 Quality Scoring

The `quality_node` (from `scripts/agents/quality_node.py`) scores each draft 0-100:

**Checks (deductions):**
- Banned phrases (AI-sounding language, trading experience claims, location reveals): -25 per phrase
- Platform length violations (too short/too long): -15
- Missing emotional hook in first sentence: -10
- Missing actionable value: -10

**Bonuses:**
- Has hashtags: +2
- Has engagement question: +3
- Data-driven language ("backtested", "data shows", "proof"): +5

**UI behavior:**
- Score displayed to user next to each platform draft
- Content scoring below 60 shows a warning: "This draft may not perform well. Consider editing or regenerating."
- User can always approve regardless of score

### 5.4 Image Generation

**Provider fallback chain:**

| Priority | Provider | Method | Notes |
|----------|----------|--------|-------|
| 1 | Cloudflare Workers AI | REST API | Fast, reliable, Amplifier's account |
| 2 | Pollinations AI | URL-based (`image.pollinations.ai/prompt/{prompt}`) | Free, no signup, no API key |
| 3 | PIL templates | Local generation (`scripts/utils/image_generator.py`) | Branded text-on-image, uses Windows fonts |

The image prompt is generated alongside text content (the `image_prompt` field in the pipeline output). One image is generated per campaign and used across all platforms.

### 5.5 Content Regeneration

Users can regenerate content per-platform independently:
1. User clicks "Regenerate" on a specific platform's draft
2. Tauri sends `regenerate_content` command to sidecar with `{campaign_id, platform}`
3. Sidecar runs the content generator for just that platform (not the full pipeline)
4. New content replaces the old draft in the local DB
5. Quality score recalculated
6. UI updates in place

---

## 6. AI-Powered Campaign Matching

Matching determines which users see which campaigns. The v2 algorithm uses AI scoring on top of hard filters.

### 6.1 Matching Flow

```
Company activates campaign
        │
        ▼
Server runs matching against all active users
        │
        ├─── Stage 1: Hard Filters (reject non-eligible)
        │    ├── Required platforms connected?
        │    ├── Follower minimums met? (verified via scraping, not self-reported)
        │    ├── Audience region matches?
        │    ├── User not suspended/banned?
        │    ├── User has < 5 active campaigns?
        │    ├── Campaign has remaining budget?
        │    └── User not already invited to this campaign?
        │
        ├─── Stage 2: AI Relevance Scoring (rank candidates)
        │    ├── Feed campaign brief + user profile to LLM
        │    ├── LLM returns relevance score 0-100
        │    └── Cache score per (campaign_id, user_id) for 24h
        │
        ├─── Stage 3: Trust & Engagement Bonuses
        │    ├── Trust score: +0.5 per trust point (0-50 bonus)
        │    └── Engagement rate: +20 per % above platform average
        │
        └─── Stage 4: Selection
             ├── Rank by combined score (AI relevance + trust + engagement)
             ├── Select top N users
             └── Create invitation records (status: "invited", expires_at: +3 days)
```

### 6.2 Hard Filters (Unchanged from v1 + New)

| Filter | Source Data | Check |
|--------|-----------|-------|
| Required platforms | `campaign.targeting.required_platforms` vs `user.platforms` | All required platforms must be connected |
| Follower minimums | `campaign.targeting.min_followers` vs `user.follower_counts` | Per-platform, now verified via scraping |
| Audience region | `campaign.targeting.target_regions` vs `user.audience_region` | User's region must be in target list (or user is "global") |
| Budget remaining | `campaign.budget_remaining` | Must be > $0 |
| Not already invited | `campaign_assignments` table | No existing record for this (campaign, user) pair |
| Active campaign limit | Count of user's active assignments | Must be < 5 |
| User status | `user.status` | Must be "active" |

### 6.3 AI Scoring (New in v2)

The existing v1 scoring uses niche-tag overlap (+30 per matching tag). V2 replaces this with an LLM call:

```python
# Server-side: ai_services.py
async def score_campaign_user_match(campaign: Campaign, user: User) -> int:
    """Score how well a user matches a campaign using AI. Returns 0-100."""
    prompt = f"""Score how relevant this user is for this campaign (0-100).

Campaign:
- Title: {campaign.title}
- Brief: {campaign.brief}
- Target audience: {campaign.content_guidance}
- Niches: {campaign.targeting.get('niche_tags', [])}

User:
- Bio: {user.bio_texts}
- Niches: {user.niche_tags}
- Engagement rates: {user.engagement_rates}
- Follower counts: {user.follower_counts}

Consider: niche alignment, audience overlap, content style fit, engagement quality.
Respond with ONLY an integer 0-100."""

    # Uses Gemini → Mistral → Groq fallback, same as content generator
    score = await call_ai(prompt)
    return int(score)
```

For efficiency, AI scoring only runs on users who pass hard filters. Results are cached in a `match_score_cache` table (campaign_id, user_id, score, cached_at) with a 24-hour TTL.

### 6.4 Invitation System (New in v2)

In v1, matching auto-assigns campaigns to users. In v2, matching creates *invitations* that users must accept or reject:

```
Matching produces invitation → User sees in Campaigns > Invitations tab
  ├── Accept → assignment created (status: "accepted") → content generation starts
  ├── Reject → assignment marked "rejected" (permanent for this campaign)
  └── No action for 3 days → assignment marked "expired" → slot re-offered to other users
```

Multiple users receive invitations for the same campaign — it is not exclusive. The campaign's targeting determines how many invitations are sent (top N by score).

---

## 7. Post Scheduling Engine

When a user approves content, Amplifier schedules it for optimal posting times instead of posting immediately.

### 7.1 Scheduling Algorithm

```python
# sidecar/scheduler.py
def calculate_schedule(approved_content: list, user_campaigns: list, user_timezone: str) -> list:
    """
    Input: list of (campaign_id, platform, content) waiting to be scheduled
    Output: list of (campaign_id, platform, scheduled_datetime)
    """
```

**Inputs:**
- Approved content queue (campaign + platform pairs)
- Each campaign's target region (determines posting windows)
- User's current schedule (already-queued posts)
- User's connected platforms

**Rules applied in order:**

1. **Region-based windows**: Map campaign target region to peak engagement hours:

   | Region | Peak Hours (local time) | Mapped Slots |
   |--------|------------------------|--------------|
   | US | 8AM-10AM, 12PM-2PM, 5PM-8PM EST | 6 slots |
   | UK | 8AM-10AM, 12PM-2PM, 5PM-8PM GMT | 6 slots |
   | EU | 9AM-11AM, 1PM-3PM, 6PM-9PM CET | 6 slots |
   | India | 9AM-11AM, 1PM-3PM, 6PM-9PM IST | 6 slots |
   | Global | Union of US + UK windows | 8 slots |

2. **Minimum 30-minute spacing**: No two campaign posts within 30 minutes of each other.

3. **Platform variety**: Don't post to the same platform for two different campaigns back-to-back. Interleave platforms.

4. **Daily limits**: Maximum posts per day = `min(active_campaigns * 2, 12)`. This prevents spam-like behavior.

5. **Jitter**: Add random offset of 1-15 minutes to avoid posting at exact :00 or :30 marks.

6. **Priority**: Campaigns closer to their end date get earlier slots. Campaigns with higher payout rates also get slight priority.

### 7.2 Queue Management

The `schedule_queue` table in the local SQLite DB holds all queued posts:

```
schedule_queue
├── queued      → content approved, waiting for its time slot
├── posting     → sidecar is currently executing this post
├── posted      → successfully published, linked to local_post record
├── failed      → posting failed (session expired, selector error, timeout)
└── cancelled   → user cancelled before posting time
```

The Rust scheduler (tokio cron) checks the queue every minute. When a post's `scheduled_at` time arrives:
1. Rust sends `post_content` command to Python sidecar
2. Sidecar updates status to "posting"
3. Sidecar runs `post.py` logic for the specific platform
4. On success: status → "posted", `local_post` record created, metric scraping scheduled
5. On failure: status → "failed", error logged, user notified

### 7.3 Schedule Visibility

The Posts > Scheduled section in the UI shows:
- Upcoming posts with their scheduled times
- Campaign name and platform for each
- Option to reschedule (move to a different time slot)
- Option to cancel (removes from queue, marks content as "skipped")

---

## 8. Metric Collection

After posting, the desktop app revisits each post URL at scheduled intervals to scrape engagement data.

### 8.1 Scraping Schedule

| Interval | Purpose | `is_final` |
|----------|---------|-----------|
| T+1h | Verify post is live, early sanity check | No |
| T+6h | Early engagement snapshot | No |
| T+24h | Primary metric (most engagement happens within 24h) | No |
| T+72h | Final metric — used for billing calculation | Yes |

Scraping is triggered by the Rust scheduler, which tracks posted times and fires `scrape_metrics` commands to the Python sidecar at the appropriate offsets.

### 8.2 Platform-Specific Methods

The `MetricCollector` class (`scripts/utils/metric_collector.py`) routes to the best available method per platform:

| Platform | Primary Method | Fallback | Data Extracted |
|----------|---------------|----------|----------------|
| X | API v2 (bearer token) | Playwright scraper | impressions, likes, retweets, replies, quote tweets |
| Reddit | PRAW API | Playwright scraper | score (upvotes), comment count, upvote ratio |
| LinkedIn | Playwright scraper | — | reactions, comments, reposts (no public API) |
| Facebook | Playwright scraper | — | reactions, comments, shares (API requires app review) |

**Playwright scraping** reuses the same browser profiles used for posting. The scraper launches in headless mode to avoid interrupting the user.

**API-based collection** (X and Reddit) is more reliable and doesn't require a browser launch. API keys are stored in `config/.env`:
- X: `X_BEARER_TOKEN` (from Twitter Developer Portal)
- Reddit: `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` (from Reddit App)

### 8.3 Server Sync Protocol

```
Metric scraped locally → stored in local_metric table (reported=0)
        │
        ▼
Next server poll cycle (every 10 minutes):
  1. Collect unreported metrics: SELECT * FROM local_metric WHERE reported=0
  2. Batch report: POST /api/metrics [{post_server_id, impressions, likes, ...}]
  3. On success: UPDATE local_metric SET reported=1 WHERE id IN (...)
  4. On failure: retry on next poll cycle (metrics stay in local DB)
```

Posts must be registered with the server (`POST /api/posts`) before metrics can be reported. The sync flow is:
1. Post is created locally → registered with server → `server_post_id` stored locally
2. Metrics are scraped → linked to the local post → reported to server using `server_post_id`

### 8.4 Billing Trigger

The T+72h scrape is marked `is_final=True` in both local and server databases. When the admin runs the billing cycle:
1. Query all metrics where `is_final=True` and not yet billed
2. Calculate earnings per the campaign's payout rules
3. Deduct from campaign budget
4. Credit to user's earnings balance
5. Dedup: each metric ID is billed at most once

---

## 9. Session Health Monitoring

Platform sessions (browser cookies) expire over time. The desktop app monitors session validity and alerts the user when re-authentication is needed.

### 9.1 Detection Method

The session health checker (`sidecar/session_health.py`) runs a lightweight test per platform:

| Platform | Health Check | How |
|----------|-------------|-----|
| X | Navigate to `https://x.com/home`, check if redirected to login | If URL contains `/login` or `/i/flow` → session expired |
| LinkedIn | Navigate to `https://www.linkedin.com/feed/`, check for auth wall | If redirected to `/login` or sees "Join LinkedIn" → expired |
| Facebook | Navigate to `https://www.facebook.com`, check for login form | If login form is visible → expired |
| Reddit | Navigate to `https://www.reddit.com`, check for logged-in indicators | If "Log In" button visible instead of user menu → expired |

Each check:
- Uses the platform's persistent browser profile (same as posting)
- Runs in headless mode
- Takes ~5-10 seconds per platform
- Timeout: 15 seconds (treat timeout as "unknown")

### 9.2 Status Mapping

| Status | Condition | Meaning |
|--------|-----------|---------|
| `green` | Health check passed, last post within 7 days | Session valid, posting works |
| `yellow` | Health check passed, but no post in 7+ days, or cookies are near expiry | Session probably valid but aging |
| `red` | Health check failed (redirected to login) | Session expired, posting will fail |
| `unknown` | Health check timed out or hasn't run yet | Indeterminate |

### 9.3 Alert Mechanism

When a session transitions to `red`:
1. Python sidecar emits `session_expired` event with `{platform}`
2. Rust receives event → triggers native OS notification: "X session expired — click to re-authenticate"
3. Dashboard > Platform Health widget updates to show red indicator
4. Clicking the re-auth button in Settings calls `connect_platform` → launches `login_setup.py` for that platform
5. After re-auth, health check runs immediately to confirm

### 9.4 Impact on Campaigns

Session expiry does NOT block campaigns:
- Other platforms continue posting normally
- Posts for the expired platform are marked "failed" with reason "session_expired"
- Failed posts auto-retry once the user re-authenticates
- The schedule adjusts: if X is expired and a campaign needs X + LinkedIn, LinkedIn posts proceed on schedule; X post is held until session is restored

### 9.5 Check Frequency

| Check | Frequency | Trigger |
|-------|-----------|---------|
| Periodic | Every 2 hours while app is running | Rust scheduler |
| Pre-post | Immediately before each scheduled post | Part of post flow |
| On-demand | When user opens Settings > Platforms | Tauri command |
| Post-auth | Immediately after user re-authenticates | After login_setup completes |

---

## 10. Communication Patterns

### 10.1 User App ↔ Server: Pull-Based Polling

The desktop app polls the server every 10 minutes (configurable via `CAMPAIGN_POLL_INTERVAL_SEC`). A single poll cycle does multiple things:

```
Poll cycle (every 10 minutes):
1. GET /api/campaigns/invitations     → new campaign invitations
2. GET /api/campaigns/mine            → active assignment updates (status changes, brief edits)
3. POST /api/posts (if any unsynced)  → register new posts with server
4. POST /api/metrics (if any unreported) → submit scraped metrics
5. PATCH /api/users/me/profile (if changed) → sync profile data
6. PATCH /api/users/me/sessions       → report session health statuses
7. GET /api/users/me/earnings         → refresh earnings display
```

**Retry policy**: 3 attempts with exponential backoff (5s, 10s, 20s). If all attempts fail, the cycle is skipped and retried at the next interval. Local operations (posting, scraping) are unaffected by server unavailability.

### 10.2 Campaign Invitation Flow

```
                    Server                              User App
                      │                                    │
  Company activates   │                                    │
  campaign ──────────▶│                                    │
                      │   Matching runs                    │
                      │   Creates invitations              │
                      │                                    │
                      │◀──── GET /campaigns/invitations ───│  (poll)
                      │───── [{id, title, brief, ...}] ──▶│
                      │                                    │  User sees invitation
                      │                                    │  User clicks "Accept"
                      │◀──── POST /invitations/{id}/accept │
                      │───── {assignment created} ─────────▶│
                      │                                    │  Content generation starts
                      │                                    │  User reviews + approves
                      │                                    │  Post scheduled + executed
                      │◀──── POST /posts ──────────────────│
                      │◀──── POST /metrics ────────────────│  (at T+1h, 6h, 24h, 72h)
                      │                                    │
                      │   Admin runs billing cycle         │
                      │   Earnings calculated              │
                      │                                    │
                      │◀──── GET /users/me/earnings ───────│  (poll)
                      │───── {balance: 12.50} ─────────────▶│
```

### 10.3 Campaign Edit Propagation

When a company edits an active campaign (brief, content guidance, payout rates):

```
Company edits campaign on server
        │
        ▼ (stored in database, updated_at changes)
        │
User app polls GET /api/campaigns/mine
        │
        ▼ (compares updated_at with local copy)
        │
        ├── Content not yet generated → uses updated brief automatically
        │
        ├── Content generated, not yet posted → flag as "Campaign updated — please re-review"
        │   User sees flag in Posts tab, can approve with changes or regenerate
        │
        └── Already posted → no change (earnings based on original terms when applicable)
```

The server sends the full campaign object on each poll, including `updated_at`. The user app compares this to the locally cached `updated_at` to detect changes.

### 10.4 Metric Reporting

```
Post published → local_post record created (synced=0)
        │
  Poll: POST /api/posts [{campaign_id, platform, post_url, content_hash}]
        │
  Server returns: [{local_id, server_post_id}] mapping
        │
  Local DB updated: local_post.server_post_id = value, synced=1
        │
  T+1h/6h/24h/72h: metric scraped → local_metric record (reported=0)
        │
  Poll: POST /api/metrics [{server_post_id, impressions, likes, reposts, ...}]
        │
  On success: local_metric.reported = 1
```

### 10.5 Earnings Sync

Earnings are calculated server-side. The user app reads them as a cache:

```
GET /api/users/me/earnings returns:
{
  "balance": 42.50,           // current withdrawable
  "pending": 12.00,           // metrics not yet final
  "total_earned": 235.00,     // lifetime
  "per_campaign": [...],      // breakdown
  "per_platform": {...},      // breakdown
  "payout_history": [...]     // past withdrawals
}
```

The user app stores this in `local_earning` for offline display but never modifies it. Server is authoritative.

---

## 11. Security Model

### 11.1 Unchanged from v1

| Mechanism | Details |
|-----------|---------|
| **Password hashing** | bcrypt via `passlib` (`server/app/core/security.py`) |
| **JWT tokens** | HS256, configurable secret (`JWT_SECRET_KEY`), 24-hour expiry |
| **Token types** | Two JWT types: `"user"` and `"company"` (distinguished by `type` claim) |
| **User API auth** | Bearer token in `Authorization` header, validated via `get_current_user()` |
| **Company API auth** | Bearer token, validated via `get_current_company()` |
| **Company web auth** | JWT stored as httpOnly cookie (`company_token`) |
| **Admin web auth** | Password comparison (env var `ADMIN_PASSWORD`), cookie `admin_token` |
| **Ownership isolation** | Companies see only their own campaigns; users see only their own data |
| **User status enforcement** | `get_current_user()` rejects banned/suspended users with 403 |

### 11.2 New in v2

| Mechanism | Details |
|-----------|---------|
| **Content screening** | Campaign briefs scanned for prohibited terms at creation time. Flagged campaigns require admin approval. |
| **Active campaign limit** | Users limited to 5 active campaigns simultaneously (server-enforced at invitation acceptance) |
| **Invitation expiry** | Invitations auto-expire after 3 days (lazy enforcement: checked on query) |
| **Profile data minimization** | Raw post content stays on-device. Server only receives aggregate metrics (follower counts, engagement rates, niche tags). |
| **API key protection** | AI API keys (Gemini, Mistral, Groq) bundled in the app binary, not exposed to users. Stored in compiled sidecar, not plaintext config. |
| **Sidecar isolation** | Python sidecar runs as a separate process with limited IPC surface. It cannot access Tauri window or system APIs directly. |

### 11.3 Known Security TODOs (Carried Forward)

| Issue | Risk | Status |
|-------|------|--------|
| Admin API uses static cookie value | No cryptographic verification | Known limitation |
| No CORS restrictions | API accessible from any origin | TODO |
| No rate limiting | Vulnerable to brute-force and poll flooding | TODO |
| No email verification | Fake account creation possible | TODO |
| Default JWT secret | Must change in production via `.env` | Configuration |
| No CSRF protection | State-changing requests vulnerable to CSRF | TODO |
| API keys in bundled app | Extractable from binary by determined attacker | Accepted risk (free tier keys, rate-limited) |

---

## 12. Theme

All three apps (user desktop, company dashboard, admin dashboard) share a consistent visual identity:

### 12.1 Color System

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#2563eb` (Blue 600) | Primary buttons, active states, links, header accents |
| `--color-primary-hover` | `#1d4ed8` (Blue 700) | Button hover states |
| `--color-primary-light` | `#3b82f6` (Blue 500) | Secondary accents, badges, light emphasis |
| `--color-primary-bg` | `#eff6ff` (Blue 50) | Tinted backgrounds, card highlights |
| `--color-bg` | `#ffffff` | Page background |
| `--color-bg-secondary` | `#f8fafc` (Slate 50) | Alternate section backgrounds, table stripes |
| `--color-text` | `#1e293b` (Slate 800) | Primary text |
| `--color-text-secondary` | `#64748b` (Slate 500) | Secondary text, labels, captions |
| `--color-border` | `#e2e8f0` (Slate 200) | Card borders, dividers, table borders |
| `--color-success` | `#10b981` (Emerald 500) | Success badges, positive metrics, "green" session status |
| `--color-warning` | `#f59e0b` (Amber 500) | Warning badges, "yellow" session status |
| `--color-error` | `#ef4444` (Red 500) | Error badges, failed states, "red" session status |

### 12.2 Typography

**Font family**: DM Sans (Google Fonts). Loaded as woff2 in the Tauri app; loaded via Google Fonts CDN in the web dashboards.

| Element | Size | Weight |
|---------|------|--------|
| Page title (h1) | 24px | 700 (bold) |
| Section title (h2) | 20px | 600 (semibold) |
| Card title (h3) | 16px | 600 |
| Body text | 14px | 400 (regular) |
| Small text / labels | 12px | 500 (medium) |
| Stat numbers | 28px | 700 |

### 12.3 Component Patterns

Shared across all apps:

- **Cards**: White background, 1px `--color-border` border, 8px border-radius, 16px padding, subtle box shadow (`0 1px 3px rgba(0,0,0,0.1)`)
- **Buttons**: Primary = `--color-primary` bg, white text, 6px border-radius, 8px 16px padding. Secondary = white bg, `--color-primary` text and border.
- **Tables**: Alternating row backgrounds (white / `--color-bg-secondary`), 12px cell padding, `--color-border` dividers
- **Badges**: Rounded pill (999px radius), 4px 12px padding, colored per status (blue=active, green=completed, amber=pending, red=failed, gray=draft)
- **Navigation**: Left sidebar (desktop app) or top nav (web dashboards), `--color-primary` active indicator, SVG icons from Heroicons
- **Stat cards**: Number in `--color-primary`, label in `--color-text-secondary`, optional trend indicator (green up / red down arrow)

### 12.4 Platform-Specific Icons

Each social media platform is represented by its official logo icon (SVG) in the app UI, used in:
- Platform badges (connected/disconnected status)
- Post previews (which platform each draft targets)
- Metric breakdowns (per-platform earnings)
- Session health indicators

| Platform | Icon | Color |
|----------|------|-------|
| X | X logo | `#000000` |
| LinkedIn | LinkedIn "in" logo | `#0077b5` |
| Facebook | Facebook "f" logo | `#1877f2` |
| Reddit | Reddit alien | `#ff4500` |

Note: The v1 dashboards used emerald green (`#10b981`) as the primary color. V2 changes to blue (`#2563eb`). The company and admin dashboards (Jinja2 templates) need their CSS updated to match.

---

## Appendix A: Existing Python Modules Reused

These files from the current codebase are bundled into the Tauri sidecar without modification (or with minimal adaptation):

| Module | Path | Role in v2 |
|--------|------|-----------|
| Post orchestrator | `scripts/post.py` | Core posting engine — Playwright automation for all 4 platforms |
| Human behavior | `scripts/utils/human_behavior.py` | Anti-detection: typing delays, scrolling, mouse movement, browsing |
| Content generator | `scripts/utils/content_generator.py` | AI text generation via Gemini/Mistral/Groq fallback |
| Agent pipeline | `scripts/agents/pipeline.py` | LangGraph content pipeline: profile → research → draft → quality |
| Pipeline state | `scripts/agents/state.py` | TypedDict schema shared by all pipeline nodes |
| Profile node | `scripts/agents/profile_node.py` | Loads cached user profiles for content personalization |
| Research node | `scripts/agents/research_node.py` | (Future) web research for content enrichment |
| Draft node | `scripts/agents/draft_node.py` | Per-platform draft generation |
| Quality node | `scripts/agents/quality_node.py` | Banned phrase, length, hook, value checks — score 0-100 |
| Metric scraper | `scripts/utils/metric_scraper.py` | Revisits post URLs at T+1h/6h/24h/72h for engagement |
| Metric collector | `scripts/utils/metric_collector.py` | Hybrid collection: X/Reddit API + Playwright for LinkedIn/Facebook |
| Server client | `scripts/utils/server_client.py` | Server API communication with retry and auth |
| Local DB | `scripts/utils/local_db.py` | SQLite database operations (extended with new tables for v2) |
| Image generator | `scripts/utils/image_generator.py` | PIL-based branded image generation (fallback) |
| Draft manager | `scripts/utils/draft_manager.py` | Draft file lifecycle management |
| Login setup | `scripts/login_setup.py` | Launches browser for manual platform authentication |

## Appendix B: New Modules to Build

| Module | Location | Purpose |
|--------|----------|---------|
| JSON-RPC dispatcher | `src-tauri/sidecar/main.py` | stdin/stdout command loop, routes to existing Python modules |
| Profile scraper | `src-tauri/sidecar/profile_scraper.py` | Playwright-based profile data extraction per platform |
| Session health checker | `src-tauri/sidecar/session_health.py` | Detect expired platform sessions |
| Posting scheduler | `src-tauri/sidecar/scheduler.py` | Region-based optimal time calculation |
| Rust sidecar manager | `src-tauri/src/sidecar.rs` | Spawn, monitor, restart Python process |
| Rust DB reader | `src-tauri/src/db.rs` | Read-only SQLite queries for fast UI |
| Rust scheduler | `src-tauri/src/scheduler.rs` | tokio cron: trigger posting, scraping, polling |
| Rust tray | `src-tauri/src/tray.rs` | System tray icon, menu, hide-to-tray |
| Tauri commands | `src-tauri/src/commands/*.rs` | Command handlers bridging WebView ↔ sidecar |
| AI services (server) | `server/app/services/ai_services.py` | Campaign wizard, matching scorer |
| Content screening | `server/app/services/content_screening.py` | Prohibited keyword detection |
| Frontend pages | `src/js/pages/*.js` | Dashboard, Campaigns, Posts, Earnings, Settings, Onboarding |
| Frontend components | `src/js/components/*.js` | Campaign card, post preview, metric chart, etc. |
