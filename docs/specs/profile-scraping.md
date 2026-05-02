# Task #86 — Profile Scraping Pipeline (Post-Platform-Connect)

**Status:** pending
**Branch:** flask-user-app
**Discovered:** during /uat-task 75 holistic re-test, 2026-05-02

## What this fixes

A real first-time user installs Amplifier → registers → connects LinkedIn (session saves) → **profile is NEVER scraped** → server has no `niches`, `follower_count`, `bio` for this user → matching service has nothing to score them against → user is never invited to any campaign → earns $0 forever.

The cascading-impact analysis from Task #82 already documented this. Task #82 fixed the daemon orphan (so daemon runs continuously). But the WIRING from "platform session saved" → "scraper fires" was never built. `login_setup.py` only saves the session; nothing triggers scraping after.

This task fixes the wiring + adds UAT to verify the chain works for every active platform, with field-level coverage and a user-confirmation step to verify what was scraped is actually true.

## Files to change

| File | Change |
|---|---|
| `scripts/utils/local_server.py` | After `POST /connect/{platform}` triggers `run_login(platform)`, also inject an `AgentCommand` of type `scrape_profiles` with `payload={"platforms": [platform]}` via `server_client.post_agent_command(...)`. Daemon picks it up on next command poll (within `COMMAND_POLL_INTERVAL`=15s in UAT, 60s in prod). |
| `scripts/background_agent.py` | `process_server_commands` already handles `scrape_profiles` type. Verify the handler calls per-platform scrapers with correct args. Add a `_handle_scrape_profiles(payload)` if missing. |
| `scripts/background_agent.py` | Add `AMPLIFIER_UAT_PROFILE_REFRESH_NOW` env override that shortens `PROFILE_REFRESH_INTERVAL` from 7 days to 30s — so end-to-end UAT runs in minutes, not days. |
| `server/app/routers/admin/users.py` | Add admin button on `/admin/users/{id}` "Refresh profile" that injects `scrape_profiles` AgentCommand for that user. Operational tooling for rescues. |
| `docs/uat/AC-FORMAT.md` | Register new `AMPLIFIER_UAT_PROFILE_REFRESH_NOW` flag in the Approved Flags section. |

## Features to verify end-to-end (Task #86)

