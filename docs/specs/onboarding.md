# Task #75 — Web Onboarding Flow

**Status:** pending  
**Branch:** flask-user-app  

New user registration and 4-step onboarding flow that bridges the hosted server (`https://api.pointcapitalis.com`) with the local daemon at `localhost:5222`. A user arrives at `/register?agent=true`, fills the form, and is walked through: account creation → platform connection → API keys → campaign discovery.

**New routes required** (not yet built — spec describes target behaviour):

| Route | Surface | Purpose |
|-------|---------|---------|
| `GET /register` | Hosted server | Registration form (with ToS checkbox) |
| `POST /register` | Hosted server | Validate + create account + redirect |
| `GET /user/onboarding` | Hosted server | Legacy alias → redirect to step 2 |
| `GET /user/onboarding/step2` | Hosted server | Platform connection step |
| `GET /user/onboarding/step3` | Hosted server | API keys step (links to localhost:5222/keys) |
| `GET /user/onboarding/step4` | Hosted server | Final step / campaign discovery |

`POST /api/auth/register` (existing JSON API, `server/app/routers/auth.py:19`) is the backend that the new `/register` form submits to. The HTML route wraps it: on success it captures the JWT and redirects to `localhost:5222/auth/callback?token=<jwt>`.

---

## Features to verify end-to-end (Task #75)

1. Registration form renders with email/password fields and a checked-by-default ToS checkbox — AC1
2. Submitting without ToS checked returns a form-level 400 error (re-render with error message) — AC2
3. Valid submission creates user, issues JWT, and redirects to local daemon callback — AC3
4. Local `/auth/callback` stores the encrypted JWT and bounces to `/user/onboarding/step2` — AC4
5. Step 2 renders connected-platform list driven by SSE badge from `/sse/user/agent-status` — AC5
6. Connecting one platform via `localhost:5222/connect` triggers SSE badge update on step 2 — AC6
7. Step 3 renders and links out to `localhost:5222/keys` — AC7
8. Step 4 redirects authenticated user to `/user/campaigns` — AC8
9. `GET /user/onboarding` (legacy alias) redirects to step 2 — AC9
10. Duplicate email registration returns form-level 409 error — AC10
11. Abandoned flow: user can log in via `/user/login` and land on `/user/dashboard` — AC11
12. `/auth/callback` without a valid token returns HTTP 400 — AC12

---

## Verification Procedure — Task #75

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `curl https://api.pointcapitalis.com/health` → `{"status":"ok"}`.
- Local user app running on `:5222` with `AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF` NOT set (daemon present for main path ACs).
- Chrome DevTools MCP available (`mcp__chrome-devtools__*` tools).
- No prior `uat-task75-user@pointcapitalis.com` row in `users` table (confirmed by cleanup or fresh run).

### Test data setup

1. Confirm no existing test user (idempotent pre-check):
   ```bash
   curl -s https://api.pointcapitalis.com/api/auth/user/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"uat-task75-user@pointcapitalis.com","password":"uat-pass-75"}' \
     | python -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'detail' in d else 1)"
   ```
   If exit 1 (user already exists), run cleanup:
   ```bash
   python scripts/uat/cleanup_test_user.py --email uat-task75-user@pointcapitalis.com
   ```

2. Start local user app (background, port 5222):
   ```bash
   AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000 \
     python scripts/user_app.py > data/uat/user_app_75.log 2>&1 &
   echo $! > data/uat/user_app_75.pid
   ```
   Wait up to 10s for `curl http://localhost:5222/healthz` → `{"status":"ok"}`.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF=1` | When set, `/register` stores the JWT in a session cookie directly and skips the `localhost:5222/auth/callback` redirect. Allows onboarding UAT to run against the hosted server without a paired daemon (CI-safe path). Default: unset (daemon-redirect path). | AC3 fallback; AC12 |
| `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` | Forces SSE heartbeat from 30s → 2s so AC5/AC6 can verify live badge update within 5s. | AC5, AC6 |

---

### AC1 — GET /register?agent=true renders the registration form

| Field | Value |
|-------|-------|
| **Setup** | Chrome DevTools MCP fresh page. No `user_token` cookie. |
| **Action** | `new_page("https://api.pointcapitalis.com/register?agent=true")` → `take_snapshot` → `take_screenshot("data/uat/screenshots/75_ac1_register.png")`. |
| **Expected** | Page title contains "Create Account" or "Register". Form contains: email input, password input, ToS checkbox (default unchecked or checked per UX), link to `/terms` and `/privacy` inline. No console errors. URL contains `?agent=true` (form retains the param for the POST). |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP sequence above |
| **Evidence** | `data/uat/screenshots/75_ac1_register.png`; snapshot text dump confirming form fields present |
| **Cleanup** | none |

---

### AC2 — POST /register rejects submission without ToS accepted

| Field | Value |
|-------|-------|
| **Setup** | Registration form loaded (AC1 state). |
| **Action** | `take_snapshot` → fill email `uat-task75-user@pointcapitalis.com` and password `uat-pass-75` → ensure ToS checkbox is UNCHECKED → click "Create Account" button → `take_snapshot` after response. |
| **Expected** | Page does NOT navigate away from `/register`. Form re-renders with an inline error message matching `(?i)(must accept|terms of service|required)`. HTTP response status 400 (verify via `list_network_requests` — the POST to `/register` or `/api/auth/register` returns 4xx). No JWT cookie set. No `users` row created (verify: `curl .../api/auth/user/login` with those creds returns 401). |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot of error state; network log showing 4xx on POST; login probe returning 401 |
| **Cleanup** | none |

---

### AC3 — POST /register creates user and redirects to local /auth/callback

| Field | Value |
|-------|-------|
| **Setup** | Registration form loaded. Local daemon running on `:5222`. |
| **Action** | Fill email `uat-task75-user@pointcapitalis.com`, password `uat-pass-75` → check ToS checkbox → click "Create Account" → wait for navigation. |
| **Expected** | Browser navigates to `http://localhost:5222/auth/callback?token=<jwt>` (with `agent=true` path). Within 3s local app receives the token, stores it, and redirects to `https://api.pointcapitalis.com/user/onboarding` (or `/user/onboarding/step2`). New `users` row exists: `python -c "import httpx; r=httpx.post('https://api.pointcapitalis.com/api/auth/user/login', json={'email':'uat-task75-user@pointcapitalis.com','password':'uat-pass-75'}); print(r.status_code)"` → `200`. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | URL transition log; login probe returning 200; screenshot of landing on onboarding step 2 |
| **Cleanup** | none (user kept for subsequent ACs) |

