# Task #76 — Pause/Resume Agent + Dashboard Agent Visibility

**Status:** pending  
**Branch:** flask-user-app  

Exposes daemon control (pause/resume) from the hosted creator dashboard at `/user/settings`, and adds live agent-health widgets to `/user/dashboard`. No new daemon logic required — `pause_agent` and `resume_agent` handlers already exist in `scripts/background_agent.py:892-896`. This task is purely UI + server-side command routing.

**New UI elements required:**

| Surface | Element | Route |
|---------|---------|-------|
| `/user/settings` | "Pause Agent" / "Resume Agent" button (toggle based on current `agent_status.paused`) | POST to new `/user/settings/pause-agent` / `/user/settings/resume-agent` route |
| `/user/dashboard` | "Last seen X minutes ago" indicator | reads `agent_status.last_seen` |
| `/user/dashboard` | Per-platform health badges (green/red) | reads `agent_status.platform_health` JSON |
| `/user/dashboard` | "X drafts ready" widget with count | queries `Draft.status='pending'` for this user |

**Server-side flow:**
1. User clicks "Pause Agent" on `/user/settings`
2. Server creates an `AgentCommand` row with `type='pause_agent'` (model: `server/app/models/agent_command.py:9-18`)
3. Daemon's `process_server_commands` loop picks it up and calls `agent.pause()` (`scripts/background_agent.py:893`)
4. Daemon next heartbeat sets `agent_status.paused=True` via `POST /api/agent/status`
5. SSE stream `/sse/user/agent-status` broadcasts update → settings page badge flips to "Paused"

---

## Features to verify end-to-end (Task #76)

1. Pause/Resume button renders on `/user/settings` and reflects current paused state — AC1
2. Clicking Pause creates an `AgentCommand` row with `type='pause_agent'` — AC2
3. Daemon picks up the command within 30s (with `AMPLIFIER_UAT_INTERVAL_SEC=15`) and sets `agent_status.paused=True` — AC3
4. Settings page badge updates to "Paused" via SSE within 5s of daemon confirming — AC4
5. Clicking Resume reverses: `resume_agent` command created, daemon clears paused flag, badge updates — AC5
6. Dashboard shows "Last seen X minutes ago" from `agent_status.last_seen` — AC6
7. Dashboard shows per-platform health badges (green/red) from `agent_status.platform_health` — AC7
8. Dashboard shows "X drafts ready" widget with count from `Draft.status='pending'`, links to `localhost:5222/drafts` — AC8

---

## Verification Procedure — Task #76

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Test user `uat-task76-user@pointcapitalis.com` with password `uat-pass-76`. Region `US`, ToS accepted, mode `semi_auto`.
- Local daemon (`scripts/background_agent.py`) running in background, registered to the test user, with `AMPLIFIER_UAT_INTERVAL_SEC=15` set.
- Daemon has sent at least one heartbeat (verify: `agent_status` row exists for the test user — `python -c "from scripts.utils.local_db import get_setting; import sqlite3; c=sqlite3.connect('data/local.sqlite'); print(c.execute('SELECT paused FROM agent_status LIMIT 1').fetchone())"`).
- Chrome DevTools MCP available.

### Test data setup

1. **Seed test user** (if not exists):
   ```bash
   curl -s -X POST https://api.pointcapitalis.com/api/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"uat-task76-user@pointcapitalis.com","password":"uat-pass-76","accept_tos":true}' \
     | python -c "import sys,json; d=json.load(sys.stdin); print('created:', 'access_token' in d)"
   ```

2. **Start daemon** with shortened poll interval:
   ```bash
   AMPLIFIER_UAT_INTERVAL_SEC=15 \
     python scripts/background_agent.py \
       2>&1 > data/uat/agent_76.log &
   echo $! > data/uat/agent_76.pid
   ```
   Wait 20s for first heartbeat: `grep -m1 "heartbeat" data/uat/agent_76.log`