1. After `POST /connect/linkedin` completes (session saved on disk), within 30s a `scraped_profile` row appears in local SQLite with `platform='linkedin'` and non-empty data — AC1
2. Same for `POST /connect/facebook` — AC2
3. Same for `POST /connect/reddit` — AC3
4. Per-platform field coverage — scraped data includes `display_name`, `follower_count`, `bio`, `recent_posts`, `niches`, `ai_niches`, `engagement_rate` for each platform (where applicable per platform's profile shape) — AC4
5. Manual user-confirmation: scraped values match what's actually visible on the user's real profile on each platform — AC5 (per-platform sub-checks)
6. Server-side `User.scraped_profiles` JSON gets updated via daemon's API push within 60s of the local scrape — AC6
7. Admin "Refresh profile" button on `/admin/users/{id}` injects a `scrape_profiles` AgentCommand and triggers a re-scrape within 30s — AC7
8. `AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1` shortens daemon's auto-refresh from 7d to 30s (so daemon fires `refresh_profiles` repeatedly during UAT) — AC8
9. Daemon log `data/uat/daemon_86.log` contains zero `error|exception|traceback` lines during the UAT window — AC9
10. After the full 3-platform connect flow, matching service scoring the test user against a sample campaign returns a non-zero score (proves scraped data flows into the matching pipeline) — AC10

---

## Verification Procedure — Task #86

### Preconditions

- Server live at `https://api.pointcapitalis.com` (`curl /health` → 200)
- Local user app + sidecar daemon will be started during setup
- Chrome DevTools MCP available
- LinkedIn / Facebook / Reddit Playwright sessions exist on disk under `profiles/` (already saved from prior UAT runs today; if not, `python scripts/login_setup.py <platform>` once per platform)
- No prior `uat-task86-user@pointcapitalis.com` row in `users` table on prod
- `scraped_profile` table has the test user's pre-state captured for delta comparison

### Test data setup

1. Confirm clean slate:
   ```bash
   curl -s -X POST https://api.pointcapitalis.com/api/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"uat-task86-user@pointcapitalis.com","password":"uat-pass-86","accept_tos":true}'
   ```
   If response is `{"detail":"Email already registered"}`, run cleanup first via SSH cascade-delete (per Task #85).

2. Capture pre-state:
   ```bash
   python -c "
   import sqlite3
   con = sqlite3.connect('data/local.db')
   for r in con.execute(\"SELECT platform, datetime(scraped_at), follower_count FROM scraped_profile ORDER BY scraped_at DESC\").fetchall():
       print(r)
   " > data/uat/task86_pre_state.txt
   ```

3. Start user_app (sidecar mode boots daemon):
   ```bash
   CAMPAIGN_SERVER_URL=https://api.pointcapitalis.com \
   AMPLIFIER_UAT_INTERVAL_SEC=15 \
   AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1 \
   AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000 \
   python -u scripts/user_app.py > data/uat/daemon_86.log 2>&1 &
   echo $! > data/uat/daemon_86.pid
   ```
   Wait until `curl http://localhost:5222/healthz` returns 200.

### Test-mode flags

| Flag | Effect | Used by AC |
|---|---|---|
| `AMPLIFIER_UAT_INTERVAL_SEC=15` | shortens command_poll + status_push to 15s | AC1, AC2, AC3, AC6 |
| `AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1` | shortens `PROFILE_REFRESH_INTERVAL` from 604800s (7d) to 30s — for the daemon's automatic refresh loop | AC8 |
| `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=2000` | SSE heartbeat 2s instead of 30s | (UI verification only) |

---

### AC1: LinkedIn scrape fires within 30s of platform connect, valid row inserted

| Field | Value |
|---|---|
| **Setup** | user_app + daemon running. JWT in local DB for `uat-task86-user`. `scraped_profile` pre-state captured. LinkedIn session saved on disk. |
| **Action** | DevTools MCP: drive the full register flow, land on `/user/onboarding/step2`, click "Open Desktop App" → opens `localhost:5222/connect` → click "Connect LinkedIn" → Playwright opens browser → user closes browser when login complete (per LEARNING 2026-04-26 auto-detect-via-log-marker). Then poll `scraped_profile` table every 5s up to 60s. |
| **Expected** | Within 30s of "Session saved for LinkedIn!" log line: `scraped_profile` has new row where `platform='linkedin'` and `scraped_at` > pre-state max. Row's `display_name` non-empty, `follower_count >= 0` (integer), `bio` non-empty OR `recent_posts` non-empty (one or both must have content). Daemon log shows `Scraping linkedin profile...` AND `Profile scraped for linkedin: <name>` (or equivalent). |
| **Automated** | yes |
| **Automation** | DevTools MCP for the click flow; `pytest scripts/uat/uat_task86.py::test_ac1_linkedin_post_connect_scrape` for the row check |
| **Evidence** | Pre/post `scraped_profile` SQL rows; daemon log excerpt with timestamps; screenshot `data/uat/screenshots/task86_ac1_step2_after_linkedin.png` showing badge update |
| **Cleanup** | none (subsequent ACs build on this) |

### AC2: Facebook scrape fires within 30s of platform connect, valid row inserted

| Field | Value |
|---|---|
| **Setup** | AC1 passed. Facebook session saved on disk. |
| **Action** | Same as AC1 but for Facebook: click "Connect Facebook" on `/connect`, manual login if needed, close browser. Poll `scraped_profile` for new facebook row. |
| **Expected** | Within 30s of "Session saved for Facebook!" log line: `scraped_profile` has new row where `platform='facebook'`, `scraped_at` > AC1 timestamp. Row contains `display_name`, `follower_count` (Facebook follower_count or "friends" count, derived per Task #53 fix — display-name-anchored regex). Daemon log shows scrape activity. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac2_facebook_post_connect_scrape` |
| **Evidence** | SQL rows; daemon log; screenshot |
| **Cleanup** | none |

### AC3: Reddit scrape fires within 30s of platform connect, valid row inserted

| Field | Value |
|---|---|
| **Setup** | AC2 passed. Reddit session saved on disk. |
| **Action** | Click "Connect Reddit", manual login if needed, close browser. Poll for new reddit row. |
| **Expected** | Within 30s of "Session saved for Reddit!" log line: `scraped_profile` has row where `platform='reddit'`, `scraped_at` > AC2 timestamp. Row contains `karma` (or follower equivalent), `reddit_age`, `active_subreddits` array (>=1). For private profiles, row should have `profile_data->'profile_privacy'='private'` per Task #13 spec. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac3_reddit_post_connect_scrape` |
| **Evidence** | SQL rows; daemon log |
| **Cleanup** | none |

### AC4: Per-platform field coverage — scraped data includes all spec'd fields

| Field | Value |
|---|---|
| **Setup** | AC1, AC2, AC3 all passed. |
| **Action** | For each platform row, verify field-level completeness: `python -c "import sqlite3,json; con=sqlite3.connect('data/local.db'); for p in ['linkedin','facebook','reddit']: r=con.execute('SELECT display_name, follower_count, bio, recent_posts, ai_niches, engagement_rate, profile_data FROM scraped_profile WHERE platform=? ORDER BY scraped_at DESC LIMIT 1', (p,)).fetchone(); print(p, [bool(x) for x in r])"` |
| **Expected** | Per platform: `display_name` non-empty, `follower_count` numeric, `bio` non-empty (or `profile_data` JSON has bio-equivalent), `recent_posts` array length >= 1 (or for low-activity accounts, may be 0 — document edge case), `ai_niches` JSON array length >= 1 (Tier 1 AI extraction worked), `engagement_rate` numeric (or null acceptable for new accounts). |
| **Automated** | partial — per-field validation auto, but `>=1 niche detected` may need manual eyeball if AI returned empty |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac4_field_coverage` |
| **Evidence** | per-platform field dump in `data/uat/task86_ac4_field_coverage.txt` |
| **Cleanup** | none |

### AC5: Manual user-confirmation — scraped values match the user's real profile

| Field | Value |
|---|---|
| **Setup** | AC4 passed. |
| **Action** | For each of LinkedIn / Facebook / Reddit, the skill (a) prints the scraped row in chat as a table with `display_name`, `follower_count`, `bio`, `recent_posts[0:3]`, `ai_niches`, then (b) opens the user's actual profile URL in Chrome DevTools MCP (e.g., `https://www.linkedin.com/in/me/`, `https://www.facebook.com/me`, `https://www.reddit.com/user/me/`) so the user can compare side-by-side. Asks: "Does the scraped data above match what you see on your actual profile? (y/n)". |
| **Expected** | User answers `y` for all 3 platforms. If `n` for any platform, the skill captures specific differences (e.g., "follower_count says 9494 but profile shows 12k") and marks AC5 as a sub-FAIL listing which platform + field mismatched. |
| **Automated** | manual — bounded yes/no per platform |
| **Automation** | `manual` (DevTools MCP renders comparison) |
| **Evidence** | Inline screenshots of user's real profile + scraped-row table in chat; user yes/no per platform captured to report |
| **Cleanup** | `close_page` on the platform tabs |

### AC6: Server-side `User.scraped_profiles` JSON updated within 60s of local scrape

| Field | Value |
|---|---|
| **Setup** | AC1, AC2, AC3 all passed. Daemon's profile-sync task should push local scrape to server. |
| **Action** | Wait 60s after AC3 completes. `curl -s -H "Authorization: Bearer <jwt>" https://api.pointcapitalis.com/api/users/me \| python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('scraped_profiles',{}), indent=2))"` |
| **Expected** | `scraped_profiles` JSON has keys for all 3 platforms (`linkedin`, `facebook`, `reddit`). Each platform's nested object has `display_name`, `follower_count`, `bio`, `niches`, `last_scraped_at` (recent timestamp). Matches the local `scraped_profile` rows. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac6_server_side_sync` |
| **Evidence** | Server JSON dump; SQL diff between local + server data |
| **Cleanup** | none |

### AC7: Admin "Refresh profile" button injects scrape command + triggers re-scrape

| Field | Value |
|---|---|
| **Setup** | AC6 passed. Admin logged in at `/admin/users/{id}` for the test user. |
| **Action** | DevTools MCP: navigate `/admin/users/<test_user_id>` → click "Refresh profile" button → wait for confirmation toast → poll local `scraped_profile` for a NEW row (timestamp later than AC1/AC2/AC3 entries). |
| **Expected** | A `scrape_profiles` AgentCommand row is inserted in server `agent_command` table with `status='pending'`. Within 30s, daemon picks it up (`process_server_commands` log line), command status flips to `done`, and at least one platform's `scraped_profile` row gets refreshed (timestamp > AC3 timestamp). |
| **Automated** | yes |
| **Automation** | DevTools MCP for click; `pytest scripts/uat/uat_task86.py::test_ac7_admin_refresh_button` |
| **Evidence** | Screenshot of admin button click + toast; SQL row showing AgentCommand lifecycle pending → done; SQL diff in `scraped_profile` |
| **Cleanup** | none |

### AC8: `AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1` shortens daemon auto-refresh from 7d to 30s

| Field | Value |
|---|---|
| **Setup** | Daemon running with `AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1` (set in test data setup). |
| **Action** | Capture daemon log timestamps for `refresh_profiles` task firing. Wait 90s. Re-check log. |
| **Expected** | Daemon log contains AT LEAST 2 occurrences of "Refreshing profiles" (or equivalent log line) within 90s — proves the 30s override is honored. Without the flag, this would fire only once per 7 days. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac8_refresh_interval_override` |
| **Evidence** | Daemon log grep with timestamps |
| **Cleanup** | none |

### AC9: Daemon log clean of error/exception/traceback during the UAT window

| Field | Value |
|---|---|
| **Setup** | UAT window started at AC1 setup, ends after AC7 cleanup. |
| **Action** | `grep -aE "(?i)error\|exception\|traceback" data/uat/daemon_86.log \| grep -v "WARNING"` |
| **Expected** | Zero matches (warnings are OK). If matches found, list them in the report; AC9 fails if any unhandled exception or traceback fired during the window. |
| **Automated** | yes |
| **Automation** | bash grep above |
| **Evidence** | grep output (must be empty) |
| **Cleanup** | none |

### AC10: Matching service can score the test user using scraped data

| Field | Value |
|---|---|
| **Setup** | AC1-AC6 passed (local + server scraped data complete). A test campaign exists with `niche_tags=["trading","finance"]` (use the standard seed_campaign helper). |
| **Action** | Trigger matching: `curl -X POST https://api.pointcapitalis.com/admin/run-matching -H "Authorization: Bearer <admin>"` (or trigger via user-pull as in production). Then check the matching score for `(test_user, test_campaign)`. |
| **Expected** | Matching service returns a score >= 30 (Gemini AI score, normalized 0-100). For a user whose `ai_niches` should include trading-adjacent terms, score should be substantial. CampaignAssignment row created with `status='pending_invitation'`. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task86.py::test_ac10_matching_uses_scraped_data` |
| **Evidence** | Matching score in log; SQL row showing CampaignAssignment created |
| **Cleanup** | reject the assignment; void the test campaign |

---

### Aggregated PASS rule for Task #86

Task #86 is marked done in task-master ONLY when:

1. AC1 + AC2 + AC3 PASS (per-platform scrape fires post-connect within 30s)
2. AC4 PASS (per-platform field coverage)
3. AC5 PASS for all 3 platforms (user manual y/n confirmation that scraped data matches reality)
4. AC6 PASS (server-side sync within 60s)
5. AC7 PASS (admin button works)
6. AC8 PASS (UAT flag honored)
7. AC9 PASS (zero exceptions/tracebacks during the window)
8. AC10 PASS (matching uses scraped data)
9. UAT report `docs/uat/reports/task-86-<yyyy-mm-dd>-<hhmm>.md` written with all evidence + screenshots embedded
10. All cleanup completed: `python scripts/uat/cleanup_test_user.py --email uat-task86-user@pointcapitalis.com` (cascade per #85), kill daemon process, void test campaign, close DevTools pages

**Cleanup command** (run unconditionally):
```bash
kill $(cat data/uat/daemon_86.pid) 2>/dev/null || true
ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162 "<cascade-delete script per Task #85>"
```
