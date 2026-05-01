# Pre-launch Comprehensive UAT — Specs & Verification

Phase E launch gate. Drives every page, every form, every button across the three user-facing surfaces (local user app, hosted creator dashboard, company dashboard, admin dashboard). Refuses to mark Task #74 done until every AC passes with zero console errors, zero 5xx responses, zero `severity=error` audit_log rows, and every screenshot embedded in the report.

**Tasks:** #74.1 (user app surface), #74.2 (company dashboard), #74.3 (admin dashboard)

**Scope deliberately wide.** Each sub-task ships its own Verification Procedure block. Run them sequentially: `/uat-task 74.1` → `/uat-task 74.2` → `/uat-task 74.3`. A FAIL on any sub-task halts the launch gate.

---

## Task #74.1 — User App Full Sweep

### What it covers

Two surfaces compose "the user app" after the Phase D split:

1. **Local creator app** at `http://localhost:5222` (slim FastAPI in `scripts/utils/local_server.py`) — 16 endpoints:
   - `GET /healthz`
   - `GET /auth/callback?token=...` (JWT handoff from hosted server)
   - `GET /connect` + `POST /connect/{platform}` (LinkedIn / Facebook / Reddit only — X must be hidden)
   - `GET /keys` + `POST /keys` + `POST /keys/test`
   - `GET /drafts` + `GET /drafts/{campaign_id}` + `GET /drafts/{draft_id}/image`
   - `POST /drafts/{draft_id}/approve|reject|restore|unapprove|edit` (HTMX swap)

2. **Hosted creator dashboard** at `https://api.pointcapitalis.com/user/*` (12 routes):
   - `GET /user/login` + `POST /user/login` + `GET /user/logout`
   - `GET /user/` + `GET /user/dashboard`
   - `GET /user/campaigns` + `GET /user/campaigns/_tab/{tab_name}` + `GET /user/campaigns/{id}`
   - `GET /user/posts`
   - `GET /user/earnings`
   - `GET /user/settings`
   - SSE: `GET /sse/user/agent-status` (cookie-auth)

### Features to verify end-to-end (Task #74.1)

1. Hosted login → JWT issued → cookie set → redirect to `/user/dashboard` — AC1
2. Dashboard renders balance, agent status, recent activity without console errors — AC2
3. Campaigns tab: Open Invitations / Active / Completed / Declined sub-tabs swap via HTMX, no full reload — AC3
4. Campaign detail page: posts table + metrics + decline-reason aggregate render — AC4
5. Posts page lists user's posts with platform, status, post URL, latest metric — AC5
6. Earnings page: summary cards + per-campaign breakdown + payout history + withdraw button gated correctly — AC6
7. Settings page: region, mode, ToS acceptance status visible; settings save persists — AC7
8. Local `/auth/callback?token=...` stores JWT and redirects to hosted onboarding — AC8
9. Local `/connect` page lists ONLY linkedin/facebook/reddit (X hidden by `filter_disabled`) — AC9
10. Local `/keys` saves encrypted, never echoes plaintext, "Test" button validates against provider — AC10
11. Local `/drafts` lists drafts grouped by campaign, draft card renders text + image — AC11
12. Local draft actions (approve/reject/restore/unapprove/edit) update local DB AND PATCH server draft — AC12
13. Local draft `GET /drafts/{id}/image` serves the actual image file (200 + correct content-type) — AC13
14. SSE `/sse/user/agent-status` heartbeat updates the dashboard agent badge in <5s (with `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000`) — AC14
15. Logout clears cookie AND local JWT — AC15
16. End-to-end real-post: approve a draft → background agent posts to LinkedIn → post URL captured → user app shows "Posted" status → cleanup deletes the post — AC16
17. Console + network hygiene: zero error-level console messages, zero 5xx network requests across full sweep — AC17

---

## Verification Procedure — Task #74.1

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Local Patchright + venv set up (`pip install -r requirements.txt && python -m patchright install chromium`).
- Test user `uat-user-74@uat.local` with password `uat-pass-74`. Region `US`, ToS accepted, mode `semi_auto`. Profile already onboarded with linkedin / facebook / reddit persistent profiles in `profiles/`.
- Local user app NOT yet running (the UAT will launch it). `data/local.db` exists (any prior run created it).
- Chrome DevTools MCP available (`mcp__chrome-devtools__*` tools).
- BYOK or env-var Gemini key in `data/local.db` settings (encrypted) so content gen path works.

### Test data setup

1. **Seed UAT campaign + invitation** (so campaigns/drafts pages have content):
   ```bash
   python scripts/uat/seed_campaign.py \
     --title "UAT-741 Comprehensive User-App Sweep" \
     --goal brand_awareness --tone casual \
     --brief "$(python -c "print('A simple desk organizer for remote workers. Made of bamboo. ' * 8)")" \
     --guidance "Mention you've been using it for a week. Be casual." \
     --company-urls "https://example.com" \
     --output-id-to data/uat/last_campaign_id.txt
   ```
2. **Force-accept the invitation** so the campaign appears in `/user/campaigns` Active tab:
   ```bash
   python scripts/uat/seed_campaign.py --accept-only --campaign-id $(cat data/uat/last_campaign_id.txt)
   ```
3. **Seed earnings fixture** (so the Earnings page has content for AC6):
   ```bash
   python scripts/uat/seed_stripe_fixtures.py \
     --user-email uat-user-74@uat.local \
     --user-available-balance-cents 1500 \
     --user-pending-balance-cents 800 \
     --output data/uat/earnings_fixture.json
   ```
   *(If the helper does not yet exist, create a one-off SQL insert via the existing `scripts/uat/conftest.py` factory and capture the IDs to `data/uat/earnings_fixture.json`.)*
4. **Start the local user app** in the background:
   ```bash
   AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000 \
     python scripts/user_app.py 2>&1 > data/uat/user_app.log &
   echo $! > data/uat/user_app.pid
   ```
   Wait up to 10s for `http://localhost:5222/healthz` → `{"status":"ok"}`.