---

### AC4 — Local /auth/callback stores encrypted JWT and redirects to /user/onboarding

| Field | Value |
|-------|-------|
| **Setup** | Obtain fresh JWT: `TOKEN=$(curl -s -X POST https://api.pointcapitalis.com/api/auth/user/login -H 'Content-Type: application/json' -d '{"email":"uat-task75-user@pointcapitalis.com","password":"uat-pass-75"}' \| python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")`. |
| **Action** | `new_page("http://localhost:5222/auth/callback?token=$TOKEN")` → wait for redirect → capture final URL. Verify local DB: `python -c "from scripts.utils.local_db import get_setting; v=get_setting('jwt'); print(bool(v) and ':' in v)"`. |
| **Expected** | Final URL is `https://api.pointcapitalis.com/user/onboarding` (or `/user/onboarding/step2`). Local DB assertion prints `True` (JWT stored in encrypted `iv:ciphertext` format). Calling `/auth/callback` without `?token=` returns HTTP 400. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP + python one-liner |
| **Evidence** | URL transition; encrypted-storage assertion stdout; 400 on tokenless call |
| **Cleanup** | none — JWT needed for subsequent ACs |

---

### AC5 — /user/onboarding/step2 renders platform list with SSE-driven badge

| Field | Value |
|-------|-------|
| **Setup** | Logged in (user_token cookie set via AC3/AC4). Background daemon running with `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000`. |
| **Action** | `navigate_page("https://api.pointcapitalis.com/user/onboarding/step2")` → `take_snapshot` → wait 5s → `take_snapshot` again → `list_network_requests` filtered to `/sse/user/agent-status`. |
| **Expected** | Page renders a list of platforms (LinkedIn, Facebook, Reddit — X must NOT appear as a connectable option). Each platform shows a connection status badge. Network log shows an open SSE connection to `/sse/user/agent-status`. After 5s (2 heartbeats at 2000ms), badge text or class has refreshed (platform health updated from daemon). Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | before/after snapshots; network log showing SSE stream; screenshot `data/uat/screenshots/75_ac5_step2.png` |
| **Cleanup** | none |

---

### AC6 — Connecting a platform via local /connect updates SSE badge on step 2

| Field | Value |
|-------|-------|
| **Setup** | Step 2 page open. Daemon running. At least one platform NOT connected (LinkedIn preferred). |
| **Action** | In a second tab: `new_page("http://localhost:5222/connect")` → `take_snapshot` → click "Connect LinkedIn" button → complete Playwright browser login (or verify session already exists and click succeeds) → on success close the tab. Return to step 2 tab. Wait up to 10s. `take_snapshot`. |
| **Expected** | Within 10s the LinkedIn platform badge on step 2 page updates from "Not connected" to "Connected" (or equivalent green indicator), driven by the SSE channel. No full page reload required. Console: zero errors. |
| **Automated** | partial — DevTools MCP for page monitoring; Playwright for the actual platform connect action |
| **Automation** | Chrome DevTools MCP (observation); `scripts/login_setup.py linkedin` (connect action — requires manual 2FA step, flag as manual sub-step) |
| **Evidence** | before/after snapshots showing badge change; `data/uat/screenshots/75_ac6_step2_after_connect.png` |
| **Cleanup** | none — platform stays connected for subsequent tasks |

---

### AC7 — /user/onboarding/step3 renders and links to localhost:5222/keys