3. **Seed a pending draft** so the "X drafts ready" widget has data (AC8):
   ```bash
   python -c "
   from scripts.utils.local_db import add_draft
   add_draft(campaign_id=1, platform='linkedin', draft_text='UAT draft', status='pending')
   print('draft seeded')
   "
   ```

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_INTERVAL_SEC=15` | Shortens daemon command-poll interval from 60s → 15s, and SSE-push interval from 30s → 15s. So pause/resume commands are processed within 30s wall-clock. | AC3, AC5 |
| `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` | Forces SSE heartbeat from 30s → 2s so AC4 badge update verifies within 5s. | AC4, AC5 |

---

### AC1 — Pause Agent button renders on /user/settings reflecting current state

| Field | Value |
|-------|-------|
| **Setup** | Daemon running, NOT paused. `user_token` cookie set for test user. |
| **Action** | `new_page("https://api.pointcapitalis.com/user/settings")` → `take_snapshot` → `take_screenshot("data/uat/screenshots/76_ac1_settings.png")`. Search snapshot for pause-related text. |
| **Expected** | Page renders a "Pause Agent" button (or toggle) visible in the settings page. Button text matches `(?i)(pause agent\|pause daemon\|pause automation)`. The button is NOT disabled. Agent status section shows `(?i)(running\|active\|online)` badge (since daemon is running). Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot; snapshot text showing button and status |
| **Cleanup** | none |

---

### AC2 — Clicking Pause creates AgentCommand row with type='pause_agent'

| Field | Value |
|-------|-------|
| **Setup** | Settings page loaded (AC1 state). Capture `agent_commands` row count before: `python -c "import sqlite3; c=sqlite3.connect('data/local.sqlite'); print(c.execute('SELECT COUNT(*) FROM agent_commands').fetchone())"` (or via server DB). |
| **Action** | `take_snapshot` → find UID of "Pause Agent" button → `click(uid)` → wait 2s → `take_snapshot`. |
| **Expected** | Server `agent_commands` table has +1 row with `type='pause_agent'`, `status='pending'`, `user_id=<test_user_id>`. Verify: `curl -s -H "Authorization: Bearer $TOKEN" https://api.pointcapitalis.com/api/agent/commands | python -c "import sys,json; cmds=json.load(sys.stdin); print([c for c in cmds if c['type']=='pause_agent' and c['status']=='pending'])"` — list is non-empty. UI shows a loading or "Pausing..." state while command is pending. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP + curl |
| **Evidence** | snapshot of button state; API response showing pending command |
| **Cleanup** | none — command must stay pending for AC3 |

---

### AC3 — Daemon picks up pause command within 30s and sets agent_status.paused=True

| Field | Value |
|-------|-------|
| **Setup** | AC2 passed. Daemon running with `AMPLIFIER_UAT_INTERVAL_SEC=15`. |
| **Action** | Wait up to 30s. Watch daemon log: `tail -f data/uat/agent_76.log | grep -m1 "pause"`. Then verify server state: `curl -s -H "Authorization: Bearer $TOKEN" https://api.pointcapitalis.com/api/agent/status`. |
| **Expected** | Within 30s: daemon log contains line matching `(?i)(pause_agent|paused|agent paused)`. Server `GET /api/agent/status` returns `{"paused": true, ...}`. The `agent_commands` row now has `status='done'`. |
| **Automated** | yes |
| **Automation** | log grep + curl |
| **Evidence** | log line; API status response JSON; agent_commands row dump |
| **Cleanup** | none |

---

### AC4 — Settings badge updates to "Paused" via SSE within 5s

| Field | Value |
|-------|-------|
| **Setup** | AC3 passed. Daemon reports `paused=True`. Settings page still open (or re-navigate). `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000`. |
| **Action** | Navigate to `/user/settings`. Wait 5s. `take_snapshot`. Check `list_network_requests` for SSE stream activity. |
| **Expected** | Agent status badge text on settings page matches `(?i)(paused|stopped|inactive)`. SSE stream `/sse/user/agent-status` still active in network log (connection not closed). No full page reload — badge update driven by SSE event. Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot `data/uat/screenshots/76_ac4_settings_paused.png`; network log showing SSE |
| **Cleanup** | none |

---

### AC5 — Clicking Resume reverses state: badge returns to running

