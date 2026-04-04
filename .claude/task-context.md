# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 28)

## Current Task

**Task #28 — Verify: Scheduled Posting** — COMPLETE. URL capture fixed on all 4 platforms. Reddit body/title split fixed. Moving to Task #29 (Metric Scraping).

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting (#27-#28), Metrics (#29-#30) | **#27-#28 done, #29-#30 pending** |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |
| Future | AI scrapers, content gen, video gen, tiers | #51-#80 | All pending |

**28 done, 0 in-progress, 52 pending. 80 total tasks.**

## Session 28 — What Was Done

### Task #28 Completed: URL Capture + Posting Fixes (3 commits)

**Commit `4e8c314` — URL capture on all 4 platforms:**
- `script_parser.py`: Added `optional` field to `ScriptStep` — non-critical steps continue on failure
- `script_executor.py`: Handle optional steps, resolve relative hrefs against page origin (X URL was missing `x.com`), preserve first captured URL across multiple extract_url steps
- `selector_chain.py`: Fixed `aria-label` matching to use exact CSS `[aria-label="X"]` instead of `page.get_by_label("X")` which was substring matching (Facebook "Post" matched "Create a post")
- `text_input` handler: Falls back to `page.keyboard.type()` when no target selector (for shadow DOM)
- LinkedIn script: `dispatch_event` for Post button (overlay `#interop-outlet` intercepts), dialog extract optional + activity page fallback
- Facebook script: `dispatch_event` for Post button, permalink selectors (`a[href*="/posts/"]`, `a[href*="/permalink/"]`)
- Reddit script: Removed image tab switch (broke text posts), keyboard body typing
- X script: Escape to close compose overlay, JS navigation to profile (avoid `#layers` overlay click interception)
- `post.py`: Removed stale `Chrome/124` user_agent (caused LinkedIn session invalidation — mismatch with `login_setup.py`)

**Commit `e72f11a` — Reddit body/title fix (Tab approach, later replaced):**
- JS `editor.focus()` in shadow DOM didn't transfer keyboard focus — body text typed into title field
- Initial fix: Tab key from title to body (replaced in next commit)

**Commit `2bf0264` — Reddit body, Post button, user agent:**
- Body text: Click `#post-composer_bodytext` directly (Tab didn't work with Lexical editor)
- User agent: Added consistent `Chrome/137.0.0.0` to both `login_setup.py` AND `post.py` (Playwright default `HeadlessChrome/143` triggers Reddit network security block)
- Reddit JSON script Post button: `dispatch_event` doesn't trigger shadow DOM components — legacy poster handles Reddit posting for now

### Verified URL Capture Results
| Platform | URL Format | Method |
|----------|-----------|--------|
| X | `https://x.com/SamaaraDas/status/{id}` | JSON script — Escape overlay → JS navigate to profile → extract `a[href*="/status/"]` |
| LinkedIn | `https://www.linkedin.com/feed/update/urn:li:share:{id}/` | JSON script — dispatch_event Post → extract from "View post" dialog → activity page fallback |
| Facebook | `https://www.facebook.com/permalink.php?story_fbid={id}` | JSON script — dispatch_event Post → extract `a[href*="/permalink/"]` from profile |
| Reddit | `https://www.reddit.com/user/{user}/comments/{id}/` | Legacy poster — redirect URL capture with `?created=t3_` parsing |

### Other Fixes
- **Server auth re-registered**: Old token expired (March 28). New account: `amplifier.test@gmail.com` / `Amplifier2026!` on deployed server
- **Stripe account note**: Father's company has existing Stripe account — use for Amplifier (saved to REMAINING-WORK.md + memory)

### Bugs Discovered & Fixed
1. **X URL missing domain**: `href="/SamaaraDas/status/..."` → `https://SamaaraDas/status/...` (missing `x.com`). Fixed: resolve relative URLs against `page.url` origin
2. **Facebook wrong button**: `get_by_label("Post")` matched `aria-label="Create a post"` (substring). Fixed: exact CSS `[aria-label="Post"]`
3. **LinkedIn session killed**: Stale `Chrome/124` user agent in `post.py` but no UA in `login_setup.py`. LinkedIn detected mismatch, invalidated session. Fixed: matching UA in both files
4. **Reddit HeadlessChrome blocked**: Default Playwright UA includes "HeadlessChrome" → Reddit security block. Fixed: explicit `Chrome/137` UA
5. **Reddit body in title**: JS `editor.focus()` doesn't transfer keyboard focus from title textarea in shadow DOM. Fixed: click `#post-composer_bodytext` directly
6. **Reddit image tab breaks text posts**: Switching to Images tab for text-only posts disables Post button. Fixed: removed image tab steps from script
7. **X compose overlay blocks profile click**: After Ctrl+Enter submit, `#layers` overlay intercepts clicks. Fixed: Escape key + JS navigation

### Key Decisions
- Reddit JSON script Post button not working (shadow DOM `dispatch_event` doesn't trigger) — using legacy poster for Reddit until fixed
- Consistent user agent between login_setup.py and post.py is critical — session invalidation otherwise
- `dispatch_event("click")` is the standard approach for overlay-intercepted buttons (X, LinkedIn, Facebook)
- `optional` field on ScriptStep is the mechanism for graceful fallback chains

## How to Start Next Session

**Phase A continues with Task #29 (Metric Scraping)**. Read `docs/REMAINING-WORK.md` for Task #29-30 specs.

The posting pipeline now works E2E on all 4 platforms with real URL capture. Metric scraping can verify against these real URLs.

## Remaining Blockers (Priority Order)
1. ~~Posting URL capture broken~~ FIXED
2. ~~Reddit body/title split~~ FIXED
3. Metric scraping unverified E2E (Tasks #29-30) — NEXT
4. Billing unverified E2E — plus `get_cpm_multiplier()` bug (Tasks #31-32)
5. X account detection risk (locked during testing)
6. Real Stripe payments (father's company Stripe account available)
7. FTC disclosure not in content generator
8. Distribution — no installable app yet

## Key Reference Files

### Implementation Planning
- `docs/REMAINING-WORK.md` — 58 tasks with implementation + verification specs
- `docs/EXECUTION-ORDER.md` — 7 phases, dependency chains, gate criteria
- `docs/SCHEMA-CHANGES.md` — All DB migrations in one manifest
- `docs/FILE-CHANGE-INDEX.md` — File-to-task mapping + conflict map

### Core Code (Posting Pipeline)
- `scripts/post.py` — Posting orchestrator (script-first, legacy fallback). Line 174 `post_via_script()`, line 128 `_launch_context()`
- `scripts/engine/script_executor.py` — 13 action types + optional step handling
- `scripts/engine/script_parser.py` — `ScriptStep` dataclass with `optional` field
- `scripts/engine/selector_chain.py` — Fallback selector chains, `aria-label` exact match
- `config/scripts/` — Platform JSON scripts (x, linkedin, facebook, reddit)
- `scripts/login_setup.py` — Manual login with matching Chrome/137 UA
- `scripts/background_agent.py` — 6 async tasks, posts every 60s
- `scripts/utils/post_scheduler.py` — `execute_scheduled_post()` line 374

### Metric Scraping (Next Task)
- `scripts/utils/metric_scraper.py` — Per-platform scrapers + tier schedule
- `scripts/utils/metric_collector.py` — X/Reddit API + LinkedIn/Facebook Browser Use
- `scripts/utils/local_db.py` — `local_metric` table, `add_metric()`, `sync_metrics_to_server()`
- `server/app/services/billing.py` — `run_billing_cycle()` reads metrics

### Server
- `server/app/services/billing.py` — Cents math, hold periods, tier promotion. BUG: `get_cpm_multiplier()` exists but never called
- `scripts/utils/server_client.py` — Auth file at `config/server_auth.json`

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222
- **GitHub**: https://github.com/Samaara-Das/Amplifier (private)

## Test Commands
```bash
python scripts/user_app.py
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
python scripts/login_setup.py <platform>   # x | linkedin | facebook | reddit
vercel deploy --yes --prod --cwd server
```

## Server Auth
- Email: `amplifier.test@gmail.com`
- Password: `Amplifier2026!`
- Auth file: `config/server_auth.json`
