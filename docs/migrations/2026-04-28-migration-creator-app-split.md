# Migration: Creator App Split (Hosted Dashboard + Local Daemon)

**Date**: 2026-04-28
**Status**: Planned
**Phase**: D (Business Launch + Tech Stack Migration)
**Estimated effort**: 8-10 days

---

## Why this migration exists

The current creator app conflates two unrelated concerns into one Flask process:
- **A daemon** that polls campaigns, generates content, schedules and executes posts via Playwright, scrapes metrics, and runs continuously.
- **A 9-page Flask UI** that's a slow web page in a browser tab, not a desktop product.

These have opposite needs. The daemon needs to be a reliable background service. The UI needs to feel responsive. Bundling them in one Flask process makes both worse.

The migration splits them:
- **Hosted dashboard** (on the FastAPI server, alongside company/admin): campaigns list, posts history, earnings, settings — all read-mostly, latency-tolerant, benefits from auto-update.
- **Local FastAPI surface** (~400-600 LOC): draft review (the daily-use core loop) + platform connection + API key entry. Stays local because (a) draft editing must be sub-second and offline-capable, (b) platform login launches a real Playwright browser on the user's machine, (c) AI keys must never leave the device.
- **Daemon**: existing 6,500+ LOC of `background_agent.py`, `engine/`, `content_agent.py`, `metric_scraper.py`, `profile_scraper.py`, `local_db.py` — preserved verbatim. Adds ~150 LOC for command polling and draft upload.

This is the architectural shape that survived three independent reviews.

## Decisions and rationale

| Decision | Choice | Why |
|---|---|---|
| Where the campaigns/posts/earnings UI lives | Hosted on FastAPI server (`/user/*`) | Read-mostly, latency-tolerant, auto-updates without user installing anything. |
| Where draft review lives | Local FastAPI on `localhost:5222/drafts` | Daily-use loop, must be sub-second, must work offline, must access local SQLite drafts and image files directly. |
| Where platform connect + API keys live | Local FastAPI on `localhost:5222/connect`, `/keys` | Requires local Playwright launch and on-disk encryption — cannot move to server. |
| Local UI tech stack | FastAPI + Jinja2 + HTMX + Tailwind CDN | Matches server pattern, no new tech. Strips Flask + 9 templates + 3,451 LOC CSS. |
| Web↔daemon command flow | Server-side AgentCommand queue + 60s daemon polling | Simpler than WebSocket, tolerates server restarts, sufficient latency for the non-draft-review flows. |
| Real-time updates web→daemon | Hosted dashboard uses SSE for daemon status push (daemon → server → SSE → web) | Read-only push, simpler than bidirectional. |
| Auth handoff | OAuth-style: web register → server redirects to `localhost:5222/auth/callback?token=...` | Standard pattern, daemon receives JWT, encrypts and stores locally. |
| Draft sync | Daemon writes draft to local SQLite → uploads text + image to server → user reviews on local UI → daemon syncs approve/edit decisions back to server | Local is source of truth for in-progress drafts; server mirrors for cross-device visibility. |

## What changes

### New server-side additions (FastAPI)

| File / change | Purpose |
|---|---|
| `server/app/models/draft.py` | New `Draft` model — mirrors local `agent_draft` for cross-device visibility. Fields: id, user_id, campaign_id, platform, text, image_url, image_local_path, quality_score, status (pending/approved/rejected/posted), created_at. |
| `server/app/models/agent_command.py` | New `AgentCommand` model — server-side command queue. Fields: id, user_id, type (`draft_approved`, `draft_rejected`, `draft_edited`, `generate_content`, `scrape_profiles`, `force_poll`, `pause_agent`, `resume_agent`), payload (JSON), status (pending/processing/done/failed), created_at, processed_at. |
| `server/app/models/agent_status.py` | New `AgentStatus` model — last-known agent health per user. Fields: user_id (PK), running, paused, last_seen, platform_health (JSON), ai_keys_configured, version. |
| `server/app/routers/agent.py` | New endpoints: `GET /api/agent/commands?status=pending`, `POST /api/agent/commands/{id}/ack`, `POST /api/agent/status` (push), `GET /api/agent/status` (read for SSE). |
| `server/app/routers/drafts.py` | New endpoints: `POST /api/drafts` (daemon uploads), `GET /api/drafts?campaign_id=X`, `PATCH /api/drafts/{id}` (approve/reject/edit). Image upload via multipart. |
| `server/app/services/draft_service.py` | Business logic: status transitions, sync rules between local and server. |
| Alembic migration | Three new tables: `draft`, `agent_command`, `agent_status`. |