| Field | Value |
|-------|-------|
| **Setup** | AC4 passed. Settings page showing "Paused" badge. `AMPLIFIER_UAT_INTERVAL_SEC=15` and `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000`. |
| **Action** | `take_snapshot` → find UID of "Resume Agent" button (should now be visible, replacing Pause) → `click(uid)` → wait 30s → `take_snapshot`. Verify server: `curl -s .../api/agent/status` → `paused` field. |
| **Expected** | `resume_agent` command created: server `agent_commands` has +1 row `type='resume_agent'`. Within 30s: daemon processes it, `agent_status.paused=False`. Settings badge returns to `(?i)(running|active|online)`. `list_network_requests` shows no 5xx. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP + curl |
| **Evidence** | before/after screenshots; API status response showing `paused: false` |
| **Cleanup** | none |

---

### AC6 — Dashboard shows "Last seen X minutes ago" from agent_status.last_seen

| Field | Value |
|-------|-------|
| **Setup** | Daemon running (resumed per AC5). At least 1 heartbeat sent within the last 2 minutes. |
| **Action** | `navigate_page("https://api.pointcapitalis.com/user/dashboard")` → `take_snapshot` → `take_screenshot("data/uat/screenshots/76_ac6_dashboard.png")`. |
| **Expected** | Dashboard contains a visible "Last seen" or "Agent last seen" indicator. Text matches a relative-time pattern such as `(?i)(last seen \d+ (second|minute)|just now|seconds? ago|minutes? ago)`. The value is within the last 5 minutes (not "hours ago" — daemon was just running). Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot; snapshot text showing the relative-time string |
| **Cleanup** | none |

---

### AC7 — Dashboard shows per-platform health badges from agent_status.platform_health

| Field | Value |
|-------|-------|
| **Setup** | Dashboard loaded (AC6 state). Daemon has reported `platform_health` with at least LinkedIn/Facebook/Reddit entries. |
| **Action** | `take_snapshot` of the platform health section. |
| **Expected** | Dashboard renders 3 platform health badges for: LinkedIn, Facebook, Reddit. Each badge shows either a green (connected/healthy) or red (disconnected/error) indicator. X must NOT appear as an active platform badge. Badge data is sourced from `agent_status.platform_health` JSON (verify: `curl .../api/agent/status` returns `platform_health` with those keys). |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot showing health badges; API status JSON dump showing `platform_health` keys |
| **Cleanup** | none |

---

### AC8 — Dashboard shows "X drafts ready" widget with count and link to localhost:5222/drafts

| Field | Value |
|-------|-------|
| **Setup** | Dashboard loaded. At least 1 `Draft` row with `status='pending'` exists for the test user (seeded in test data setup). |
| **Action** | `take_snapshot` of the drafts widget area. Inspect the widget's link `href` attribute: `evaluate_script("document.querySelector('a[href*=\"localhost:5222/drafts\"]')?.href")`. |
| **Expected** | Dashboard shows a widget with text matching `(?i)(\d+ draft(s)? ready\|draft(s)? pending\|draft(s)? await)` — count >= 1. Widget contains an `<a>` element with `href` containing `localhost:5222/drafts`. (Note: the test browser may not be able to navigate to localhost — spec only verifies the href attribute, not that the link resolves. This is intentional per the Phase D architecture split.) Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot `data/uat/screenshots/76_ac8_drafts_widget.png`; `evaluate_script` output showing href |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #76

Task #76 is marked done in task-master ONLY when:
1. AC1–AC8 all PASS
2. No `error|exception|traceback` lines in `data/uat/agent_76.log` during the UAT window
3. No `audit_log` rows with `severity='error'` during the window
4. All cleanup completed: `kill $(cat data/uat/agent_76.pid) 2>/dev/null || true`
5. Server `/health` returns 200 at end of run
6. UAT report `docs/uat/reports/task-76-<yyyy-mm-dd>.md` written with all screenshots embedded

**Cleanup command** (run unconditionally after UAT, even on partial fail):
```bash
kill $(cat data/uat/agent_76.pid) 2>/dev/null || true
# Remove seeded test draft if it persists
python -c "
import sqlite3
c = sqlite3.connect('data/local.sqlite')
c.execute(\"DELETE FROM agent_draft WHERE draft_text='UAT draft'\")
c.commit()
print('cleanup done')
"
```