5. **Start background agent in `--once` mode** (will exit after one cycle, generating drafts for AC11):
   ```bash
   AMPLIFIER_UAT_FORCE_DAY=1 \
   AMPLIFIER_UAT_INTERVAL_SEC=30 \
     python scripts/background_agent.py --once \
       --campaign-id $(cat data/uat/last_campaign_id.txt) \
       2>&1 | tee data/uat/agent.log
   ```

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` | Forces SSE agent-status heartbeat from 30s → 2s so AC14 verifies live update in <5s | AC14 |
| `AMPLIFIER_UAT_INTERVAL_SEC=30` | Shortens content-gen + cache TTLs so seed step 5 produces drafts within 60s | setup |
| `AMPLIFIER_UAT_FORCE_DAY=1` | Forces day_number=1 so brand_awareness LinkedIn draft is generated on first run | setup |
| `AMPLIFIER_UAT_POST_NOW=1` | Schedules approved drafts ~1min out instead of next slot — used by AC16 | AC16 |

---

### AC1 — Hosted login issues JWT cookie and redirects to dashboard

| Field | Value |
|-------|-------|
| **Setup** | DevTools MCP fresh page. No `user_token` cookie. |
| **Action** | `new_page("https://api.pointcapitalis.com/user/login")` → `take_snapshot` → fill email + password → click "Sign in" → `wait_for(text="Dashboard")`. Inspect cookies via `evaluate_script("document.cookie")`. |
| **Expected** | After submit: redirect to `/user/dashboard`. `document.cookie` contains `user_token=...` (HttpOnly cookie may or may not be visible — also verify via `list_network_requests` that the next page request sent `Cookie:` header). Page title contains "Dashboard". |
| **Automated** | yes |
| **Automation** | Chrome DevTools MCP sequence above |
| **Evidence** | `data/uat/screenshots/74_1_ac1_dashboard.png`; cookie dump; network log showing 302 redirect |
| **Cleanup** | none — stay logged in for AC2+ |

### AC2 — Dashboard loads with balance, agent status, recent activity, zero console errors

| Field | Value |
|-------|-------|
| **Setup** | AC1 succeeded. On `/user/dashboard`. |
| **Action** | `take_snapshot` of dashboard → `list_console_messages()` → `list_network_requests()` → `take_screenshot("data/uat/screenshots/74_1_ac2_dashboard.png")`. |
| **Expected** | DOM contains visible balance card (text matches `\$\d`). Agent status badge present (text in {`Connected`, `Idle`, `Posting`, `Generating`}). Recent activity list rendered (or empty state with copy, not raw "[]"). Console messages: zero with `level=error`. Network: zero 4xx/5xx for `/user/*` or `/sse/*` or `/api/*`. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot; console + network JSON dumps |
| **Cleanup** | none |

### AC3 — Campaigns tab swaps Open / Active / Completed / Declined via HTMX (no full reload)

| Field | Value |
|-------|-------|
| **Setup** | Logged in. Test campaign exists in Active. |
| **Action** | `navigate_page("/user/campaigns")` → `take_snapshot` → for each tab in `[invitations, active, completed, declined]`: click the tab pill → wait for HTMX swap → snapshot the visible list region. Inspect `list_network_requests` filter to `/_tab/`. |
| **Expected** | Each tab click fires exactly one network request to `/user/campaigns/_tab/{tab}` (HTMX partial). Active tab shows seeded UAT-741 campaign card. Completed/Declined empty states render explicit copy ("No completed campaigns yet" / similar), not raw blank. No full-page navigation (URL stays `/user/campaigns`, only fragment or no change). |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | per-tab snapshots; network request JSON showing 4 GETs to `/_tab/*` |
| **Cleanup** | none |

### AC4 — Campaign detail page renders posts table, metrics, decline-reason aggregate

| Field | Value |
|-------|-------|
| **Setup** | Logged in. Active tab visible. |
| **Action** | Click the UAT-741 campaign card → `wait_for(text="Campaign")` → `take_snapshot`. |
| **Expected** | Campaign title + brief render. Posts table present (may be empty with empty-state copy if no posts yet). Per-platform metric placeholders render. URL is `/user/campaigns/<id>`. Zero console errors. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | navigate back to `/user/campaigns` |

### AC5 — Posts page lists user's posts with platform / status / URL / latest metric

| Field | Value |
|-------|-------|
| **Setup** | Logged in. |
| **Action** | `navigate_page("/user/posts")` → `take_snapshot`. |
| **Expected** | Either a table of posts with columns {platform, status, post_url, last_metric_at, earnings_cents} OR an empty-state with copy ("No posts yet — approve a draft to start earning"). No raw JSON, no `undefined`, no broken `<img>`. Zero console errors. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC6 — Earnings page: summary cards, per-campaign, history, withdraw button gated correctly

| Field | Value |
|-------|-------|
| **Setup** | Earnings fixture seeded (available=$15, pending=$8). User has NO `stripe_account_id`. |
| **Action** | `navigate_page("/user/earnings")` → `take_snapshot`. Find the "Withdraw" button — click it. |
| **Expected** | Summary cards show: Total Earned, Available `$15.00`, Pending `$8.00`. Per-campaign breakdown lists at least the UAT-741 campaign. Payout history table present (may be empty). Withdraw button shows "Connect your bank account first" or is disabled with CTA — NOT a transfer attempt. No 5xx. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot before + after click; network dump showing zero `/api/payouts` POST |
| **Cleanup** | none |

### AC7 — Settings page: region/mode/ToS visible, save persists

| Field | Value |
|-------|-------|
| **Setup** | Logged in. |
| **Action** | `navigate_page("/user/settings")` → `take_snapshot` → change `mode` from `semi_auto` to `auto` (or whatever toggle is present) → click "Save" → reload page → `take_snapshot` again. |
| **Expected** | Initial snapshot shows region (`US`), mode (`semi_auto`), ToS accepted timestamp. After save + reload: mode shows `auto`. Server response 200; network log shows POST to `/user/settings` (or PATCH `/api/users/me`). |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | before/after screenshots; network log |
| **Cleanup** | revert mode to `semi_auto` |

### AC8 — Local `/auth/callback?token=...` stores JWT and redirects to hosted onboarding

| Field | Value |
|-------|-------|
| **Setup** | Local user app running on :5222. Use a synthetic token: `TOKEN=$(curl -s -X POST https://api.pointcapitalis.com/api/auth/user/login -H 'Content-Type: application/json' -d '{"email":"uat-user-74@uat.local","password":"uat-pass-74"}' \| jq -r .access_token)`. |
| **Action** | `new_page("http://localhost:5222/auth/callback?token=$TOKEN")` → wait for redirect → capture final URL. Verify local DB: `python -c "from scripts.utils.local_db import get_setting; print(bool(get_setting('jwt')))"`. |
| **Expected** | Final URL is `https://api.pointcapitalis.com/user/onboarding`. `get_setting('jwt')` returns truthy. Local `data/.amplifier_auth.json` file exists with `access_token` field. Calling without `?token=` returns 400. |
| **Automated** | yes |
| **Automation** | DevTools MCP + python one-liner |
| **Evidence** | URL transition; `bool(get_setting('jwt'))` stdout |
| **Cleanup** | none — JWT needed for AC9-AC13 |

### AC9 — Local `/connect` lists ONLY linkedin / facebook / reddit (X hidden)

| Field | Value |
|-------|-------|
| **Setup** | Local user app running. |
| **Action** | `navigate_page("http://localhost:5222/connect")` → `take_snapshot`. Search snapshot text for platform names. |
| **Expected** | Snapshot contains "LinkedIn", "Facebook", "Reddit". Does NOT contain "X" or "Twitter" as a connectable platform card. Connect buttons are present and clickable for the 3 active platforms. |
| **Automated** | yes |
| **Automation** | DevTools MCP — assert via regex on snapshot text |
| **Evidence** | screenshot; snapshot text dump |
| **Cleanup** | none |

### AC10 — Local `/keys` saves encrypted, never echoes plaintext, Test button validates

| Field | Value |
|-------|-------|
| **Setup** | Local user app running. Use a known-good Gemini key from env (`GEMINI_API_KEY`). |
| **Action** | `navigate_page("/keys")` → `take_snapshot` (record initial state). Fill `gemini_api_key` field with `$GEMINI_API_KEY` → submit → `take_snapshot` of response. Reload page → `take_snapshot`. Then click the "Test" button next to Gemini → wait for HTMX response. |
| **Expected** | Initial snapshot: input is empty OR shows "configured / re-enter to overwrite" placeholder, NEVER the plaintext key. Save response: success banner mentioning "Gemini". Reload: same masked placeholder, plaintext NEVER in DOM (assert via `evaluate_script` that `document.body.innerText` does not contain `$GEMINI_API_KEY`). Test button: returns "Key valid". Stored value in DB is `iv_hex:ciphertext_hex` format (verify: `python -c "from scripts.utils.local_db import get_setting; v=get_setting('gemini_api_key'); print(':' in v and len(v)>40)"`). |
| **Automated** | yes |
| **Automation** | DevTools MCP + python verifier |
| **Evidence** | screenshots; encrypted-stored assertion stdout |
| **Cleanup** | none |

### AC11 — Local `/drafts` lists drafts grouped by campaign with text + image

| Field | Value |
|-------|-------|
| **Setup** | Background agent has produced ≥1 draft per active platform for UAT-741 (verify: `python scripts/uat/dump_drafts.py --campaign-id $(cat data/uat/last_campaign_id.txt)` shows ≥3 rows). |
| **Action** | `navigate_page("http://localhost:5222/drafts")` → `take_snapshot` → `take_screenshot("data/uat/screenshots/74_1_ac11_drafts.png")`. Also navigate to `/drafts/<campaign_id>`. |
| **Expected** | `/drafts` page groups drafts under "UAT-741 ..." heading. Each draft card shows platform badge, draft text (non-empty), status pill ("pending"). At least 1 draft has an embedded `<img>` from `/drafts/{id}/image` returning HTTP 200 in network log. `/drafts/<id>` filtered view shows only that campaign's drafts. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot; network log showing 200 on draft image fetches |
| **Cleanup** | none |

### AC12 — Draft actions (approve/reject/restore/unapprove/edit) update local DB AND server

| Field | Value |
|-------|-------|
| **Setup** | AC11 passed. Drafts present. Capture each draft's `server_draft_id` via `dump_drafts.py`. |
| **Action** | Pick the LinkedIn draft. Sequence: (a) Click "Approve" → wait for HTMX swap → status pill should be "approved". (b) Click "Unapprove" → status "pending". (c) Click "Edit" → modify text → submit → status "pending" + new text. (d) Click "Reject" → status "rejected". (e) Click "Restore" → status "pending". After each, query local DB AND server: `curl -s -H "Authorization: Bearer $TOKEN" "https://api.pointcapitalis.com/api/drafts?campaign_id=<id>" \| jq '.[] \| select(.id == <server_draft_id>) \| .status'`. |
| **Expected** | Each action: HTMX response 200, draft card re-renders with new status. Local DB `agent_draft.approved` matches the action (1 / 0 / -1). Server-side draft status (after ≤5s for fire-and-forget sync) matches the local action. No `Server sync ... failed` lines in `data/uat/user_app.log`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + bash curl + python DB query |
| **Evidence** | per-action snapshot; per-action server status; user_app.log grep |
| **Cleanup** | leave one draft in "approved" state for AC16 |

### AC13 — `GET /drafts/{id}/image` serves the actual image file

| Field | Value |
|-------|-------|
| **Setup** | A draft exists with non-null `image_path` pointing to a real file. Capture draft id. |
| **Action** | `curl -sI http://localhost:5222/drafts/<draft_id>/image \| head -10`. Also fetch a non-existent id `99999`. |
| **Expected** | Real id: HTTP 200, `Content-Type: image/jpeg` (or `image/png`), `Content-Length > 0`. Bogus id: HTTP 404 with detail "Image not found" or "Draft not found". |
| **Automated** | yes |
| **Automation** | curl |
| **Evidence** | both responses headers |
| **Cleanup** | none |

### AC14 — SSE `/sse/user/agent-status` updates dashboard agent badge in <5s

| Field | Value |
|-------|-------|
| **Setup** | Logged into hosted dashboard. `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` is in effect for the server process (set in `/etc/amplifier/server.env` for the duration of the UAT run, then restart `amplifier-web.service`). Background agent NOT running (so initial state is "Idle"). |
| **Action** | On `/user/dashboard`, capture initial agent badge text. Then start background agent in another shell: `python scripts/background_agent.py --once --campaign-id $(cat data/uat/last_campaign_id.txt) &`. Wait up to 5s. `take_snapshot` of the agent badge. |
| **Expected** | Initial badge: "Idle". Within 5s of agent start: badge text changes to "Generating" or "Connected" (whatever heartbeat reports). Page did NOT navigate. `list_network_requests` shows an active EventSource on `/sse/user/agent-status`. Cookie auth used (no `Authorization` header on the SSE request). |
| **Automated** | yes |
| **Automation** | DevTools MCP + shell |
| **Evidence** | before/after screenshots; SSE request headers |
| **Cleanup** | restore default heartbeat in `server.env`; restart `amplifier-web` |

### AC15 — Logout clears server cookie AND local JWT

| Field | Value |
|-------|-------|
| **Setup** | Logged in on hosted dashboard. JWT present in local `data/.amplifier_auth.json`. |
| **Action** | `navigate_page("/user/logout")` → `wait_for(text="Sign in")` → check cookie + local file. |
| **Expected** | Final URL is `/user/login`. `document.cookie` no longer contains `user_token=` (or contains `user_token=` but value is empty/expired). For the local-side clear: confirmed if the daemon's 401 handler clears the JWT — verify by re-running a daemon `--once` cycle and observing `clear_jwt()` is invoked OR the local file is removed. |
| **Automated** | partial |
| **Automation** | DevTools MCP for browser side; manual file check for local side |
| **Evidence** | cookie dump; presence/absence of `data/.amplifier_auth.json` |
| **Cleanup** | log back in for AC16 |

### AC16 — Real post: approve → background posts → URL captured → user app shows "Posted" → cleanup deletes

| Field | Value |
|-------|-------|
| **Setup** | Local user app running. Approved LinkedIn draft from AC12. `AMPLIFIER_UAT_POST_NOW=1` set in env. Real LinkedIn profile cookies present in `profiles/linkedin-profile/`. Background agent NOT yet running. |
| **Action** | Start background agent in foreground: `AMPLIFIER_UAT_POST_NOW=1 python scripts/background_agent.py 2>&1 \| tee data/uat/agent_post.log`. Wait up to 180s for "Post succeeded" log line. Verify on LinkedIn via Playwright headless that the post is live (use `scripts/uat/delete_post.py --dry-run` to confirm visibility). Then run actual deletion: `python scripts/uat/delete_post.py --platform linkedin --post-url <captured_url> --update-local-db`. |
| **Expected** | `agent_post.log` contains `Post succeeded` for `platform=linkedin`. `posts` row created in local DB and server with `post_url` matching `linkedin.com/feed/update/`. User app `/drafts` shows the draft as "posted". `/user/posts` shows the post with status "live". After deletion: `delete_post.py` reports success; `posts.status` updates to `deleted`; `void_earnings_for_post` voids any pending payout. |
| **Automated** | partial — automated lifecycle, manual eyeball confirmation that the post truly went live and was deleted |
| **Automation** | shell + Playwright via `delete_post.py` |
| **Evidence** | `agent_post.log`; post_url; LinkedIn screenshot of the live post; `delete_post.py` output |
| **Cleanup** | post deleted from LinkedIn; local + server DB rows in `deleted` status |

### AC17 — Console + network hygiene across the full sweep

| Field | Value |
|-------|-------|
| **Setup** | All prior ACs run. DevTools MCP has accumulated console + network state. |
| **Action** | After AC1-AC16 complete, dump `list_console_messages()` and `list_network_requests()` for the entire session. Grep for level=error and status>=500. |
| **Expected** | Zero console messages with `level=error`. Zero network requests to `/user/*`, `/sse/*`, `/api/*`, or `localhost:5222/*` with status code ≥500. Warnings (e.g., HTMX missing target on hot-reload) ARE allowed but must be reviewed in the report. |
| **Automated** | yes |
| **Automation** | DevTools MCP final dump + grep |
| **Evidence** | full console + network JSON dumps embedded in `data/uat/reports/task-74-1-<yyyy-mm-dd>-<hhmm>.md` |
| **Cleanup** | `close_page` on all DevTools-opened pages; `kill $(cat data/uat/user_app.pid)`; `python scripts/uat/cleanup_campaign.py --id $(cat data/uat/last_campaign_id.txt)` |

---

### Aggregated PASS rule for Task #74.1

Task #74.1 is marked done in task-master ONLY when:
1. AC1–AC17 all PASS (AC15 partial-manual, AC16 partial-manual)
2. Server `journalctl -u amplifier-web --since "<UAT start>"` contains zero `(?i)error|exception|traceback` lines (warnings OK)
3. Local `data/uat/user_app.log` contains zero `(?i)error|exception|traceback` lines
4. `audit_log` rows added during the UAT window — none have `severity='error'`
5. UAT report `docs/uat/reports/task-74-1-<yyyy-mm-dd>-<hhmm>.md` written with every screenshot embedded, network/console dumps appended, and a PASS/FAIL line per AC
6. Cleanup steps executed: UAT campaign voided, local user app stopped, real LinkedIn post deleted (AC16), test heartbeat env restored

---

## Task #74.2 — Company Dashboard Full Sweep

### What it covers

Every page and action under `/company/*` on the hosted server (24 endpoints):

- `GET /company/login` + `POST /company/login` + `POST /company/register` + `GET /company/logout`
- `GET /company/` (dashboard cards)
- `GET /company/campaigns` (list + HTMX filter partials)
- `GET /company/campaigns/new` + `POST /company/campaigns/new` (manual create)
- `GET /company/campaigns/ai-wizard` + `POST /company/campaigns/ai-generate` (AI wizard)
- `POST /company/campaigns/upload-asset` (Bearer-auth image upload, Task #64)
- `GET /company/campaigns/{id}` (detail: assignments / posts / metrics / decline reasons)
- `POST /company/campaigns/{id}/edit`
- `POST /company/campaigns/{id}/status` (activate / pause / complete / cancel)
- `POST /company/campaigns/{id}/topup` (per-campaign top-up)
- `POST /company/campaigns/{id}/repost-content` (deferred Task #7 — verify it 404s/hides)
- `GET /company/billing` + `POST /company/billing/topup` + `GET /company/billing/success` (Stripe Checkout)
- `GET /company/influencers` (list)
- `GET /company/stats`
- `GET /company/settings` + `POST /company/settings` (profile)
- `POST /company/settings/api-keys` + `POST /company/settings/api-keys/test` (BYOK, Task #70)

### Features to verify end-to-end (Task #74.2)

1. Register with ToS checkbox gates submission (Task #28); register without ToS shows error — AC1
2. Register with ToS succeeds, redirects to `/company/`, `tos_accepted_at` stamped — AC2
3. Login + logout work; logout clears cookie — AC3
4. Dashboard cards render: balance, active campaigns, total spend, recent posts — AC4
5. Campaigns list HTMX filter (`status=draft|active|paused|completed`) swaps without full reload — AC5
6. Manual campaign create form submission triggers quality gate (Task #15); low-quality brief rejected — AC6
7. Manual campaign create with high-quality brief activates and runs AI review (Task #71 audit log entry) — AC7
8. AI wizard scrapes URL → generates brief via Gemini → renders prefilled form for review — AC8
9. AI wizard generated campaign goes through quality gate + AI review on activate (Task #71 fix) — AC9
10. Asset upload via `POST /campaigns/upload-asset` returns `{url, filename, content_type}` (Task #64); 401 without auth — AC10
11. Campaign detail page renders assignments table, posts table, metrics aggregate, decline reasons aggregate (Task #5) — AC11
12. Campaign edit updates fields and persists; quality gate re-runs if budget/payouts changed — AC12
13. Status transitions: draft→active→paused→active→completed (each state guarded correctly) — AC13
14. Cancel campaign refunds remaining budget to company balance (`balance_cents` increases by exact remainder) — AC14
15. Per-campaign top-up adds to that campaign's budget without touching company balance for other campaigns — AC15
16. Repost content endpoint: deferred per Task #7 — UI hides the action; direct POST returns 404 or 400 — AC16
17. Billing page top-up: Stripe Checkout test card `4242 4242 4242 4242` flows; webhook credits balance once (Task #19 AC4 idempotency) — AC17
18. Billing success page shows confirmed amount and updated balance — AC18
19. Influencers list renders accepted users grouped by campaign with their post counts — AC19
20. Stats page renders aggregate engagement / spend / impressions chart without console errors — AC20
21. Settings profile save persists; reload shows updated values — AC21
22. BYOK keys: save → DB stores encrypted (`iv:ciphertext` format) → reload never echoes plaintext → "Test" button validates against provider; auth-error fallback to env var works (Task #70) — AC22
23. Console + network hygiene across full sweep — AC23

---

## Verification Procedure — Task #74.2

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Stripe test mode active on VPS env. Webhook endpoint registered (per Task #19 AC2). Stripe CLI listening forwarded if needed.
- Test company throwaway: `uat-co-742-<timestamp>@uat.local` / `uat-pass-742`. Will register fresh in AC2 (no pre-seed).
- Pre-existing test company `uat-co-existing@uat.local` with $200 balance and 1 active campaign (for ACs that need state).
- Chrome DevTools MCP available. Stripe MCP authenticated (`mcp__stripe__list_products`).
- Working Gemini key in env (for wizard ACs).

### Test data setup

1. **Seed companion fixtures** for ACs that need pre-existing state:
   ```bash
   python scripts/uat/seed_company_fixtures.py \
     --email uat-co-existing@uat.local \
     --password uat-pass-existing \
     --balance-cents 20000 \
     --with-active-campaign true \
     --output data/uat/company_fixture.json
   ```
   *(Helper to be created if absent — wraps existing `tests/conftest.py` factory + sets balance + activates one campaign.)*

2. **Stripe test webhook listener** (skip if prod webhook already registered):
   ```bash
   stripe listen --forward-to https://api.pointcapitalis.com/api/stripe/webhook --skip-verify
   ```

3. **Test image fixture** at `data/uat/fixtures/product1.jpg` (create if missing per Task #64 setup).

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `STRIPE_MODE=test` | Forces test keys (set in VPS env for the UAT window) | All Stripe ACs |
| `AMPLIFIER_UAT_DRY_STRIPE=1` | Fallback when Stripe MCP unavailable; logs Transfer kwargs without calling Stripe | AC17 fallback |

---

### AC1 — Register without ToS checkbox shows error and does not create company

| Field | Value |
|-------|-------|
| **Setup** | DevTools MCP fresh page. No session cookie. |
| **Action** | `new_page("https://api.pointcapitalis.com/company/login")` → click "Register" tab → fill name, email `uat-co-742-{ts}@uat.local`, password → leave ToS checkbox UNCHECKED → click "Create Account" → `take_snapshot`. |
| **Expected** | Page stays at `/company/login?register=1`. Error banner contains "terms of service" (case-insensitive). No 302 to `/company/`. SQL `SELECT count(*) FROM companies WHERE email='<email>'` → 0. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL count via VPS cleanup helper |
| **Evidence** | screenshot of error banner; SQL count |
| **Cleanup** | none |

### AC2 — Register WITH ToS succeeds, redirects, stamps `tos_accepted_at`

| Field | Value |
|-------|-------|
| **Setup** | Continuing from AC1. Same email. |
| **Action** | Check the ToS checkbox → click "Create Account" → wait for redirect → `take_snapshot`. SQL `SELECT tos_accepted_at FROM companies WHERE email='<email>'`. |
| **Expected** | Redirect to `/company/` (302). Dashboard renders. `tos_accepted_at` is non-null and within 60s of NOW(). The ToS checkbox label has working hyperlinks to `/terms` and `/privacy` (HTTP 200 on each, verified separately). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | screenshot of dashboard; `tos_accepted_at` timestamp |
| **Cleanup** | leave logged in for AC3 (logout test) |

### AC3 — Login + logout work; logout clears cookie

| Field | Value |
|-------|-------|
| **Setup** | Logged in from AC2. |
| **Action** | `navigate_page("/company/logout")` → wait for redirect → `evaluate_script("document.cookie")` → log back in via `/company/login` with email + password → wait for redirect to `/company/`. |
| **Expected** | After logout: redirect to `/company/login`. `company_token` cookie absent or empty. Login attempt with wrong password → error banner (HTTP 401 in network log). Login with correct password → redirect to `/company/`. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | cookie dump before/after; network log of login attempts |
| **Cleanup** | logged in for AC4 |

### AC4 — Dashboard cards: balance, active campaigns, spend, recent posts

| Field | Value |
|-------|-------|
| **Setup** | Logged in as `uat-co-existing@uat.local` (has $200 + active campaign). |
| **Action** | `navigate_page("/company/")` → `take_snapshot` → `take_screenshot`. |
| **Expected** | DOM contains: balance card showing `\$200\.00` (or formatted equivalent), active-campaigns card with count >= 1, total-spend card (numeric), recent-posts list (or empty state with copy). Zero console errors, zero 5xx. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC5 — Campaigns list HTMX filter swaps without full reload

| Field | Value |
|-------|-------|
| **Setup** | Logged in. ≥1 campaign in `active` status. Optionally seed 1 in `draft` and 1 in `completed` for full filter coverage. |
| **Action** | `navigate_page("/company/campaigns")` → for each filter pill `[draft, active, paused, completed]`: click → wait for HTMX swap → snapshot. Inspect `list_network_requests`. |
| **Expected** | Each click fires GET `/company/campaigns?status=<filter>` (or partial endpoint) returning HTML fragment. URL fragment updates but page does NOT reload. Each filter shows campaigns matching that state, or explicit empty-state copy. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | per-filter snapshots; network log with HTMX partial requests |
| **Cleanup** | none |

### AC6 — Manual create with low-quality brief rejected by quality gate

| Field | Value |
|-------|-------|
| **Setup** | Logged in. On `/company/campaigns/new`. |
| **Action** | Fill minimum fields with INTENTIONALLY low-quality data: title "test", brief "buy stuff" (under 50 chars), guidance empty, payouts at $0.01 each, budget $5 → submit. |
| **Expected** | Form re-renders with quality gate score and reasons listed (score < 85). Campaign saved as `draft` (or rejected outright) — NOT activated. `audit_log` row added with `event='quality_gate_rejected'`. UI shows actionable feedback ("Brief too short", "Budget below $10", etc.). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | screenshot of rejection feedback; audit_log row dump |
| **Cleanup** | delete the draft campaign |

### AC7 — Manual create with high-quality brief activates + AI review runs

| Field | Value |
|-------|-------|
| **Setup** | Logged in. Capture `audit_log` count. |
| **Action** | Submit a high-quality manual campaign: title "UAT-742 Bamboo Desk Organizer", goal `brand_awareness`, brief 300+ chars detailing product/audience/value, guidance 80+ chars, niche_tags `["productivity","work-from-home"]`, required_platforms `["linkedin","reddit"]`, payouts: views $0.50/1k, like $0.01, comment $0.02, repost $0.05, budget $50, end_date 2 weeks out, accept-and-activate checkbox if present. |
| **Expected** | HTTP 200. Campaign created with `status=active`. Quality gate score >= 85 (visible on detail page or in audit_log). New audit_log rows: `event='quality_gate_pass'` AND `event='ai_review_complete'` (Task #71 wizard-vs-create parity). AI review verdict in {`safe`, `caution`} — not `reject`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | screenshot; audit_log diff (>= 2 new rows); campaign id captured to `data/uat/last_company_campaign.txt` |
| **Cleanup** | leave campaign for ACs 11-14 |

### AC8 — AI wizard scrapes URL, generates brief, prefills form

| Field | Value |
|-------|-------|
| **Setup** | On `/company/campaigns/ai-wizard`. Use `https://example.com` (or a known stable URL). |
| **Action** | Fill input URL → click "Generate" → wait up to 60s for response → `take_snapshot`. |
| **Expected** | Generated form fields populated: title, brief (≥ 200 chars), goal, niche_tags ≥ 1, target audience description. Generated content references the URL's domain. POST `/campaigns/ai-generate` returns 200 in ≤ 60s. No console errors. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot of populated form; network log timing |
| **Cleanup** | navigate away without saving (AC9 will save) |

### AC9 — AI wizard generated campaign runs full pipeline on activate (Task #71)

| Field | Value |
|-------|-------|
| **Setup** | On AI wizard with populated form from AC8. Capture `audit_log` count. |
| **Action** | Click "Create + Activate" → wait for response. |
| **Expected** | Campaign created with `status=active`. New audit_log rows: `event='quality_gate_pass'` AND `event='ai_review_complete'` (regression check for Task #71 — wizard path historically skipped these). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | audit_log diff |
| **Cleanup** | mark campaign as cancelled at end of UAT |

### AC10 — Asset upload requires Bearer auth, returns expected JSON shape

| Field | Value |
|-------|-------|
| **Setup** | Test image at `data/uat/fixtures/product1.jpg`. Company JWT obtainable via login API. |
| **Action** | (1) Unauth: `curl -s -X POST https://api.pointcapitalis.com/api/company/campaigns/assets -F "file=@data/uat/fixtures/product1.jpg" -o /dev/null -w '%{http_code}'`. (2) Auth: same with `-H "Authorization: Bearer $COMPANY_TOKEN"`. (3) Bad type: upload a `.txt` file with auth. |
| **Expected** | (1) 401 or 403. (2) 200 + JSON `{"url":"...","filename":"...","content_type":"image/jpeg"}`. (3) 400 with detail "Unsupported file type" or similar. |
| **Automated** | yes |
| **Automation** | curl + jq |
| **Evidence** | three response bodies + status codes |
| **Cleanup** | none |

### AC11 — Campaign detail renders assignments + posts + metrics + decline reasons

| Field | Value |
|-------|-------|
| **Setup** | UAT-742 campaign from AC7 (id captured). At least 1 assignment + 1 declined invitation seeded. |
| **Action** | `navigate_page("/company/campaigns/<id>")` → `take_snapshot` → `take_screenshot`. |
| **Expected** | Page renders sections: Overview (title/brief/budget), Assignments (table with user emails + status), Posts (table with platform + metrics or empty-state), Metrics aggregate (impressions / engagements / spend), Decline Reasons (top reasons with counts — Task #5). No raw `null` / `undefined` in DOM. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC12 — Edit campaign updates fields; quality gate re-runs on budget change

| Field | Value |
|-------|-------|
| **Setup** | UAT-742 campaign. |
| **Action** | Click "Edit" on detail page → change `guidance` field → submit. Then change `budget_cents` → submit. |
| **Expected** | Both edits persist (verify via SQL or reload). On budget change: new audit_log row `event='quality_gate_recheck'` (or equivalent). UI shows updated values. |
| **Automated** | partial |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | before/after field values |
| **Cleanup** | none |

### AC13 — Status transitions: draft→active→paused→active→completed

| Field | Value |
|-------|-------|
| **Setup** | Create a fresh draft campaign for this AC (`POST /campaigns/new` without activate). |
| **Action** | Sequentially: activate → pause → activate → complete via the status-change buttons on the detail page. After each, query `SELECT status FROM campaigns WHERE id=<id>`. |
| **Expected** | DB shows `draft → active → paused → active → completed`. Each transition writes an audit_log row `event='campaign_status_changed'` with `from`/`to` metadata. UI reflects each state. Cannot transition from `completed` back to `active` (button hidden or rejected). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | status timeline; audit_log diff |
| **Cleanup** | leave at `completed` |

### AC14 — Cancel campaign refunds remaining budget to company balance

| Field | Value |
|-------|-------|
| **Setup** | Fresh active campaign with $50 budget, $20 already spent (seed 2 metric rows that bill to $20). Capture `companies.balance_cents` before. |
| **Action** | Cancel the campaign via the detail page button. |
| **Expected** | Campaign `status=cancelled`. `companies.balance_cents` increased by exactly $30.00 (3000 cents). audit_log row `event='campaign_cancelled_refund'` with `refund_cents=3000`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | balance before/after; audit_log row |
| **Cleanup** | none |

### AC15 — Per-campaign top-up adds to that campaign only

| Field | Value |
|-------|-------|
| **Setup** | UAT-742 active campaign. Capture both `campaigns.budget_cents` and `companies.balance_cents`. Note balance must be sufficient for top-up. |
| **Action** | On detail page, click per-campaign top-up button → enter $25 → submit. |
| **Expected** | `campaigns.budget_cents` increased by 2500. `companies.balance_cents` decreased by 2500. Other campaigns' budgets unchanged (verify via SQL). audit_log row `event='campaign_topup'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | before/after for affected and unaffected campaigns + balance |
| **Cleanup** | none |

### AC16 — Repost content endpoint hidden in UI; direct POST rejected

| Field | Value |
|-------|-------|
| **Setup** | Logged in as company. UAT-742 campaign id available. |
| **Action** | (1) `take_snapshot` of campaign detail page; grep for "repost"/"Repost". (2) Direct: `curl -s -X POST -H "Authorization: Bearer $COMPANY_TOKEN" https://api.pointcapitalis.com/company/campaigns/<id>/repost-content -d '{}' -w '\n%{http_code}\n'`. |
| **Expected** | (1) UI snapshot does NOT contain a visible "Repost" button or link in active state — feature deferred per Task #7. (2) Direct POST returns 4xx (404 if route disabled, 400 if guard rejects, 405 if method not allowed). NOT 200. |
| **Automated** | yes |
| **Automation** | DevTools MCP + curl |
| **Evidence** | snapshot grep; curl response code |
| **Cleanup** | none |

### AC17 — Stripe Checkout test card credits balance once (idempotent)

| Field | Value |
|-------|-------|
| **Setup** | Logged in. On `/company/billing`. Capture `companies.balance_cents` before. |
| **Action** | Click "Add Funds" → enter `$100` → click "Continue to Stripe" → on Stripe Checkout test page enter card `4242 4242 4242 4242` exp `12/34` cvc `123` ZIP `12345` → click "Pay" → wait for redirect to `/company/billing/success?session_id=...`. Capture session id. Then via MCP: `mcp__stripe__trigger_event(event_type="checkout.session.completed", checkout_session=<session_id>)` (replay — idempotency check). |
| **Expected** | After Checkout: webhook log shows `webhook_received event=checkout.session.completed sig_verified=True`. `balance_cents` increased by exactly 10000. After replay: balance UNCHANGED (idempotent). audit_log gains 1 `event='balance_credited'` row from real flow + 1 `event='webhook_duplicate_ignored'` from replay (or count unchanged). |
| **Automated** | partial |
| **Automation** | DevTools MCP for UI + Stripe MCP for replay + SQL for balance + journalctl grep |
| **Evidence** | session id; balance timeline; audit_log dump; server log lines |
| **Cleanup** | none — credited balance carries through |

### AC18 — Billing success page shows confirmed amount and updated balance

| Field | Value |
|-------|-------|
| **Setup** | Continuing from AC17. On `/company/billing/success?session_id=<id>`. |
| **Action** | `take_snapshot` + `take_screenshot`. Reload the page. |
| **Expected** | Page shows "Top-up successful" with amount `$100.00` and updated balance. Reloading does NOT trigger a second balance credit (idempotent — same as AC17 but verified end-user-facing). |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC19 — Influencers list renders accepted users grouped by campaign

| Field | Value |
|-------|-------|
| **Setup** | At least 1 user has accepted UAT-742 invitation. |
| **Action** | `navigate_page("/company/influencers")` → `take_snapshot`. |
| **Expected** | Page shows table of users with email (or display name), tier, post count for this company, total earnings paid out by this company. Grouped or filterable by campaign. Empty-state copy if no influencers yet. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC20 — Stats page renders aggregates without console errors

| Field | Value |
|-------|-------|
| **Setup** | Logged in. |
| **Action** | `navigate_page("/company/stats")` → `take_snapshot` → `list_console_messages`. |
| **Expected** | Page renders chart(s) — Chart.js canvas present. Numbers for total impressions / engagements / spend. Zero console errors. Zero 5xx in network. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot; console + network dumps |
| **Cleanup** | none |

### AC21 — Settings profile save persists

| Field | Value |
|-------|-------|
| **Setup** | Logged in. On `/company/settings`. |
| **Action** | Change company name + website URL → submit → reload page → verify values match new input. |
| **Expected** | POST `/company/settings` returns success. Reload shows updated values. SQL `SELECT name, website FROM companies WHERE id=<id>` matches. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | before/after snapshots |
| **Cleanup** | revert values |

### AC22 — BYOK keys: encrypted, never echoed plaintext, Test button validates, fallback works

| Field | Value |
|-------|-------|
| **Setup** | On `/company/settings`. Have a known-good Gemini key in env (`GEMINI_API_KEY`). |
| **Action** | (a) Initial snapshot → input shows "Not set" or empty. (b) Submit Gemini key field with `$GEMINI_API_KEY` → response → reload page → snapshot. (c) Click "Test" next to Gemini → wait for HTMX result. (d) Set an INVALID Gemini key → activate any campaign that triggers AI review (or POST `/campaigns/quality-gate-recheck`) → verify auth-error fallback (Task #70 `call_with_byok_fallback`). |
| **Expected** | (a) Initial: no plaintext key in DOM. (b) After save+reload: shown as "•••••• (configured — re-enter to overwrite)" or equivalent — plaintext NEVER in DOM (`evaluate_script("!document.body.innerText.includes('$GEMINI_API_KEY')")` → true). DB row is encrypted (`SELECT encrypted_value FROM company_api_keys WHERE company_id=<id> AND provider='gemini'` — value contains `:` and length > 40). (c) Test button: returns "Key valid" message. (d) With bad key: AI review still completes (fallback to env-var key); audit_log shows `event='byok_auth_error_fallback'` or similar. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL + grep audit_log |
| **Evidence** | screenshots; SQL dump (encrypted); fallback audit_log row |
| **Cleanup** | restore valid Gemini key |

### AC23 — Console + network hygiene across full sweep

| Field | Value |
|-------|-------|
| **Setup** | All prior ACs run. DevTools MCP cumulative state. |
| **Action** | Final dump: `list_console_messages()` + `list_network_requests()`. Grep for `level=error` and HTTP status >=500 on `/company/*` and `/api/*`. |
| **Expected** | Zero console errors. Zero 5xx. Warnings allowed but reviewed in report. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | full JSON dumps embedded in report |
| **Cleanup** | `close_page` on all DevTools-opened pages; cancel UAT campaigns; delete throwaway company `uat-co-742-*@uat.local` from prod DB |

---

### Aggregated PASS rule for Task #74.2

Task #74.2 is marked done in task-master ONLY when:
1. AC1–AC23 all PASS (AC12, AC17, AC18 partial-manual checkpoints OK)
2. `journalctl -u amplifier-web` during the UAT window contains zero `(?i)error|exception|traceback` lines
3. `audit_log` rows added during the UAT window — none have `severity='error'`
4. UAT report `docs/uat/reports/task-74-2-<yyyy-mm-dd>-<hhmm>.md` written with every screenshot embedded
5. Cleanup: throwaway company deleted, UAT campaigns cancelled, Stripe test transfers reconciled, BYOK valid key restored
6. Stripe test mode keys still active on VPS (no accidental flip to live during UAT)

---

## Task #74.3 — Admin Dashboard Full Sweep

### What it covers

Every page and action under `/admin/*` (36+ routes across 11 modular routers):

- Auth: `GET /admin/login` + `POST /admin/login` + `GET /admin/logout` (password-only auth)
- Overview: `GET /admin/` (live stats via SSE `/sse/admin/overview`)
- Users: `GET /admin/users` + `POST /admin/users/bulk/suspend` + `GET /admin/users/{id}` + `POST /admin/users/{id}/{suspend|unsuspend|ban|adjust-trust}`
- Companies: `GET /admin/companies` + `GET /admin/companies/{id}` + `POST /admin/companies/{id}/{add-funds|deduct-funds|suspend|unsuspend}`
- Campaigns: `GET /admin/campaigns` + `GET /admin/campaigns/{id}` + `POST /admin/campaigns/{id}/{pause|resume|cancel}`
- Financial (Task #8 + worker manual overrides): `GET /admin/financial` + `POST /financial/{run-billing|run-payout|run-earning-promotion|run-payout-processing}` + `POST /financial/payouts/{id}/{void|approve}`
- Fraud: `GET /admin/fraud` + `POST /fraud/run-check` + `POST /fraud/penalties/{id}/{approve-appeal|deny-appeal}`
- Review queue: `GET /admin/review-queue` + `POST /review-queue/{id}/{approve|reject}` (quality gate `caution` verdicts land here)
- Analytics: `GET /admin/analytics`
- Audit log: `GET /admin/audit-log` (with filters)
- Settings: `GET /admin/settings`

### Features to verify end-to-end (Task #74.3)

1. Admin login with correct password redirects to `/admin/`; wrong password rejected — AC1
2. Overview renders live stats; SSE `/sse/admin/overview` updates count without page reload — AC2
3. Users list HTMX search/filter swaps without full reload — AC3
4. User detail page shows trust score, posts, payouts, audit_log entries — AC4
5. Per-user trust adjust modifies trust_score and writes audit_log row — AC5
6. Per-user suspend/unsuspend toggles `is_suspended`; suspended user cannot log in — AC6
7. Bulk suspend (Alpine fetch path) suspends multiple selected users in one request — AC7
8. Per-user ban sets `is_banned=True` (terminal); audit_log entry created — AC8
9. Companies list renders with balance + active campaigns count — AC9
10. Company detail: add-funds increases balance; deduct-funds decreases; both write audit_log — AC10
11. Company suspend prevents new campaign creation; unsuspend restores — AC11
12. Admin campaign list + detail + pause/resume/cancel transitions; cancel refunds budget to company balance — AC12
13. Financial page: 5 manual override buttons each fire and complete (run-billing, run-payout, run-earning-promotion, run-payout-processing, plus aggregate stats card) — AC13
14. Per-payout void: pending payout → voided, returns funds to campaign budget, audit_log row with reason — AC14 (Task #8)
15. Per-payout force-approve: pending → available immediately (skips 7-day hold), audit_log row — AC15 (Task #8)
16. Available payout void: returns funds AND decrements user `earnings_balance_cents` — AC16 (Task #8)
17. Fraud page lists flagged users; run-check button fires manual sweep — AC17
18. Fraud penalty appeal approve/deny each work and write audit_log — AC18
19. Review queue lists campaigns with `caution` verdict from AI quality gate; approve/reject each work — AC19 (Task #15)
20. Analytics page renders Chart.js charts without console errors — AC20
21. Audit log page renders with filters (event type, severity, time range); pagination works — AC21
22. Settings page renders feature flags / platform-cut % / hold days — AC22
23. Logout clears session — AC23
24. Console + network hygiene across full sweep — AC24

---

## Verification Procedure — Task #74.3

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Admin password set in VPS env (`ADMIN_PASSWORD`). Capture for AC1.
- Test fixtures: ≥3 users (1 normal, 1 to suspend, 1 to ban), ≥2 companies (1 to suspend), ≥3 campaigns (1 active to cancel, 1 in `caution` review queue, 1 already complete).
- ≥2 payouts (1 pending past 7-day hold ready to promote, 1 available ready to void).
- ≥1 fraud penalty with appeal pending.
- Chrome DevTools MCP available.

### Test data setup

1. **Seed admin fixtures**:
   ```bash
   python scripts/uat/seed_admin_fixtures.py \
     --users 3 \
     --companies 2 \
     --campaigns 3 \
     --pending-payouts 1 \
     --available-payouts 1 \
     --fraud-penalty-with-appeal 1 \
     --review-queue-caution-campaign 1 \
     --output data/uat/admin_fixtures.json
   ```
   *(Helper to be created if absent — composes existing seed primitives.)*

2. **Capture admin password** via VPS env:
   ```bash
   ADMIN_PW=$(ssh sammy@31.97.207.162 "sudo grep ^ADMIN_PASSWORD /etc/amplifier/server.env | cut -d= -f2-")
   ```

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` | Speeds admin overview SSE heartbeat for AC2 | AC2 |
| `AMPLIFIER_UAT_DRY_STRIPE=1` | Logs Transfer kwargs without calling Stripe — used by financial run-payout path when MCP unavailable | AC13 (run-payout-processing path) |

---

### AC1 — Admin login: correct password → `/admin/`; wrong password rejected

| Field | Value |
|-------|-------|
| **Setup** | DevTools MCP fresh page. No admin session. |
| **Action** | (1) `new_page("https://api.pointcapitalis.com/admin/login")` → enter "wrong-password" → submit → snapshot. (2) Reload → enter `$ADMIN_PW` → submit → wait for redirect. |
| **Expected** | (1) Stays at `/admin/login` with error banner. Network log shows 401 or 422. (2) Redirects to `/admin/`. Cookie `admin_token` set. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | both snapshots; cookie dump |
| **Cleanup** | none |

### AC2 — Overview renders live stats; SSE updates without reload

| Field | Value |
|-------|-------|
| **Setup** | Logged in as admin. `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` set in VPS env. |
| **Action** | `take_snapshot` of `/admin/` — capture initial counts (users, companies, campaigns, posts today, payouts pending). Trigger an event that bumps a counter (e.g., register a fresh user via curl). Wait up to 5s. `take_snapshot` again. Inspect SSE request via `list_network_requests`. |
| **Expected** | EventSource open on `/sse/admin/overview` with cookie auth (no Bearer header). Within 5s of new-user registration: users-count card updates without page navigation. URL unchanged. Zero console errors. |
| **Automated** | yes |
| **Automation** | DevTools MCP + curl trigger |
| **Evidence** | before/after snapshots; SSE request headers |
| **Cleanup** | restore default heartbeat |

### AC3 — Users list HTMX search/filter swaps without full reload

| Field | Value |
|-------|-------|
| **Setup** | Logged in. ≥3 users seeded. |
| **Action** | `navigate_page("/admin/users")` → enter search query in the email filter input → wait for HTMX swap. Try filter pills (status: all / active / suspended / banned). |
| **Expected** | Each filter fires GET `/admin/users?q=...&status=...` returning HTML fragment. URL fragment updates; no full reload. Filter results match query. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | per-filter snapshots; network log |
| **Cleanup** | none |

### AC4 — User detail: trust score, posts, payouts, audit log

| Field | Value |
|-------|-------|
| **Setup** | Click into a seeded user. |
| **Action** | `navigate_page("/admin/users/<id>")` → `take_snapshot` → `take_screenshot`. |
| **Expected** | Page sections present: profile (email, tier, trust_score, joined_at), posts table, payouts history, audit_log entries for this user. No raw `null`/`undefined`. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC5 — Trust adjust modifies trust_score + writes audit_log

| Field | Value |
|-------|-------|
| **Setup** | On user detail. Capture initial `trust_score`. |
| **Action** | Click "Adjust Trust" → enter delta `-10` + reason "uat-744-test" → submit. Reload page. Query SQL `SELECT trust_score FROM users WHERE id=<id>`. |
| **Expected** | UI shows new trust_score = initial - 10 (clamped 0..100). audit_log row added: `event='trust_adjusted'`, `metadata.delta=-10`, `metadata.reason='uat-744-test'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | trust_score before/after; audit_log row |
| **Cleanup** | revert trust_score (+10) |

### AC6 — Per-user suspend/unsuspend; suspended user blocked from login

| Field | Value |
|-------|-------|
| **Setup** | On detail page of test user "uat-suspend-target@uat.local". |
| **Action** | (1) Click "Suspend" → confirm. (2) From a separate browser/curl, attempt user login with that email's credentials. (3) Click "Unsuspend" → re-attempt login. |
| **Expected** | (1) `users.is_suspended=True`. (2) Login attempt rejected with 403 (or 401 with `account suspended` detail). (3) After unsuspend, login succeeds. audit_log rows for both suspend and unsuspend events. |
| **Automated** | yes |
| **Automation** | DevTools MCP + curl |
| **Evidence** | SQL state; login response codes |
| **Cleanup** | leave unsuspended |

### AC7 — Bulk suspend (Alpine fetch path) suspends multiple users at once

| Field | Value |
|-------|-------|
| **Setup** | `/admin/users` list. ≥2 test users with checkboxes. |
| **Action** | Check 2 user rows → click "Suspend Selected" → wait for response → reload list. |
| **Expected** | POST `/admin/users/bulk/suspend` returns 200. Both users now `is_suspended=True` in SQL. Page refreshes/swaps to reflect. Single network request — confirms Alpine fetch path works (Bug #66 history: `hx-vals='js:'` was broken; replaced with direct fetch). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | network request; SQL state for both users |
| **Cleanup** | unsuspend both |

### AC8 — Per-user ban sets `is_banned=True` (terminal)

| Field | Value |
|-------|-------|
| **Setup** | On user detail page of a throwaway test user. |
| **Action** | Click "Ban" → confirm with reason. SQL: `SELECT is_banned FROM users WHERE id=<id>`. |
| **Expected** | `is_banned=True`. audit_log row `event='user_banned'`. UI now hides the Suspend/Unsuspend buttons (terminal state). |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | SQL state; audit_log row |
| **Cleanup** | optionally unban via direct SQL for cleanup |

### AC9 — Companies list renders with balance + active campaigns count

| Field | Value |
|-------|-------|
| **Setup** | Logged in. ≥2 seeded companies. |
| **Action** | `navigate_page("/admin/companies")` → `take_snapshot`. |
| **Expected** | Table shows email, name, balance (formatted as `$X.XX`), active campaigns count, total spend. Filters or search work. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC10 — Company add-funds + deduct-funds adjust balance and write audit_log

| Field | Value |
|-------|-------|
| **Setup** | Click into a test company. Capture `balance_cents`. |
| **Action** | (1) Click "Add Funds" → enter `$50` + reason → submit. (2) Click "Deduct Funds" → enter `$25` + reason → submit. SQL after each. |
| **Expected** | After (1): `balance_cents` increased by 5000. After (2): decreased by 2500 from the post-add value. audit_log rows for both: `event='admin_balance_credit'` and `event='admin_balance_debit'` with `metadata.amount_cents` and `metadata.reason`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | balance timeline; audit_log rows |
| **Cleanup** | revert balance to original |

### AC11 — Company suspend blocks new campaign creation

| Field | Value |
|-------|-------|
| **Setup** | Test company logged in separately (or curl JWT in hand). |
| **Action** | (1) Admin clicks "Suspend Company". (2) From company side, POST `/company/campaigns/new` with valid payload. (3) Admin clicks "Unsuspend". (4) Retry POST. |
| **Expected** | (2) Returns 403 (or 400 with "company suspended" detail). (4) Returns 200 (or 302 to detail page). audit_log rows for both transitions. |
| **Automated** | yes |
| **Automation** | DevTools MCP + curl |
| **Evidence** | response codes; SQL state |
| **Cleanup** | leave unsuspended |

### AC12 — Admin campaign pause/resume/cancel; cancel refunds budget

| Field | Value |
|-------|-------|
| **Setup** | Active test campaign with $40 remaining budget. |
| **Action** | On `/admin/campaigns/<id>`: pause → SQL check `status=paused`. Resume → `status=active`. Capture company balance. Cancel → SQL check `status=cancelled` + balance. |
| **Expected** | Status transitions correct. Cancel refunds remaining budget exactly to company `balance_cents`. audit_log rows for each transition. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | status timeline; balance before/after cancel |
| **Cleanup** | none |

### AC13 — Financial: 5 manual override buttons each fire and complete

| Field | Value |
|-------|-------|
| **Setup** | On `/admin/financial`. Seed: 1 ready pending payout (past 7-day hold), 1 available payout, 1 unbilled metric. |
| **Action** | Click each button in turn: (a) Run Billing, (b) Run Payout, (c) Run Earning Promotion, (d) Run Payout Processing. After each, observe response banner + reload page. Capture audit_log delta. |
| **Expected** | Each POST returns 200 within 30s. Server log shows job started + completed lines. (a) Bills the unbilled metric → new payout row. (c) Promotes 1 pending → 1 available. (d) Sends Transfer for the available payout (test mode or `AMPLIFIER_UAT_DRY_STRIPE=1`). audit_log gains 1 row per run. |
| **Automated** | partial |
| **Automation** | DevTools MCP + journalctl + SQL |
| **Evidence** | per-button response banner; payout state timeline; journalctl excerpts |
| **Cleanup** | none |

### AC14 — Void pending payout returns funds to campaign budget (Task #8)

| Field | Value |
|-------|-------|
| **Setup** | Pending payout `id=P1` with `amount_cents=500` against campaign `id=C1`. Capture `campaigns.budget_cents` before. |
| **Action** | On `/admin/financial`, find P1 → click "Void" → enter reason "uat-744-fake-metrics" → confirm. SQL after. |
| **Expected** | P1 `status=voided`. C1 `budget_cents` increased by 500. User `earnings_balance_cents` UNCHANGED (was pending, never available). audit_log row `event='payout_voided'`, `metadata.payout_id=P1`, `metadata.reason='uat-744-fake-metrics'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | budget timeline; SQL state |
| **Cleanup** | none |

### AC15 — Force-approve pending payout → available immediately (Task #8)

| Field | Value |
|-------|-------|
| **Setup** | Pending payout `id=P2`, `available_at` 5 days in future, `amount_cents=300`. |
| **Action** | Click "Force Approve" → confirm. SQL after. |
| **Expected** | P2 `status=available`. User `earnings_balance_cents` increased by 300. audit_log row `event='payout_force_approved'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | SQL state; audit_log row |
| **Cleanup** | none |

### AC16 — Void available payout: refunds + decrements user balance (Task #8)

| Field | Value |
|-------|-------|
| **Setup** | Available payout `id=P3`, `amount_cents=400`, against campaign `id=C1`. Capture user `earnings_balance_cents` and `campaigns.budget_cents`. |
| **Action** | Click "Void" on P3 → reason → confirm. SQL after. |
| **Expected** | P3 `status=voided`. User `earnings_balance_cents` decreased by 400 (refunded to company, not user). C1 `budget_cents` increased by 400. audit_log row `event='payout_voided'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | balance timelines |
| **Cleanup** | none |

### AC17 — Fraud page lists flagged users; run-check fires manual sweep

| Field | Value |
|-------|-------|
| **Setup** | At least 1 user with `trust_score < 60` or recent fraud penalty. |
| **Action** | `navigate_page("/admin/fraud")` → `take_snapshot`. Click "Run Check" → wait for response. |
| **Expected** | Page lists flagged users + active penalties. "Run Check" returns 200 within 30s; server log shows trust sweep ran. New audit_log row if any anomalies detected (or zero, that's OK). |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot; server log |
| **Cleanup** | none |

### AC18 — Penalty appeal approve/deny each work + write audit_log

| Field | Value |
|-------|-------|
| **Setup** | Penalty `P_A` with appeal pending. |
| **Action** | (1) Click "Approve Appeal" on P_A → confirm. (2) Repeat for P_B (different penalty) but click "Deny Appeal". |
| **Expected** | (1) P_A `status=appeal_approved`, penalty refunded if applicable. audit_log `event='penalty_appeal_approved'`. (2) P_B `status=appeal_denied`. audit_log `event='penalty_appeal_denied'`. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | SQL state per penalty |
| **Cleanup** | none |

### AC19 — Review queue: list `caution` campaigns; approve/reject each work (Task #15)

| Field | Value |
|-------|-------|
| **Setup** | ≥1 campaign with quality gate verdict `caution` queued in `admin_review_queue`. Capture campaign id. |
| **Action** | `navigate_page("/admin/review-queue")` → `take_snapshot`. Click "Approve" on the test entry → confirm. Then create another `caution` entry, click "Reject" → enter reason → confirm. |
| **Expected** | Approve: campaign `status` transitions to `active`. Queue entry removed. audit_log `event='admin_review_approved'`. Reject: campaign stays `draft` (or transitions to `rejected` per spec). audit_log `event='admin_review_rejected'` with reason. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL |
| **Evidence** | SQL state; audit_log rows |
| **Cleanup** | none |

### AC20 — Analytics page renders charts without console errors

| Field | Value |
|-------|-------|
| **Setup** | Logged in as admin. |
| **Action** | `navigate_page("/admin/analytics")` → `take_snapshot` → `list_console_messages`. |
| **Expected** | Chart.js canvases render. Numeric KPIs display (total revenue, total payouts, MoM growth). Zero console errors. Zero 5xx. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot; console dump |
| **Cleanup** | none |

### AC21 — Audit log: filters work + pagination

| Field | Value |
|-------|-------|
| **Setup** | ≥30 audit_log rows from prior ACs (the UAT itself generated plenty). |
| **Action** | `navigate_page("/admin/audit-log")` → `take_snapshot`. Apply filters: event_type=`payout_voided`, severity=`info`, date range last 1h. Click "Next page". |
| **Expected** | Filtered results match SQL `SELECT * FROM audit_log WHERE event=...`. Pagination shows correct row counts. URL params reflect filter state. |
| **Automated** | yes |
| **Automation** | DevTools MCP + SQL diff |
| **Evidence** | snapshot; row count comparison |
| **Cleanup** | none |

### AC22 — Settings page renders feature flags / platform-cut % / hold days

| Field | Value |
|-------|-------|
| **Setup** | On `/admin/settings`. |
| **Action** | `take_snapshot`. |
| **Expected** | Page shows current platform cut % (default 20), earning hold days (default 7), any feature flags. Read-only or editable per implementation — either way, no errors. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | screenshot |
| **Cleanup** | none |

### AC23 — Logout clears admin session

| Field | Value |
|-------|-------|
| **Setup** | Logged in as admin. |
| **Action** | `navigate_page("/admin/logout")` → wait for redirect → check cookie. Try to navigate to `/admin/users` directly. |
| **Expected** | Redirect to `/admin/login`. `admin_token` cookie absent. Direct navigation to `/admin/users` redirects to login. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | cookie dump; redirect chain |
| **Cleanup** | none |

### AC24 — Console + network hygiene across full sweep

| Field | Value |
|-------|-------|
| **Setup** | All prior ACs run. |
| **Action** | Final `list_console_messages` + `list_network_requests` dumps. Grep `level=error` and status>=500. |
| **Expected** | Zero console errors. Zero 5xx on `/admin/*`, `/sse/*`, `/api/*`. |
| **Automated** | yes |
| **Automation** | DevTools MCP |
| **Evidence** | full dumps embedded in report |
| **Cleanup** | `close_page` on all DevTools pages; revert any state changes (suspended users unsuspended, balance reverts, banned user optionally unbanned via SQL); delete UAT-744 fixtures via `python scripts/uat/cleanup_admin_fixtures.py --input data/uat/admin_fixtures.json` |

---

### Aggregated PASS rule for Task #74.3

Task #74.3 is marked done in task-master ONLY when:
1. AC1–AC24 all PASS
2. `journalctl -u amplifier-web` during the UAT window contains zero `(?i)error|exception|traceback` lines (warnings OK)
3. `audit_log` rows added during the UAT window — none have `severity='error'`
4. UAT report `docs/uat/reports/task-74-3-<yyyy-mm-dd>-<hhmm>.md` written with every screenshot embedded
5. Cleanup: all admin state reverted (no permanently suspended/banned/voided test users), fixtures deleted, no orphan Stripe transfers

---

## Aggregated PASS rule for Task #74 (parent)

Task #74 is marked done in task-master ONLY when ALL three sub-tasks PASS:
1. `/uat-task 74.1` PASS — every AC green, report written
2. `/uat-task 74.2` PASS — every AC green, report written
3. `/uat-task 74.3` PASS — every AC green, report written
4. Combined audit_log of all three windows — zero `severity='error'` rows
5. No regressions in `pytest tests/` (303 passing baseline holds)

When all 4 above hold, the launch gate is passed and `#22` (landing page) can ship.