### Daemon-side additions (Python, in `scripts/`)

| File / change | Purpose |
|---|---|
| `scripts/utils/server_client.py` | Add methods: `get_pending_commands()`, `ack_command(id)`, `push_agent_status(payload)`, `upload_draft(draft_dict, image_bytes)`, `update_draft_status(id, status)`. |
| `scripts/background_agent.py` | Add `_process_server_commands()` task to the asyncio loop (runs every 60s alongside `execute_due_posts`). Handles each command type. |
| `scripts/background_agent.py` | Modify `generate_daily_content()` to upload generated drafts to the server immediately after creation, not just write to local DB. |
| `scripts/background_agent.py` | Add `_push_agent_status()` task (runs every 60s) — pushes running/paused/platform_health/version to server so SSE can fan out to dashboards. |
| `scripts/utils/draft_sync.py` | New module: handles bidirectional sync of draft state between `agent_draft` (local) and `Draft` (server). Conflict resolution: local wins for in-progress edits, server wins for posted state. |

### Local Flask UI strip-down (`scripts/user_app.py` and `scripts/templates/user/`)

| File | Change |
|---|---|
| `scripts/user_app.py` | Replace Flask with FastAPI. Strip all routes EXCEPT: `/auth/callback` (OAuth handoff), `/connect` (platform connection), `/keys` (API key entry), `/drafts` (draft review — new and meaty), `/drafts/{campaign_id}` (campaign-specific drafts). Total ~400-600 LOC. |
| `scripts/templates/user/base.html` | Keep, simplified — Tailwind CDN + HTMX + Alpine. |
| `scripts/templates/user/login.html` | DELETE — login is on the hosted dashboard. |
| `scripts/templates/user/dashboard.html` | DELETE — moved to server. |
| `scripts/templates/user/campaigns.html` | DELETE — moved to server. |
| `scripts/templates/user/campaign_detail.html` | DELETE — moved to server. |
| `scripts/templates/user/posts.html` | DELETE — moved to server. |
| `scripts/templates/user/earnings.html` | DELETE — moved to server. |
| `scripts/templates/user/settings.html` | DELETE — moved to server (read-only display). |
| `scripts/templates/user/onboarding.html` | DELETE — onboarding is now web-driven with local handoffs. |
| `scripts/templates/user/connect.html` | NEW — minimal page with platform connection buttons. |
| `scripts/templates/user/keys.html` | NEW — minimal page with API key inputs (encrypted via existing `crypto.py`). |
| `scripts/templates/user/drafts.html` | NEW — full draft review page (image carousel, inline text editing, approve/reject/restore buttons, day-by-day navigation). |
| `scripts/static/css/*` | DELETE the 3,451 lines of hand-rolled CSS. Replace with Tailwind utility classes. |

### Daemon-side new files

| File | Purpose |
|---|---|
| `scripts/utils/local_server.py` | The slim FastAPI app for `localhost:5222`. Replaces `user_app.py`'s Flask role. |
| `scripts/utils/auth_handoff.py` | Receives JWT from server redirect, encrypts via `crypto.py`, stores in SQLite. |
| `scripts/utils/tray_menu.py` | System tray menu (already exists in `tray.py`) — updates: add "Open Dashboard" (opens hosted web), "Review Drafts" (opens `localhost:5222/drafts`), "Connect Platforms" (opens `localhost:5222/connect`), "Settings" (opens `localhost:5222/keys`), "Pause/Resume", "Quit". |

### Files NOT touched

- `scripts/engine/*` — JSON script engine for posting, all platform scripts. Unchanged.
- `scripts/utils/post.py` — Posting engine. Unchanged.
- `scripts/utils/profile_scraper.py` — Profile scraper. Unchanged.
- `scripts/utils/metric_scraper.py` — Metric scraper. Unchanged.
- `scripts/ai/*` — Content generation, image generation, post-processing. Unchanged.
- `scripts/utils/local_db.py` — Local SQLite. Unchanged (existing 12 tables stay).
- `scripts/utils/crypto.py` — Encryption helpers. Unchanged.
- `scripts/utils/post_scheduler.py` — Post scheduling logic. Unchanged.
- `config/scripts/*.json` — Per-platform JSON post scripts. Unchanged.

## Auth handoff sequence

