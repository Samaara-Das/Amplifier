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

---

## Verification Procedure — Task #67

> Format: `docs/uat/AC-FORMAT.md`. Drives the **real local FastAPI** at `localhost:5222`, the **real daemon**, and the **real hosted server** at `https://api.pointcapitalis.com` (or `http://127.0.0.1:8000` in local UAT). Critical-path regression ACs ensure draft review, post execution, profile scraping, content generation still work after the user_app rewrite.

### Preconditions

- Server live with #67 code merged (`https://api.pointcapitalis.com` or local `127.0.0.1:8000`).
- Local daemon installed on dev machine. `data/local.db` exists.
- LinkedIn / Facebook / Reddit profiles connected (verify: `python -c "from scripts.utils.local_db import get_user_profiles; print(get_user_profiles(['linkedin','facebook','reddit']))"`).
- A test user exists on the server (`uat-task67@example.com` / `smoketest123`) and is logged in to the local daemon (encrypted JWT in `data/local.db.settings`).
- `data/local.db` has at least one accepted `agent_assignment` row + corresponding active campaign.
- Local pytest baseline 238/238 green on `flask-user-app`.

### Test data setup

1. Apply Alembic migration adding `draft`, `agent_command`, `agent_status` tables:
   ```bash
   cd server && alembic upgrade head
   ```
2. Seed a test user + accepted campaign + 3 generated drafts in local SQLite via `scripts/uat/seed_creator_local.py` (NEW helper).
3. Start daemon: `python scripts/background_agent.py 2>&1 | tee data/uat/task67_daemon.log` (background).
4. Start local FastAPI: `python scripts/utils/local_server.py 2>&1 | tee data/uat/task67_local.log` (background, binds `127.0.0.1:5222`).
5. Verify both alive: `curl -s http://127.0.0.1:5222/healthz` returns 200.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_INTERVAL_SEC=15` | Shortens daemon command-poll + status-push interval to 15s (default 60s) | AC2, AC11 |
| `AMPLIFIER_UAT_DRAFT_SYNC_NOW` | Forces immediate draft upload (bypasses 30s batch window) | AC3 |

(Document new flag `AMPLIFIER_UAT_DRAFT_SYNC_NOW` in `docs/uat/AC-FORMAT.md` Test-mode flags section when added.)

---

## Features to verify end-to-end (Task #67)

**New functionality (the migration itself):**
1. Server-side Draft + AgentCommand + AgentStatus tables created via Alembic — AC1
2. `GET /api/agent/commands` returns pending list filtered by user — AC2
3. Daemon polls + acks commands every ≤90s — AC2
4. Daemon uploads drafts to server within 30s of generation — AC3
5. Server `Draft` table mirrors local `agent_draft` post-sync — AC3
6. Old Flask routes (`/dashboard`, `/campaigns`, `/posts`, `/earnings`, `/settings`, `/login`, `/onboarding`) all return 404 on `localhost:5222` — AC4
7. Only the 5 new routes respond on `localhost:5222`: `/auth/callback`, `/connect`, `/keys`, `/drafts`, `/drafts/{campaign_id}` — AC4
8. Hosted `/user/campaigns` shows "Open in Desktop App" link instead of inline drafts — AC5 (already verified in Task #66 AC8)
9. Local draft review reads directly from local SQLite (works offline) — AC6
10. Local Approve writes to local DB <200ms; server sync is fire-and-forget — AC7
11. Auth handoff: web register → server redirect to localhost:5222/auth/callback → JWT stored encrypted → redirect to onboarding step 2 — AC8
12. Tray menu has correct items pointing to correct URLs — AC9
13. Hosted settings AI keys section is read-only — AC10
14. Pause/resume command flows web→server→daemon end-to-end — AC11

**Critical-path regression sweep:**
15. Daemon still generates content (4-phase agent runs, agent_draft populated) — AC12
16. Daemon still posts to LinkedIn/FB/Reddit on schedule — AC13
17. Profile scraping still functional — AC14
18. Metric scraping + billing pipeline unchanged — AC15
19. Hosted /user/* dashboard surfaces (5 pages) all 200, no console errors — AC16
20. Server pytest suite 238/238 still green + new tests for drafts/commands/status (~15 new) — AC17

---

### AC1 — Alembic migration creates 3 new tables, 7/7 schema verified

| Field | Value |
|-------|-------|
| **Setup** | Repo at HEAD with `0002_add_drafts_commands_status.py` (or equivalent) migration file present. Empty test DB. |
| **Action** | `cd server && DATABASE_URL=postgresql://postgres:postgres@localhost:5432/amplifier_test alembic upgrade head; psql ... -c "\dt"` |
| **Expected** | `\dt` lists 17 tables (existing 14 + new 3: `draft`, `agent_command`, `agent_status`). Each new table has expected columns: `draft.{id, user_id, campaign_id, platform, text, image_url, image_local_path, quality_score, status, created_at}`; `agent_command.{id, user_id, type, payload, status, created_at, processed_at}`; `agent_status.{user_id PK, running, paused, last_seen, platform_health JSONB, ai_keys_configured, version}`. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac1_schema` |
| **Evidence** | `\dt` output; per-table `\d <name>` dumps |
| **Cleanup** | drop test DB |

### AC2 — Daemon polls + processes + acks commands within 90s

| Field | Value |
|-------|-------|
| **Setup** | Daemon running with `AMPLIFIER_UAT_INTERVAL_SEC=15`. Test user JWT loaded. Server clean of pending commands. |
| **Action** | Insert command via SQL: `INSERT INTO agent_command (user_id, type, payload, status) VALUES (1, 'force_poll', '{}', 'pending') RETURNING id;`. Capture id. Watch daemon log + DB. |
| **Expected** | Within 30s: daemon log contains `Received command #<id> type=force_poll`. Within 60s: command status = `processing` then `done`, `processed_at` populated. Daemon's `_force_poll_campaigns()` ran (visible in log). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac2_command_lifecycle` |
| **Evidence** | daemon log lines; SQL row before/after |
| **Cleanup** | reset agent_command rows |