| Field | Value |
|-------|-------|
| **Setup** | Logged in. |
| **Action** | `navigate_page("https://api.pointcapitalis.com/user/onboarding/step3")` → `take_snapshot`. Locate the link or button pointing to `http://localhost:5222/keys`. |
| **Expected** | Page renders a step 3 heading ("Configure API Keys" or similar). Contains a visible link or CTA button with `href` containing `localhost:5222/keys`. Link text is human-readable (e.g., "Configure API keys"). Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | snapshot text confirming link href; screenshot `data/uat/screenshots/75_ac7_step3.png` |
| **Cleanup** | none |

---

### AC8 — /user/onboarding/step4 redirects authenticated user to /user/campaigns

| Field | Value |
|-------|-------|
| **Setup** | Logged in (valid `user_token` cookie). |
| **Action** | `navigate_page("https://api.pointcapitalis.com/user/onboarding/step4")` → wait for navigation → capture final URL. |
| **Expected** | Final URL is `https://api.pointcapitalis.com/user/campaigns`. Page renders the campaigns page (Open Invitations tab visible). HTTP 302 redirect chain visible in `list_network_requests`. Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | URL transition; network log showing 302; screenshot of campaigns page |
| **Cleanup** | none |

---

### AC9 — GET /user/onboarding (legacy alias) redirects to step 2

| Field | Value |
|-------|-------|
| **Setup** | Logged in. |
| **Action** | `navigate_page("https://api.pointcapitalis.com/user/onboarding")` → wait for navigation → capture final URL. |
| **Expected** | Final URL is `https://api.pointcapitalis.com/user/onboarding/step2`. HTTP 302 in network log. Page renders the step 2 platform list. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | URL transition; network log |
| **Cleanup** | none |

---

### AC10 — Duplicate email registration returns 409 / form error

| Field | Value |
|-------|-------|
| **Setup** | `uat-task75-user@pointcapitalis.com` already exists (created in AC3). Fresh registration form: `new_page("https://api.pointcapitalis.com/register")`. |
| **Action** | Fill same email `uat-task75-user@pointcapitalis.com` + any password + check ToS → click "Create Account". |
| **Expected** | Page re-renders form with error message matching `(?i)(already registered|email.*taken|account.*exists)`. HTTP 4xx response on POST (400 or 409). No new `users` row created. No JWT issued. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot of error; network log showing 4xx |
| **Cleanup** | none |

---

### AC11 — Abandoned-flow user can log back in and reach /user/dashboard

| Field | Value |
|-------|-------|
| **Setup** | `uat-task75-user@pointcapitalis.com` account exists. No `user_token` cookie (incognito or cleared). |
| **Action** | `new_page("https://api.pointcapitalis.com/user/login")` → fill email/password → click "Sign in" → wait for navigation. |
| **Expected** | Redirect to `/user/dashboard`. Dashboard renders (balance card, agent status badge visible). No redirect back to onboarding (user account is complete even if onboarding steps were not finished). `user_token` cookie set. Zero console errors. |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP |
| **Evidence** | screenshot `data/uat/screenshots/75_ac11_dashboard.png`; cookie dump |
| **Cleanup** | none |

---

### AC12 — /auth/callback without valid token returns 400

| Field | Value |
|-------|-------|
| **Setup** | Local daemon running on `:5222`. |
| **Action** | `curl -i http://localhost:5222/auth/callback` (no `?token=` param). Also test: `curl -i "http://localhost:5222/auth/callback?token=notavalidjwt"`. |
| **Expected** | First call: HTTP 400, body contains `"Missing token parameter"`. Second call: HTTP 400, body contains error indicating invalid/malformed token (NOT a 500 or unhandled exception). In both cases no JWT is written to local DB. |
| **Automated** | yes |
| **Automation** | curl + `python -c "from scripts.utils.local_db import get_setting; print(get_setting('jwt'))"` (must not have changed) |
| **Evidence** | curl output (status + body); DB assertion showing JWT unchanged |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #75

Task #75 is marked done in task-master ONLY when:
1. AC1–AC12 all PASS
2. AC6 manual sub-step confirmed: user says `y` on "Does the badge update to Connected within 10s?" prompt
3. No `error|exception|traceback` lines in `data/uat/user_app_75.log` during the UAT window
4. No `audit_log` rows with `severity='error'` created during the window
5. `/health` returns 200 at end of run
6. All cleanup completed: `python scripts/uat/cleanup_test_user.py --email uat-task75-user@pointcapitalis.com`
7. UAT report `docs/uat/reports/task-75-<yyyy-mm-dd>.md` written with all screenshots embedded

**Cleanup command** (run unconditionally after UAT, even on partial fail):
```bash
python scripts/uat/cleanup_test_user.py --email uat-task75-user@pointcapitalis.com
kill $(cat data/uat/user_app_75.pid) 2>/dev/null || true
```

**Helper to spec** (not yet written — spec here for implementer):
`scripts/uat/cleanup_test_user.py --email <email>` — DELETE the `users` row by email and cascade-delete all associated rows (`campaign_assignments`, `posts`, `metrics`, `payouts`, `penalties`, `agent_status`, `agent_commands`). Refuse to delete any email that does NOT match the `uat-task*@pointcapitalis.com` pattern (safety guard).