```
1. User clicks "Sign Up" on hosted dashboard at https://amplifier.app/register?agent=true
2. User completes registration form
3. Server creates user, generates JWT
4. Server returns redirect: http://localhost:5222/auth/callback?token=eyJ...
5. Browser hits localhost:5222
6. Local FastAPI receives token, encrypts via crypto.py, stores in SQLite settings
7. Local FastAPI redirects browser to https://amplifier.app/onboarding/step2
8. Onboarding step 2 (web): "Connect your platforms"
9. Web shows: "Open the Amplifier app on your desktop and right-click the tray icon"
10. User right-clicks tray → Connect Platforms → opens localhost:5222/connect
11. User clicks "Connect LinkedIn" → Playwright opens visible browser → user logs in → profile saved
12. Daemon pushes status to server: POST /api/agent/status with platform_health update
13. Web dashboard updates via SSE: LinkedIn turns green
14. Repeat for each platform
15. Web step 3: "Set up AI keys" — user opens tray → API Keys → enters keys at localhost:5222/keys
16. Web step 4: "Done" — onboarding flag set, redirect to /user/campaigns
```

## Command flow example: User approves a draft

```
1. User opens tray → Review Drafts → localhost:5222/drafts
2. Local FastAPI reads agent_draft table directly, renders HTMX page
3. User clicks "Approve" on draft #42
4. HTMX POST localhost:5222/drafts/42/approve
5. Local FastAPI:
   a. Updates agent_draft.approved = 1 in local SQLite (instant)
   b. Calls server_client.update_draft_status(42, "approved") (background, fire-and-forget)
   c. Calls post_scheduler.schedule_draft(42) → inserts into post_schedule
   d. Returns updated draft card HTML to HTMX
6. Background: server receives PATCH /api/drafts/42 → updates Draft.status = "approved"
7. Hosted web dashboard, if open in another tab, gets SSE update showing draft approved
8. At scheduled time, daemon's execute_due_posts() task fires
9. Playwright posts via Patchright (see stealth migration doc)
10. URL captured, reported to server
```

## Acceptance Criteria

### AC-1: New server endpoints exist and authenticate
**Given** the server is running with the new routers mounted
**When** I call `GET /api/agent/commands` without an Authorization header
**Then** I get 401 Unauthorized
**And** when I call it with a valid user JWT, I get an empty list (no pending commands)

### AC-2: Daemon polls for commands every 60 seconds
**Given** the daemon is running
**When** an admin inserts an `AgentCommand` row for the user
**Then** within 60-90 seconds, the daemon retrieves it via `GET /api/agent/commands`
**And** processes the command according to its type
**And** acks via `POST /api/agent/commands/{id}/ack`
**And** the command's status transitions to `done`

### AC-3: Daemon uploads drafts to server after generation
**Given** the daemon generates content for an accepted campaign
**When** generation completes and `agent_draft` rows are inserted locally
**Then** within 30 seconds, the daemon calls `POST /api/drafts` for each draft
**And** the server `Draft` table contains rows with matching text and image
**And** if upload fails, the local draft has a `synced=0` flag for retry on next iteration

### AC-4: Local UI strip-down — old Flask routes return 404
**Given** the local FastAPI is running on `localhost:5222`
**When** I navigate to any of: `/dashboard`, `/campaigns`, `/posts`, `/earnings`, `/settings`, `/login`, `/onboarding`
**Then** I get 404 Not Found
**And** the only routes that respond are: `/auth/callback`, `/connect`, `/keys`, `/drafts`, `/drafts/{campaign_id}`

### AC-5: Hosted creator dashboard renders campaigns
**Given** I am logged in at `https://amplifier.app/user/login`
**When** I navigate to `/user/campaigns`
**Then** I see my accepted campaigns and pending invitations
**And** the page does NOT have a "Review Drafts" inline button
**And** there is a "Open in Desktop App" link that goes to `localhost:5222/drafts/{campaign_id}`

### AC-6: Local draft review reads directly from local SQLite
**Given** the daemon has generated drafts that have NOT yet been uploaded to the server
**When** I open `localhost:5222/drafts`
**Then** I see those drafts immediately
**And** the page renders even if the server is unreachable (offline test)

### AC-7: Local draft approve writes to local DB instantly
**Given** I am viewing a draft on `localhost:5222/drafts`
**When** I click "Approve"
**Then** the UI updates within 200ms
**And** the local `agent_draft.approved` field is set to 1 immediately
**And** the server-side sync happens in the background (visible in logs as a separate request)
**And** if the background sync fails, the local state remains correct