### AC3 — Daemon uploads drafts to server within 30s of generation

| Field | Value |
|-------|-------|
| **Setup** | Daemon running. Server `Draft` table empty for test user. Local `agent_draft` empty for test campaign. |
| **Action** | Trigger generation: insert command type `generate_content` for the test campaign. Wait up to 5 min. |
| **Expected** | Within 5 min: local `agent_draft` has 3 rows (LI/FB/Reddit). Within 30s after: server `Draft` table has 3 matching rows with same `text`, `platform`, `campaign_id`. Each local row's new `synced` column = 1. Image_url on server points to a valid storage URL or matches the local path. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac3_draft_upload` |
| **Evidence** | local + server SQL row dumps; HTTP request log |
| **Cleanup** | delete drafts on both sides |

### AC4 — Old Flask routes return 404, only 5 new routes respond on localhost:5222

| Field | Value |
|-------|-------|
| **Setup** | Local FastAPI running on `127.0.0.1:5222`. |
| **Action** | `for p in /dashboard /campaigns /posts /earnings /settings /login /onboarding /auth/callback /connect /keys /drafts /drafts/1 /healthz; do echo $p $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5222$p); done` |
| **Expected** | First 7 paths return 404. Last 5 paths return 200 (or 302 if auth required). `/healthz` returns 200. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac4_route_inventory` |
| **Evidence** | curl status code list |
| **Cleanup** | none |

### AC5 — Hosted /user/campaigns links out to localhost:5222/drafts/{id}

| Field | Value |
|-------|-------|
| **Setup** | Test user logged in at `https://api.pointcapitalis.com/user/login`. Active campaign exists. |
| **Action** | DevTools MCP: navigate `/user/campaigns/<id>` → grep snapshot for `localhost:5222/drafts/`. |
| **Expected** | Page contains an "Open in Desktop App" button with `href="http://localhost:5222/drafts/<id>"`. NO inline draft editor on the hosted page. (Already verified in Task #66 AC8 — re-verify here for regression.) |
| **Automated** | yes |
| **Automation** | DevTools MCP + `pytest scripts/uat/uat_task67.py::test_ac5_no_inline_drafts` |
| **Evidence** | snapshot text; href value |
| **Cleanup** | none |

### AC6 — Local draft review works offline

| Field | Value |
|-------|-------|
| **Setup** | Local FastAPI running. Local `agent_draft` has ≥3 unposted rows. **Server unreachable** — block via firewall: `sudo iptables -A OUTPUT -d api.pointcapitalis.com -j REJECT` (or kill local uvicorn if testing against 127.0.0.1:8000). |
| **Action** | DevTools MCP: navigate `http://localhost:5222/drafts` → take_snapshot. |
| **Expected** | Page renders within 3s with all 3 drafts visible. Image carousel, text content, approve/reject buttons. No spinner stuck on "Loading…". Console may show network errors for the unreachable server (acceptable). |
| **Automated** | partial — manual confirmation that drafts render |
| **Automation** | `scripts/uat/uat_task67.py::test_ac6_offline_drafts` (DevTools MCP automation) |
| **Evidence** | snapshot; screenshot |
| **Cleanup** | restore network: `sudo iptables -D OUTPUT -d api.pointcapitalis.com -j REJECT` |

### AC7 — Local Approve writes to local DB <200ms

| Field | Value |
|-------|-------|
| **Setup** | Server reachable. Local FastAPI on `localhost:5222`. Test draft id=42 with `approved=0`. |
| **Action** | DevTools MCP: navigate `http://localhost:5222/drafts` → click Approve on draft 42 → measure time from click to UI badge change. Inspect local DB: `SELECT approved FROM agent_draft WHERE id=42`. |
| **Expected** | UI updates "Approved" badge within 200ms. Local row `approved=1` within 200ms. Server sync request fires in background within 5s (not blocking). If server sync fails (kill server first), local state remains `approved=1`. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac7_local_first_approve` |
| **Evidence** | timing screenshots; local SQL row; server log of background sync |
| **Cleanup** | reset draft approved=0 |

### AC8 — Auth handoff: register → localhost callback → encrypted JWT → onboarding step 2

| Field | Value |
|-------|-------|
| **Setup** | Local daemon running. Local DB has no JWT in settings. |
| **Action** | DevTools MCP: navigate `https://api.pointcapitalis.com/register?agent=true` → fill new email → submit → wait for redirect chain. Inspect local DB: `SELECT value FROM settings WHERE key='jwt'`. |
| **Expected** | After submit: 302 to `localhost:5222/auth/callback?token=...`. Within 2s: 302 to `https://api.pointcapitalis.com/onboarding/step2`. Local DB has encrypted JWT (length > 100, NOT plaintext base64). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac8_auth_handoff` |
| **Evidence** | redirect chain dump; SQL row showing encrypted blob |
| **Cleanup** | delete throwaway user from server; clear local jwt |

### AC9 — Tray menu has 6 items, each opens correct URL

| Field | Value |
|-------|-------|
| **Setup** | Daemon running with tray icon visible. |
| **Action** | Right-click tray → take screenshot of menu → manually click each item. |
| **Expected** | Menu has 6 items: "Open Dashboard", "Review Drafts", "Connect Platforms", "Settings", "Pause/Resume", "Quit". Each opens the correct URL: dashboard → `https://api.pointcapitalis.com/user/`; drafts → `localhost:5222/drafts`; connect → `localhost:5222/connect`; settings → `localhost:5222/keys`; pause/resume toggles; quit terminates. |
| **Automated** | partial — manual y/n on screenshot of menu items |
| **Automation** | `scripts/uat/uat_task67.py::test_ac9_tray_menu` (verifies items in tray.py source) + manual screenshot review |
| **Evidence** | tray screenshot; per-action behavior log |
| **Cleanup** | none |

### AC10 — Hosted settings AI keys section is read-only

| Field | Value |
|-------|-------|
| **Setup** | Test user with both Gemini + Mistral keys configured locally. |
| **Action** | DevTools MCP: navigate `https://api.pointcapitalis.com/user/settings` → grep snapshot for `<input` elements in the AI keys section. |
| **Expected** | NO `<input>` elements within the AI keys card. Status badges show "Gemini: configured", "Mistral: configured", "Groq: not configured". A button "Manage Keys (Desktop App)" present, links to `localhost:5222/keys`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + `pytest scripts/uat/uat_task67.py::test_ac10_settings_readonly` |
| **Evidence** | snapshot HTML excerpt of AI keys card |
| **Cleanup** | none |

### AC11 — Pause/resume command flows web→server→daemon

| Field | Value |
|-------|-------|
| **Setup** | Daemon running with `AMPLIFIER_UAT_INTERVAL_SEC=15`. Test user logged in to hosted dashboard. Capture initial daemon `paused=False` from `agent_status`. |
| **Action** | DevTools MCP: navigate `https://api.pointcapitalis.com/user/settings` → click "Pause Agent" → wait up to 90s → poll `agent_status` SQL. |
| **Expected** | Within 30s: server has new `agent_command` row type=`pause_agent` status=`pending`. Within 90s: command status=`done`, daemon log contains `Pausing agent`. `agent_status.paused = True`. Hosted dashboard updates via SSE: "Status: Paused". Click "Resume Agent" → reverse flow within 90s. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac11_pause_resume_e2e` |
| **Evidence** | per-stage SQL rows; daemon log timeline; SSE event |
| **Cleanup** | resume agent |

### AC12 — REGRESSION: 4-phase content agent still works

| Field | Value |
|-------|-------|
| **Setup** | Test campaign + accepted assignment. `agent_research` + `agent_draft` empty for this campaign. |
| **Action** | `python scripts/background_agent.py --once --campaign-id <id> 2>&1 \| tee data/uat/task67_ac12.log` |
| **Expected** | Within 5 min: log has 4 Phase complete lines. agent_draft has 3 rows. (Mirrors Task #66 AC24 — verifies daemon-side migration didn't break content agent.) |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task67.py::test_ac12_content_agent_regression` |
| **Evidence** | log excerpt; SQL rows |
| **Cleanup** | none |

### AC13 — REGRESSION: Real LinkedIn post via JSON engine

| Field | Value |
|-------|-------|
| **Setup** | LinkedIn session valid. Approved draft from AC12. `AMPLIFIER_UAT_POST_NOW=1`. |
| **Action** | `python scripts/post.py --slot 1`. Wait up to 3 min. |
| **Expected** | Post appears on LinkedIn. Local `agent_draft.status=posted`, `post_url` populated. Server `posts` table has the row + `Draft.status=posted` synced. (Mirrors Task #66 AC25 — verifies posting still works through the new draft sync layer.) |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task67.py::test_ac13_post_regression` (DB checks) + manual y/n |
| **Evidence** | LinkedIn URL; SQL rows on both sides |
| **Cleanup** | DELETE LinkedIn post via `python scripts/uat/delete_post.py --url <url>` |

### AC14 — REGRESSION: Profile scraping still functional

| Field | Value |
|-------|-------|
| **Setup** | LinkedIn / FB / Reddit profiles connected. Disconnect Reddit by deleting `profiles/reddit-profile/` so re-scrape is forced. |
| **Action** | Reconnect Reddit via local `localhost:5222/connect` → click "Connect Reddit" → log in. |
| **Expected** | Playwright opens visible browser. Login completes. Profile scraper runs (3-tier pipeline visible in daemon log). `scraped_profile` row inserted with `follower_count`, `bio`, `niches`, `recent_posts` populated. (Verifies the new local FastAPI didn't break profile scraping integration.) |
| **Automated** | partial — manual login |
| **Automation** | `scripts/uat/uat_task67.py::test_ac14_profile_scrape_regression` |
| **Evidence** | scraped_profile SQL row; daemon log |
| **Cleanup** | none |

### AC15 — REGRESSION: Metric scrape → billing → payout pending

| Field | Value |
|-------|-------|
| **Setup** | Posted LI post from AC13. |
| **Action** | `python scripts/utils/metric_scraper.py --post-url <url>` (one-shot). Then `curl -s https://api.pointcapitalis.com/api/users/me/earnings -H "Authorization: Bearer $TOKEN"`. |
| **Expected** | metric row added; payout row pending; earnings.pending_balance > 0. (Mirrors Task #66 AC26.) |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task67.py::test_ac15_metric_billing_regression` |
| **Evidence** | scraper log; SQL rows; earnings JSON |
| **Cleanup** | void test payout |

### AC16 — REGRESSION: Hosted /user/* surfaces still 200 + no console errors

| Field | Value |
|-------|-------|
| **Setup** | Test user logged in. |
| **Action** | DevTools MCP: visit `/user/`, `/user/campaigns`, `/user/campaign_detail/<id>`, `/user/posts`, `/user/earnings`, `/user/settings`. Per page: `list_console_messages`. |
| **Expected** | 6/6 pages return 200. Zero console errors per page (Tailwind CDN warning OK). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task67.py::test_ac16_user_pages_regression` |
| **Evidence** | per-page status + console messages |
| **Cleanup** | none |

### AC17 — REGRESSION: pytest 238/238 + ~15 new tests for drafts/commands/status

| Field | Value |
|-------|-------|
| **Setup** | Repo at HEAD post-#67 merge. |
| **Action** | `pytest tests/ -v 2>&1 \| tee data/uat/task67_ac17_pytest.log` |
| **Expected** | ≥253 tests passing (238 baseline + ~15 new). Zero `FAILED`/`ERROR`. New tests cover: draft sync conflict resolution, command queue lifecycle, status push debounce, auth handoff JWT decryption, local draft offline-first writes. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest log |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #67

Task #67 is marked done in task-master ONLY when:
1. AC1–AC17 all PASS (AC6/AC9/AC13/AC14 manual y/n confirmations from user)
2. pytest suite ≥253/253 passing
3. Zero `error|exception|traceback` in `journalctl -u amplifier-web` during UAT window
4. Daemon log clean of unhandled exceptions for the full UAT run
5. Local FastAPI process stable (no crashes during AC4–AC11)
6. UAT report `docs/uat/reports/task-67-<yyyy-mm-dd>-<hhmm>.md` written with all evidence
7. All cleanup steps completed (test users deleted, LinkedIn UAT posts deleted, drafts cleared)
8. Server `/health` returns 200 at end; both `amplifier-web` + `amplifier-worker` `active`
