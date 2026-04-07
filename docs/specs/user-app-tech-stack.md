# User App Tech Stack — Analysis & Recommendation

**Date**: April 6, 2026
**Status**: Approved architecture direction
**Scope**: Amplifier user-facing desktop app (currently `scripts/user_app.py` + `scripts/background_agent.py`)

---

## Table of Contents

1. [Current Tech Stack Audit](#1-current-tech-stack-audit)
2. [Hard Technical Constraints](#2-hard-technical-constraints)
3. [The Core Architectural Problem](#3-the-core-architectural-problem)
4. [Options Evaluated](#4-options-evaluated)
5. [Recommended Architecture](#5-recommended-architecture)
6. [Installation & Onboarding UX](#6-installation--onboarding-ux)
7. [Web-to-Local Command Flow](#7-web-to-local-command-flow)
8. [Always-Running Requirement](#8-always-running-requirement)
9. [Specific Tech Stack Choices](#9-specific-tech-stack-choices)
10. [Migration Plan](#10-migration-plan)
11. [What Changes vs What Stays](#11-what-changes-vs-what-stays)

---

## 1. Current Tech Stack Audit

### What's running today

| Layer | Technology | Size |
|-------|-----------|------|
| UI | Flask + Jinja2 SSR + vanilla CSS + vanilla JS | 9 templates, 3,451 LOC CSS, 81 LOC JS |
| Data | SQLite (13 tables, WAL mode) | 1,246 LOC (`scripts/utils/local_db.py`) |
| Background | Python asyncio event loop | 939 LOC (`scripts/background_agent.py`) |
| Automation | Playwright (persistent browser profiles) | Across `post.py`, `engine/`, `login_setup.py` |
| AI | Gemini/Mistral/Groq Python SDKs | 472 LOC (`scripts/utils/content_generator.py`) |
| Desktop | pystray (system tray) + plyer (notifications) | In `requirements.txt` |
| Server comms | httpx with retry/backoff | 270 LOC (`scripts/utils/server_client.py`) |
| **Total** | | **~8,047 LOC across key files** |

### What's wrong

1. **SPA behavior forced through server-side rendering.** Sidebar navigation, tab switching, live status badges, 30s AJAX polling — this is SPA behavior delivered via full-page reloads. Every click to Campaigns/Posts/Earnings reloads the entire page, re-renders the sidebar, re-fetches everything. 2015-era UX.

2. **81 lines of JavaScript total.** The only client-side logic is a 30-second poll and browser notifications. No inline draft editing, no optimistic UI, no real-time agent status, no toast notifications for background events. Everything goes through Flask redirects and `flash()` messages.

3. **3,451 lines of hand-rolled CSS.** No utility framework, no component system. Every new page means writing custom CSS from scratch. Maintenance debt that compounds.

4. **No real-time connection.** The background agent communicates with the UI through database writes + 30s polling. User posts something, sees nothing until the next poll cycle. No WebSocket, no SSE.

5. **Distribution is unsolved.** PyInstaller spec is gone. pystray + plyer are in requirements but there's no packaging pipeline. Telling users "install Python, pip install, run a script" is a non-starter for a $200 paid product.

6. **Single-threaded UI + async agent in same process.** Flask's dev server is synchronous. The background agent is asyncio. Mixed in the same Python process via threading. A heavy Playwright operation can make the dashboard feel slow.

### What's fine

- **Python for automation** — Playwright, AI SDKs, scraping all have best-in-class Python libraries. Correct choice.
- **SQLite for local data** — Fast, zero-config, WAL mode for concurrent reads. Perfect for a desktop app.
- **Flask as a localhost API** — If it were just an API backend (not a full UI), Flask would be fine.
- **httpx for server comms** — Async-capable, modern, good retry story. Correct choice.

---

## 2. Hard Technical Constraints

### What MUST run on the user's machine (non-negotiable)

| Component | Why it can't move to server |
|-----------|---------------------------|
| **Playwright browser automation** | Uses persistent browser profiles (`profiles/{platform}-profile/`) with cookies, localStorage, 2FA sessions. User's social media credentials never leave their device — this is a core trust/security promise. |
| **Browser profiles** | Site-specific authentication state. Can't be serialized and uploaded without breaking sessions. |
| **AI content generation** | User's own API keys (Gemini, Mistral, Groq) stored locally, encrypted at rest. Keys never sent to server. |
| **Background agent** | 60s posting loop, 10m campaign polling, 30m session health checks. Must be always-running with access to local browser profiles. |
| **Platform connection** | User manually logs into X/LinkedIn/Facebook/Reddit through a real Playwright browser window. Session captured into local profile directory. |
| **Metric scraping (fallback)** | When APIs aren't available, Playwright navigates to post URLs to scrape engagement metrics. Requires local browser sessions. |

### What does NOT need to be local

| Component | Why it can move to web |
|-----------|----------------------|
| Campaign browsing | Data comes from server API. Pure read operation. |
| Draft review (approve/reject/edit) | Agent can upload drafts to server. User reviews on web. Agent polls for approval. |
| Earnings display | Server is source of truth for earnings. Pure read. |
| Post history & metrics | Server stores all posts and metrics. Pure read. |
| Analytics & stats | Computed server-side. Pure read. |
| Settings (most) | Mode toggle, niche selection, profile info — all stored on server already. |

---

## 3. The Core Architectural Problem

The current app does two fundamentally different jobs in one Flask process:

| Concern | What it does | What it needs |
|---------|-------------|---------------|
| **Dashboard** | Show stats, review drafts, manage campaigns, view earnings, settings | Rich, responsive UI. Real-time updates. SPA navigation. Accessible from any device. |
| **Agent** | Playwright posting, AI content gen, metrics scraping, session health | Headless background process. Reliability. Crash recovery. Access to local browser profiles. Always running. |

These have opposite requirements:
- The dashboard wants fast, interactive, pretty UI → best served as a web app
- The agent wants headless reliability and local hardware access → best served as a background service

Merging them means both are worse. The dashboard is slow (tied to a synchronous Flask process sharing resources with Playwright). The agent is fragile (crashes in the UI layer can kill the posting loop).

---

## 4. Options Evaluated

### Option 1: Keep Flask + Jinja2 (status quo)

Add htmx for SPA-like navigation, flask-socketio for real-time updates.

- **Pros:** Minimal migration work. Same language everywhere.
- **Cons:** PyInstaller packaging still produces 200-400MB installers with antivirus false positives, slow startup, no auto-update. The UI will always feel "web page in a browser" not a real product.
- **Verdict:** Good quick win for v1 UX, doesn't solve distribution. Acceptable for launch, not for scale.

### Option 2: Tauri shell + Python sidecar

Tauri (Rust + system webview) wraps a web frontend. Python agent runs as a sidecar executable.

- **Pros:** Tiny Tauri shell (~5MB), native system tray, auto-update built in, cross-platform.
- **Cons:** Tauri sidecars expect standalone executables. You'd still PyInstaller the Python agent into a 100-200MB `.exe`, then Tauri wraps it. Net result: ~150-250MB total. Adds Rust to the stack. Cross-language debugging (Rust + Python + JS). The installer is barely smaller.
- **Core issue:** Tauri's value is a native UI shell. The agent doesn't need a UI shell — it's headless. Tauri solves a problem we don't have (rich native UI) and doesn't solve the one we do (Python bundling).
- **Verdict:** Wrong tool for this job.

### Option 3: Electron + Python sidecar

Electron for the desktop shell + React/Vue frontend. Python agent as subprocess.

- **Pros:** Mature ecosystem, electron-builder for packaging, auto-update, full Chromium rendering.
- **Cons:** 150-200MB for Electron alone, plus the Python sidecar. 350-500MB total. Memory hog (200-400MB RAM for Electron process). Overkill for a dashboard with 5 pages.
- **Verdict:** Shipping VS Code so users can see a simple dashboard. Over-engineered.

### Option 4: Web dashboard + headless Python agent (**RECOMMENDED**)

Dashboard is a website hosted on Vercel. Agent is a headless Python process with system tray icon.

- **Pros:** Zero UI to package for 90% of the experience. Dashboard auto-updates (it's a website). Agent `.exe` is smaller (no Flask templates, CSS, UI deps). Cross-platform from day 1. Works on any device. Clean separation of concerns.
- **Cons:** Onboarding (platform connection) still needs local interaction. Draft review flow needs rearchitecting (agent pushes drafts to server, user reviews on web, agent polls for approvals). ~2 weeks migration work.
- **Verdict:** Right architecture. Best UX. Least ongoing maintenance.

### Option 5: Progressive Web App + Python agent with local API

PWA served from server, talks to localhost API for agent control.

- **Pros:** Modern web UI with offline capability. Can be "installed" from browser.
- **Cons:** PWA can't start the Python process. Mixed content issues (HTTPS page calling localhost HTTP). User must run agent separately. Less "desktop app" feel.
- **Verdict:** Viable but more friction than Option 4.

---

## 5. Recommended Architecture

Split into two independent components that communicate through the existing server:

```
┌─────────────────────────────────────────┐
│  Web Dashboard (hosted on Vercel)       │
│                                         │
│  Pages:                                 │
│  - /user/login                          │
│  - /user/dashboard (stats, activity)    │
│  - /user/campaigns (list, invitations)  │
│  - /user/campaigns/{id} (detail, draft  │
│    review, approve/reject/edit)         │
│  - /user/posts (history, metrics)       │
│  - /user/earnings (balance, withdraw)   │
│  - /user/settings (profile, mode, sub)  │
│                                         │
│  Tech: Jinja2 + htmx + Alpine.js       │
│  (same stack as company/admin dashboards│
│   — no new framework, no build step)    │
└──────────────┬──────────────────────────┘
               │ (existing server API + new endpoints)
               │
┌──────────────▼──────────────────────────┐
│  Amplifier Server (Vercel + Supabase)   │
│                                         │
│  Existing: campaigns, billing, payouts, │
│  matching, auth, company/admin pages    │
│                                         │
│  New additions:                         │
│  - Draft model + CRUD endpoints         │
│  - Agent command queue                  │
│  - Agent status endpoint                │
│  - SSE for real-time dashboard updates  │
│  - 7 user dashboard HTML pages          │
└──────────────┬──────────────────────────┘
               │ (HTTP REST, Bearer auth, 60s polling)
               │
┌──────────────▼──────────────────────────┐
│  Desktop Agent (system tray .exe)       │
│                                         │
│  Always-running headless Python process │
│                                         │
│  Core jobs:                             │
│  - Playwright posting (60s check loop)  │
│  - AI content generation                │
│  - Campaign polling (10m)               │
│  - Metric scraping                      │
│  - Session health checks (30m)          │
│  - Profile refresh (7d)                 │
│                                         │
│  Server communication:                  │
│  - Pushes: drafts, post results,        │
│    metrics, health status               │
│  - Polls: commands (approve, generate,  │
│    connect, pause/resume)               │
│                                         │
│  Minimal local UI (localhost:5222):     │
│  - Platform connection wizard (2 pages) │
│  - API key management (1 page)          │
│                                         │
│  System tray:                           │
│  - Status indicator (running/paused/err)│
│  - "Open Dashboard" → browser to web    │
│  - "Connect Platforms" → localhost       │
│  - "Settings" → localhost               │
│  - "Pause / Resume"                     │
│  - "Quit"                               │
│                                         │
│  Packaging: Nuitka → native .exe        │
│  Installer: Inno Setup (Windows)        │
│  Auto-update: HTTP version check        │
└─────────────────────────────────────────┘
```

---

## 6. Installation & Onboarding UX

### Installation (what the user experiences)

The user never sees Python, never opens a terminal, never runs pip install.

**Step 1: Download**
- User visits amplifier website or receives download link after paying joining fee
- Downloads `AmplifierSetup.exe` (~300-350MB, includes bundled Chromium)
- Single file, no prerequisites

**Step 2: Install**
```
Double-click AmplifierSetup.exe
  → Inno Setup wizard: "Welcome to Amplifier" → Next → Install Location → Install
  → Installs to C:\Program Files\Amplifier\
  → Creates Start Menu shortcut: "Amplifier"
  → Optionally adds to Windows Startup (auto-start on boot, default: yes)
  → Finish → "Launch Amplifier" checkbox (checked by default)
```

**Step 3: First launch**
```
Amplifier.exe starts
  → System tray icon appears (blue "A" icon)
  → Tray tooltip: "Amplifier — Setting up..."
  → Agent opens user's default browser to: https://app.amplifier.com/register
```

**Why bundle Chromium in the installer (Option A) instead of downloading on first launch (Option B):**

| | Bundle in installer | Download on first launch |
|---|---|---|
| Installer size | ~350MB | ~150MB |
| First launch | Instant (< 1 second) | 1-3 min download wait |
| Offline install | Works | Fails |
| User trust | "Big installer, normal for apps" | "Why is it downloading things after I installed it?" |

For a $200 product, Option A wins. Users expect large installers for desktop software. They don't expect mystery downloads after installation.

### Onboarding (the split flow)

Onboarding has steps that MUST be local (browser login) and steps that are web-based. The web dashboard is the guide; the local agent handles what requires hardware access.

**Step 1: Register (WEB)**
```
Agent opens browser to: https://app.amplifier.com/register?agent=true
User creates account: email + password
Server creates user record, generates JWT
Server redirects to: http://localhost:5222/auth/callback?token=eyJ...
Agent's local Flask server receives the token
Agent stores token encrypted in local DB
Agent redirects browser to: https://app.amplifier.com/onboarding/step2
```

The `?agent=true` query parameter tells the server to redirect to localhost after registration instead of staying on the web. This is the same pattern OAuth uses for desktop app auth flows.

**If user already has an account** (registered on phone/web first):
```
System tray → "Log In"
  → Opens localhost:5222/login
  → User enters email + password
  → Agent calls server API → gets JWT → stores locally
  → Redirects to web dashboard
```

**Step 2: Connect Platforms (LOCAL)**
```
Web dashboard shows: "Connect your social accounts"
  → "Open the Amplifier app on your desktop to connect"
  → Shows 4 platform cards: X, LinkedIn, Facebook, Reddit
  → Each shows "Waiting for connection..."

User right-clicks system tray icon → "Connect Platforms"
  → Opens localhost:5222/connect (minimal local Flask page)
  → Shows 4 buttons: "Connect X", "Connect LinkedIn", etc.

User clicks "Connect X"
  → Playwright opens VISIBLE browser window to x.com
  → User logs in manually (types password, completes 2FA)
  → User closes browser window (or clicks "Done" button)
  → Profile saved to profiles/x-profile/
  → Agent pushes status to server:
    POST /api/agent/status { "platforms": {"x": "connected", ...} }
  → Web dashboard updates via SSE: X card turns green with checkmark

User repeats for each platform.
When at least 1 platform connected, "Continue" button enables on web dashboard.
```

**Step 3: Profile Scanning (LOCAL execution, WEB display)**
```
Web dashboard says: "Scanning your profiles..."
  → Server creates agent command: { type: "scrape_profiles" }
  → Agent polls, sees command, executes profile_scraper.py
  → For each connected platform:
    1. Launch persistent Playwright context (reuses profile from Step 2)
    2. Navigate to home/feed URL
    3. Extract: follower count, bio, recent posts, engagement rate
    4. AI classifies niches from bio + posts
  → Agent pushes results: POST /api/users/me/profile { niches, followers, ... }
  → Web dashboard updates: shows detected niches, follower counts
```

**Step 4: Preferences (WEB)**
```
Web dashboard shows:
  → Detected niches (pre-selected from AI scan), user can adjust
  → Region (auto-detected via IP geolocation)
  → Operating mode: Semi-auto (review before posting) vs Full-auto (auto-post)
  → User clicks "Save & Continue"
  → Stored on server (user profile)
```

**Step 5: API Keys (LOCAL)**
```
Web dashboard says: "Set up your AI keys for content generation"
  → "Open Amplifier app → right-click tray → Settings → API Keys"
  → Shows links to free signup pages for Gemini, Mistral, Groq

User right-clicks tray → "Settings"
  → Opens localhost:5222/settings (minimal local page)
  → Pastes API keys into form fields
  → Keys encrypted and stored locally (never sent to server)
  → Agent tests each key with a sample request → shows green checkmark or red X
  → Agent pushes status: POST /api/agent/status { "ai_keys_configured": true }
  → Web dashboard updates: "AI keys configured" checkmark
```

**Step 6: Complete (WEB)**
```
Web dashboard: "You're all set! Browse campaigns →"
  → set_setting("onboarding_done", "true") on server
  → Redirects to /user/campaigns
  → Background agent immediately starts: polling campaigns, ready to generate and post
```

**Key UX principle:** The web dashboard is the GUIDE. It tells the user what to do step by step. When something requires local hardware access (connect platform, set API keys), the web dashboard says "open the Amplifier app" and shows a waiting state. When the local action completes, the web dashboard updates in real-time via SSE. The local Flask UI is intentionally minimal — a utility page, not a designed experience.

---

## 7. Web-to-Local Command Flow

When a user takes an action on the web dashboard (e.g., approves a draft), the Python agent running on their machine needs to know about it. The mechanism is a **server-side command queue with agent polling**.

### Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Web Browser  │────→│   Server     │←────│  Local Agent  │
│  (user acts)  │     │  (Vercel)    │     │  (Python)     │
└──────────────┘     └──────────────┘     └──────────────┘
                          │                       ↑
                     Stores command           Polls every
                     in agent_command         60 seconds
                     table                        │
                          └───────────────────────┘
```

### Concrete example: User approves a draft

```
1. USER ACTION (Web Dashboard)
   ─────────────────────────────
   User clicks "Approve" on draft #42 at https://app.amplifier.com/user/campaigns/5
   → Browser sends: PATCH /api/drafts/42 { "status": "approved" }
   → Server updates draft record in DB: status = "approved"
   → Server inserts command record:
     INSERT INTO agent_command (user_id, type, payload, status, created_at)
     VALUES (7, 'draft_approved', '{"draft_id": 42}', 'pending', now())

2. AGENT POLLS (Local, every 60 seconds)
   ─────────────────────────────────────
   Background agent's main loop includes:
     response = GET /api/agent/commands?status=pending
     → Returns: [{"id": 101, "type": "draft_approved", "payload": {"draft_id": 42}}]

3. AGENT PROCESSES COMMAND (Local)
   ────────────────────────────────
   Agent sees type="draft_approved":
   → Fetches full draft: GET /api/drafts/42
   → Response: { platform: "x", text: "...", image_url: "...", campaign_id: 5 }
   → Downloads image to local disk if present
   → Calls post_scheduler.py to calculate optimal posting time
   → Inserts into local post_schedule table:
     { draft_id: 42, platform: "x", scheduled_at: "2026-04-06T18:30:00Z", status: "queued" }
   → Acknowledges command:
     POST /api/agent/commands/101/ack

4. AGENT POSTS (when scheduled time arrives)
   ──────────────────────────────────────────
   Normal posting flow kicks in:
   → Playwright opens persistent browser context (x-profile)
   → Executes x_post.json script (type text, upload image, submit)
   → Captures post URL
   → Reports to server: POST /api/posts/report { url, platform, campaign_id }
   → Server pushes update via SSE
   → Web dashboard shows: "Posted to X" with checkmark and post URL
```

### Why polling (not WebSocket)

| Concern | Polling (60s) | WebSocket |
|---------|--------------|-----------|
| Complexity | GET request in existing loop | Persistent connection, reconnection logic, heartbeats |
| Server restart tolerance | Picks up commands next poll | Connection drops, needs reconnect + state reconciliation |
| Vercel compatibility | Native (HTTP request) | Requires separate WebSocket server (Vercel has 25s function timeout) |
| Latency | ≤60 seconds | Near-instant |
| Acceptable? | Yes — user approves draft, agent schedules it for a future time slot (hours away). 60s delay is invisible. | Over-engineered for this use case. |

If lower latency is ever needed (e.g., a "Post NOW" button), the poll interval for commands specifically can drop to 10 seconds without changing the architecture.

### Command types needed

| Command Type | Web Trigger | Agent Action |
|-------------|-------------|-------------|
| `draft_approved` | User approves a draft | Calculate posting time, insert into schedule |
| `draft_rejected` | User rejects a draft | Mark draft rejected. If user requested regeneration, trigger content gen. |
| `draft_edited` | User edits draft text on web | Update local draft content, re-approve |
| `generate_content` | User clicks "Generate" for a campaign | Run content generation pipeline for that campaign |
| `scrape_profiles` | Onboarding Step 3 | Run profile_scraper.py for all connected platforms |
| `force_poll` | User clicks "Refresh Campaigns" | Immediately poll server for new campaign invitations |
| `pause_agent` | User pauses posting from web settings | Stop posting and generation loops |
| `resume_agent` | User resumes posting from web settings | Restart posting and generation loops |

### Server-side implementation

New model (~15 lines):
```python
class AgentCommand(Base):
    __tablename__ = "agent_command"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    type = Column(String, nullable=False)       # "draft_approved", "generate_content", etc.
    payload = Column(Text, default="{}")         # JSON with command-specific data
    status = Column(String, default="pending")   # pending → processing → done | failed
    created_at = Column(DateTime, default=func.now())
    processed_at = Column(DateTime, nullable=True)
```

New endpoints (~50 lines):
```
GET  /api/agent/commands?status=pending    → Return pending commands for authenticated user
POST /api/agent/commands/{id}/ack          → Mark command as done (agent confirms processing)
POST /api/agent/status                     → Agent pushes current health/status
```

Agent-side addition (~30 lines added to background_agent.py poll loop):
```python
async def _process_server_commands(self):
    """Poll server for pending commands and execute them."""
    commands = await server_client.get_pending_commands()
    for cmd in commands:
        if cmd["type"] == "draft_approved":
            await self._handle_draft_approved(cmd["payload"])
        elif cmd["type"] == "generate_content":
            await self._handle_generate_content(cmd["payload"])
        # ... etc
        await server_client.ack_command(cmd["id"])
```

---

## 8. Always-Running Requirement

### The agent must run continuously in both architectures

This does not change regardless of tech stack. The reason is fundamental to what Amplifier does.

**Why it must be always-running:**

The core job is posting at specific scheduled times throughout the day:

| Slot | IST Time | EST Time | What happens |
|------|----------|----------|-------------|
| 1 | 18:30 | 8:00 AM | Agent launches Playwright, opens platform, posts, captures URL |
| 2 | 20:30 | 10:00 AM | Same |
| 3 | 23:30 | 1:00 PM | Same |
| 4 | 01:30 | 3:00 PM | Same |
| 5 | 04:30 | 6:00 PM | Same |
| 6 | 06:30 | 8:00 PM | Same |

Between posts, the agent also runs:
- Metric scraping (every 60s, checks what's due)
- Campaign polling (every 10 min)
- Session health checks (every 30 min)
- Content generation (every 2 min, checks if campaigns need drafts)
- Command polling (every 60s, new in proposed architecture)

**Alternatives evaluated and rejected:**

| Alternative | Why it doesn't work |
|------------|-------------------|
| **Windows Task Scheduler** (wake up only at post times) | 10-30s cold start (Python + Playwright + Chromium). Metric scraping, health checks, and polling can't be pre-scheduled — they run based on dynamic state. |
| **Server-side posting** (move Playwright to cloud) | User's cookies/sessions are local. Uploading them breaks the security model. Cloud IPs trigger platform anti-bot detection. Cost per user is high (dedicated Chromium instances). |
| **Wake-on-push** (server pings agent when work available) | To receive a push, the agent must be listening. Which means it's already running. |

**Resource profile when idle:**

| State | CPU | RAM | Comparable to |
|-------|-----|-----|--------------|
| Idle (sleeping in asyncio loop) | 0% | ~25-35 MB | Dropbox (~100MB), OneDrive (~80MB), Steam (~60MB) |
| Posting (Chromium active) | 5-15% | ~200-400 MB | Chrome with 1 tab open |
| Post-posting (browser closed) | 0% | ~25-35 MB | Back to idle |

The agent spends >99% of its time idle. Users won't notice it.

**What happens if the user shuts down their computer:**
- Posts scheduled during shutdown are missed
- On restart, agent checks for overdue posts:
  - Posts <2 hours overdue → post immediately (still within engagement window)
  - Posts >2 hours overdue → reschedule to next available slot
  - Missed metrics → scraped on next cycle
- The user is in India posting for US hours (18:30-06:30 IST). Their computer is likely on during these evening/night hours.

---

## 9. Specific Tech Stack Choices

### Web Dashboard (hosted on Vercel)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Framework** | Jinja2 templates served by existing FastAPI server | Already using this pattern for company (10 pages) and admin (14 pages) dashboards. Same design system (blue `#2563eb`, DM Sans, gradient cards, Heroicons). No new framework to learn. No build step. No npm. |
| **Interactivity** | htmx + Alpine.js | htmx: SPA-like navigation via partial HTML swaps. One `<script>` tag. Alpine.js: client-side interactions (modals, toggles, countdown timers, form validation). One `<script>` tag. Both eliminate the need for React/Vue/Svelte without sacrificing UX. |
| **Real-time updates** | Server-Sent Events (SSE) | Agent pushes status to server → server pushes to dashboard via SSE. One-directional (server → browser), which is all we need. Simpler than WebSocket. Works through Vercel (unlike WebSocket which hits Vercel's 25s timeout). |
| **Styling** | Existing CSS design system (port from user.css) | 3,451 lines of CSS already written and working. Reuse it. Alternatively, migrate to Tailwind via CDN if a cleanup is desired. |

**Why NOT React/Next.js/Vue:**
- 7 pages of CRUD. Server-rendered Jinja2 + htmx handles this perfectly.
- Adding a JS framework means: npm, build pipeline, Node.js in the stack, separate deployment, CORS configuration, two codebases to maintain.
- The company and admin dashboards already prove the Jinja2 + FastAPI pattern works at this scale.
- React adds zero value for pages that display data from an API and have a few buttons.

### Desktop Agent

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Runtime** | Python 3.11+ | Non-negotiable. Playwright, AI SDKs (google-genai, mistralai, groq), httpx — all Python ecosystem. |
| **Background service** | asyncio event loop (`background_agent.py`) | Already works. No change needed. |
| **System tray** | pystray (already in requirements.txt) | Native Windows/Mac tray icon. Show agent status, context menu with actions. |
| **Notifications** | plyer (already in requirements.txt) | Windows toast notifications. "Posted to X successfully", "New campaign invitation", etc. |
| **Local API** | Flask on localhost:5222 | Only 2-3 routes: platform connection wizard, API key management, auth callback. Stays minimal. |
| **Packaging** | Nuitka (replaces PyInstaller) | See comparison below. |
| **Auto-update** | HTTP version check on startup | Agent calls `GET /api/system/version`. If newer version exists, downloads new `.exe` from GitHub Releases or S3, replaces itself, restarts. ~50 lines of code. |
| **Installer** | Inno Setup (Windows) | Single `.exe` installer. Installs agent + bundled Chromium, creates Start Menu shortcut, optionally adds to Startup. |

**Why Nuitka over PyInstaller:**

| | PyInstaller | Nuitka |
|---|---|---|
| How it works | Bundles Python interpreter + code as archive, extracts to temp on launch | Compiles Python → C → native binary |
| Startup time | 3-10 seconds (extracts archive to temp dir) | <1 second (native execution) |
| Binary size | 200-400MB typically | 100-250MB (30-40% smaller) |
| Antivirus false positives | Common (unknown .exe extracting files to temp triggers heuristics) | Rare (looks like a normally compiled program) |
| Compatibility | Good (most packages work) | Good (most packages work, some C extension edge cases) |
| Build time | Fast (seconds) | Slow (minutes, compiles C) |

For a $200 product, the startup time and antivirus story matter. A 5-second blank screen on launch feels broken. Antivirus quarantining the installer is a support nightmare.

### Server Additions

**New model:**
- `AgentCommand` — Command queue for web-to-agent communication (type, payload, status, timestamps)
- `Draft` — Stores AI-generated draft content per platform (similar to existing Post model but pre-posting stage)

**New API endpoints:**
```
POST   /api/drafts                         → Agent uploads generated draft (text + image)
GET    /api/drafts?campaign_id=X           → Dashboard fetches drafts for review
PATCH  /api/drafts/{id}                    → Dashboard approves/rejects/edits draft
GET    /api/agent/commands?status=pending   → Agent polls for pending commands
POST   /api/agent/commands/{id}/ack         → Agent confirms command processed
POST   /api/agent/status                   → Agent pushes health/platform/posting status
GET    /api/agent/status                   → Dashboard reads agent status (for SSE)
```

**New dashboard pages (7 pages, following existing company/admin patterns):**
```
/user/login           → User auth (JWT)
/user/dashboard       → Stats + activity feed + alerts
/user/campaigns       → Campaign list with 3 tabs (invitations, active, completed)
/user/campaigns/{id}  → Campaign detail + draft review (approve/reject/edit)
/user/posts           → Post history with metrics
/user/earnings        → Balance, per-campaign breakdown, withdrawal
/user/settings        → Profile, mode toggle, subscription, connected platforms status
```

---

## 10. Migration Plan

### Phase 1: Ship v1 with current stack (NOW)

Do NOT migrate yet. The current Flask app works. The blockers are URL capture, Stripe, and billing verification — not the UI framework.

Quick wins to apply now (1-2 days):
1. Add htmx to existing templates for SPA-like navigation (~4 hours)
2. Add flask-socketio for real-time agent → UI push (~4 hours)
3. Don't package at all for first users — white-glove setup included with $200 fee

### Phase 2: Build the split (after 10-20 paying users, ~2 weeks)

| Task | Effort | Risk |
|------|--------|------|
| Add Draft model + AgentCommand model to server DB | 2 hours | Low |
| Add 5 new server API endpoints (drafts, commands, status) | 1-2 days | Low — follows existing patterns |
| Build 7 user dashboard pages on server (Jinja2 + htmx) | 3-5 days | Low — copy company dashboard patterns |
| Add SSE endpoint for real-time dashboard updates | 4 hours | Low |
| Modify background_agent.py to push drafts to server instead of local DB | 1 day | Medium — test upload flow |
| Modify background_agent.py to poll for commands | 4 hours | Low |
| Strip Flask UI from agent (keep only connect + API keys + auth callback) | 2 hours | Low |
| Switch packaging from PyInstaller to Nuitka | 1 day | Medium — test Playwright + Nuitka compat |
| Build auto-update mechanism | 4 hours | Low |
| Build Inno Setup installer with bundled Chromium | 1 day | Medium |

**Total: ~2 weeks of focused work.**

### Phase 3: Polish (ongoing)

- Mac agent packaging (Nuitka supports macOS)
- Auto-update refinement (delta updates, rollback)
- Agent crash recovery (Windows service wrapper or watchdog)
- Offline resilience (agent queues commands locally if server unreachable)

---

## 11. What Changes vs What Stays

### Stays exactly the same (zero changes)

| Component | Why unchanged |
|-----------|--------------|
| All Playwright automation (posting, scraping, profiles) | Core product. No architectural change touches this. |
| All AI content generation (text + images) | Runs locally, uses local API keys. Unaffected by UI location. |
| Background agent core loop (intervals, scheduling, error recovery) | Same asyncio loop, same timing, same logic. |
| Local SQLite for agent state | Agent still needs local state for scheduling, retries, profile cache. |
| Platform connection flow (Playwright browser login) | Still local. Moved from Flask UI route to minimal Flask utility page. |
| Server-side billing, matching, payouts | Completely unrelated to user app tech stack. |
| Engine JSON scripts (`config/scripts/`) | Posting automation layer. Unaffected. |
| Human behavior emulation | Typing delays, scrolling, engagement. Unaffected. |

### Changes

| Component | Current | Proposed | Migration effort |
|-----------|---------|----------|-----------------|
| Campaign browsing UI | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page |
| Draft review UI | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page + new draft upload flow |
| Earnings display | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page (already reads from server) |
| Posts history | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page (already reads from server) |
| Settings UI | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page (some settings stay local) |
| Dashboard | Flask on localhost:5222 | Jinja2 on server (Vercel) | Rebuild 1 page |
| Draft lifecycle | Agent writes to local DB → local Flask reads | Agent uploads to server → web dashboard reads | New server endpoints + agent push logic |
| Agent commands | Direct function calls from Flask routes | Server command queue + 60s polling | New model + 2 endpoints + agent poll loop |
| Real-time updates | 30s JS polling of /api/status | SSE from server | New SSE endpoint |
| Packaging | PyInstaller (no working spec) | Nuitka + Inno Setup | New build pipeline |
| Auto-update | None | HTTP version check + self-replace | New (~50 LOC) |

### Testing required after migration

| Flow | What to verify |
|------|---------------|
| Registration → agent auth handoff | Token passes from web → localhost callback → encrypted storage |
| Platform connection from tray menu | Playwright opens, user logs in, profile saved, status pushed to server |
| Draft generation → server upload | Agent generates content, uploads text + image to server, appears on web |
| Draft approve on web → agent scheduling | User approves on web → command created → agent polls → schedules post |
| Draft reject + regenerate on web | User rejects → agent regenerates → re-uploads |
| Posting pipeline end-to-end | Scheduled post → Playwright execution → URL capture → server report → dashboard update |
| Metric scraping → server sync | Metrics scraped → pushed to server → displayed on earnings page |
| Onboarding complete flow | Register → connect platforms → scan profiles → preferences → API keys → complete |
| Agent restart recovery | Kill agent → restart → overdue posts handled → commands caught up |
| Nuitka packaging | Built .exe launches correctly, Playwright works, all imports resolve |
| Installer | Inno Setup installs cleanly, Chromium bundled, startup entry created |

---

## Appendix: Auth Token Handoff Detail

When the user registers on the web and needs to authenticate the local agent:

**Primary flow (agent running during registration):**
```
1. Agent opens browser to: https://app.amplifier.com/register?agent=true
2. User registers on web
3. Server creates account, generates JWT
4. Server redirects to: http://localhost:5222/auth/callback?token=eyJ...
5. Agent's local Flask receives the token at /auth/callback
6. Agent stores token encrypted in local DB via crypto.py
7. Agent redirects browser to: https://app.amplifier.com/onboarding/step2
```

**Fallback flow (user registered without agent, e.g., on phone):**
```
1. User installs agent later
2. System tray → "Log In" → opens localhost:5222/login
3. User enters email + password on minimal local login page
4. Agent calls POST /api/auth/login → receives JWT
5. Agent stores token encrypted in local DB
6. Agent redirects to web dashboard
```

**Token refresh:**
- JWT has 30-day expiry (configurable)
- Agent includes token in all server requests via Authorization header
- If 401 received, agent clears token and shows tray notification: "Session expired — please log in again"
- Clicking notification opens localhost:5222/login