### AC-8: Auth handoff succeeds
**Given** a fresh install with the daemon running
**When** I sign up at `https://amplifier.app/register?agent=true`
**Then** after submitting the form, my browser is redirected to `localhost:5222/auth/callback?token=...`
**And** within 2 seconds, my browser is redirected to `https://amplifier.app/onboarding/step2`
**And** the local SQLite contains an encrypted JWT
**And** subsequent calls from the daemon to the server include this JWT

### AC-9: Tray menu actions work
**Given** the daemon is running with a system tray icon
**When** I right-click the tray icon
**Then** I see: "Open Dashboard", "Review Drafts", "Connect Platforms", "Settings", "Pause/Resume", "Quit"
**And** "Open Dashboard" opens the hosted web dashboard in the default browser
**And** "Review Drafts" opens `localhost:5222/drafts`
**And** the other actions perform their respective functions

### AC-10: Hosted settings page is read-only for sensitive fields
**Given** I am on `https://amplifier.app/user/settings`
**When** I look at the AI keys section
**Then** I see status only ("Gemini: configured" / "Mistral: not configured")
**And** I do NOT see any input field for API keys
**And** there is a button "Manage Keys (Desktop App)" that opens `localhost:5222/keys`

### AC-11: Pause/resume command works end-to-end
**Given** I am on `https://amplifier.app/user/settings` and the daemon is running
**When** I click "Pause Agent"
**Then** the server inserts an `AgentCommand` of type `pause_agent`
**And** within 90 seconds, the daemon receives the command and pauses
**And** the daemon pushes status update — `paused: true`
**And** the web dashboard shows "Paused" within 2 seconds via SSE

### AC-12: Old templates and CSS deleted
**Given** the migration is complete
**When** I list `scripts/templates/user/`
**Then** I see only: `base.html`, `connect.html`, `keys.html`, `drafts.html`, possibly `auth_callback.html`
**And** the previous templates (`dashboard.html`, `campaigns.html`, `campaign_detail.html`, `posts.html`, `earnings.html`, `settings.html`, `login.html`, `onboarding.html`) are deleted
**And** the 3,451-line CSS file is replaced with Tailwind utility classes inline in templates

## Out of scope

- Tauri shell (rejected — see context)
- React frontend on desktop (rejected)
- Native UI framework (rejected)
- Bidirectional WebSocket sync (SSE one-way is sufficient)
- Mobile app
- Auto-launch on boot (handled by Inno Setup in stealth-and-packaging migration)

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Server outage breaks the creator experience | Mitigated — draft review and posting work entirely offline. Only campaign list, earnings, and settings need the server. Daemon caches campaign list locally; degrades gracefully. |
| Command queue grows unbounded | Add `processed_at` cleanup job: delete `done` commands older than 7 days. |
| Draft sync conflicts (user edits on web while daemon also updates) | Local is source of truth during edit; on conflict, local wins for `text`/`image_url`/`approved`, server wins for `status` if it's `posted`. |
| Daemon offline when web dashboard expects SSE updates | Show "Agent offline" banner if `last_seen` is more than 5 minutes old. |
| Token expiry mid-session | Daemon handles 401 by clearing local token and showing tray notification "Re-authenticate at amplifier.app/login". |

## Test plan

1. Manual E2E onboarding — register from web, verify token handoff, connect 1 platform, enter 1 API key.
2. Manual E2E posting — generate content, review locally, approve, verify post executes via Patchright, URL captured, server has the draft + post records.
3. Offline test — kill server connection, verify draft review still works, verify posts execute via local schedule, verify queue catches up when connection restored.
4. Pytest tests for: command queue lifecycle, draft sync logic, auth handoff edge cases, status push debouncing.
5. Playwright tests for: web→daemon command flow, hosted dashboard with SSE updates.

## Dependencies

- **Dashboards HTMX upgrade migration** — must be in progress or complete (the new creator pages share `base.html` with company/admin).
- **Task #18 (pytest suite)** — must be in place to test the new sync logic.
- **Task #44 (ARQ worker)** — recommended for processing draft uploads asynchronously on the server, though not strictly required for v1.

## Followups

- After v1 launch, consider WebSocket for the agent command channel if 60s polling latency causes user-visible issues.
- Consider an "agent log viewer" page on the hosted dashboard that streams daemon logs via SSE for debugging.
