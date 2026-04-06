# Amplifier — Task Context

**Last Updated**: 2026-04-06 (Session 35)

## Current State

**Tasks #1–4, #6 complete. Next up: Task #5 (Invitation UX), #7 (Repost UI), #8 (Admin payout actions) to finish Tier 2.**

40 total tasks: 5 done, 23 pending, 12 deferred. Detailed product specs exist for 16 tasks across 4 batches in `docs/specs/`.

## Task List (37 total)

### Tier 1: Fix Broken Foundation — COMPLETE
| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Fix URL capture (LinkedIn, Facebook, Reddit) | **done** | high |

### Tier 2: Incomplete Security & Product Gaps (7 tasks)
| # | Task | Status | Priority |
|---|------|--------|----------|
| 2 | Stripe top-up verification + idempotency fix | **done** | high |
| 3 | CSRF tokens in all server HTML forms | **done** | high |
| 4 | Slowapi rate limiting on auth endpoints | **done** | high |
| 5 | Invitation UX (countdown, expired badge, decline reason) | pending | medium |
| 6 | Metrics accuracy (deleted post detection, rate limits) | **done** | high |
| 7 | Repost campaign company creation UI | pending | medium |
| 8 | Admin payout void/approve actions | pending | medium |

### Tier 3: Features Needing Deeper Specs (10 tasks)
| # | Task | Status | Priority | Depends on |
|---|------|--------|----------|------------|
| 9 | Metric scraping per platform | pending | high | 1 ✓ |
| 10 | Billing (earnings calc, verify E2E) | pending | high | 9 |
| 11 | Earnings display (server→local sync, withdrawal) | pending | high | 10 |
| 12 | AI matching (scoring logic, verify) | pending | high | — |
| 13 | AI profile scraping (Gemini Vision, per-platform) | pending | high | — |
| 14 | 4-phase content agent | pending | high | 13 |
| 15 | AI campaign quality gate | pending | medium | — |
| 16 | Content formats (threads, polls) | pending | high | 14 |
| 17 | Free/Pro tiers (Stripe subscription) | pending | medium | — |
| 18 | Write automated test suite | pending | high | 10, 11 |

### Tier 4: Launch Tasks (4 tasks)
| # | Task | Status | Priority | Depends on |
|---|------|--------|----------|------------|
| 19 | Stripe live integration (Checkout + Connect) | pending | high | 2 ✓, 10 |
| 20 | PyInstaller packaging (Windows) | pending | high | — |
| 21 | Mac support | pending | medium | 20 |
| 22 | Landing page | pending | medium | 20 |

### Tier 5: Quick Polish (6 tasks)
| # | Task | Status | Priority |
|---|------|--------|----------|
| 23 | Periodic DB backup | pending | low |
| 24 | Status label renaming | pending | low |
| 25 | Clipboard copy for post URLs | pending | low |
| 26 | Client-side form validation | pending | low |
| 27 | Server-side post URL dedup | pending | medium |
| 28 | ToS/privacy acceptance | pending | medium |

### Deferred (12 tasks — post-launch)
29-36: Political campaigns, self-learning, video gen, Flux.1, GDPR, ARIA, CSV export, mobile responsive
37: Local lightweight LLM for user-side AI
38: AI-powered browser automation — replace all scraping/posting selectors with AI-driven navigation and extraction
39: Full profile scraping — scrape ALL info on user's social profiles (every tab, section, expand button), not just partial data
40: Onboarding questionnaire — ask users questions during onboarding so AI knows them even when profiles are sparse/generic

## Session 35 — Task #6: Metrics Accuracy (2026-04-06)

### What was done

5 gaps fixed in the metric scraping pipeline:

**1. Persistent rate limit back-off** (`metric_scraper.py`)
- Module-level `_platform_backoff_until` dict persists across `run_metric_scraping()` calls
- After 3 consecutive rate limits on a platform, sets 1-hour cooldown via `_set_platform_backoff()`
- Both API and Playwright paths check `_is_platform_backed_off()` before scraping
- Expired cooldowns auto-clear on next check

**2. Server deleted post propagation** (`metrics.py`, `server_client.py`, `metric_scraper.py`)
- New `PATCH /api/posts/{post_id}/status` server endpoint
- Accepts `{"status": "deleted"}`, verifies post ownership, calls `void_earnings_for_post()`
- New `report_post_deleted()` in `server_client.py`
- `_mark_post_deleted()` helper marks locally AND notifies server in one call
- Both API and Playwright detection paths use `_mark_post_deleted()`

**3. Server-side duplicate metric prevention** (`metrics.py`)
- `submit_metrics()` checks for existing `(post_id, scraped_at)` before inserting
- Duplicate submissions return `skipped_duplicate` count
- Metrics for deleted posts rejected with `skipped_deleted` count
- Response now includes: `{accepted, total_submitted, skipped_deleted, skipped_duplicate}`

**4. X API deleted tweet detection** (`metric_collector.py`)
- `_collect_x_api()` now catches HTTP 404 → raises `ValueError("Post deleted/unavailable")`
- Also catches HTTP 429 → raises rate limit error
- Handles empty `data` field (200 response but no tweet data) → checks for `errors` array

**5. All-zero metric warning** (`metric_scraper.py`)
- `_warn_if_all_zero()` logs WARNING when non-first scrape returns all zeros
- First scrape zeros are expected (new post) — no warning
- Warning stored in logs for investigation, zeros still saved (valid data)

### Files changed
- `scripts/utils/metric_scraper.py` — 4 new functions, backoff integration, server notification
- `scripts/utils/metric_collector.py` — X API error handling
- `scripts/utils/server_client.py` — `report_post_deleted()`
- `server/app/routers/metrics.py` — PATCH endpoint, dedup logic, deleted post rejection

### Test results (all pass)
- Rate limit back-off: 4 unit tests (initial clear, set, isolation, expiry)
- All-zero warning: 3 cases (first scrape, non-first zeros, non-zero)
- Server PATCH 404: non-existent post returns "Post not found"
- Server PATCH 422: invalid status returns validation error
- Metric submission: accepted=1, billing triggered correctly
- Duplicate metric: accepted=0, skipped_duplicate=1
- Mark deleted: earnings_voided=1, status changed
- Metrics for deleted post: accepted=0, skipped_deleted=1

## Session 34 — Tasks #2, #3, #4 (2026-04-06)

### Task #2: Stripe Top-Up Idempotency Fix

**Fixed the double-credit bug in company billing top-up flow.**

**The bug:** `/billing/success` handler credited `company.balance` on every visit with no idempotency check. Refreshing the success URL credited again.

**Fix:**
- New `CompanyTransaction` model (`server/app/models/company_transaction.py`): `id`, `company_id`, `stripe_session_id` (unique), `amount_cents`, `type`, `created_at`
- `/billing/success`: checks for existing transaction BEFORE crediting → "Payment already processed" if duplicate
- `/billing/topup` (test mode): creates transaction with `test_{uuid}` session ID
- Both `balance` and `balance_cents` updated together
- Submit buttons disable on click (double-submit protection)
- New "Top-Up History" table on billing page

**Test results (Chrome DevTools):** All 6 tests passed — add funds, cumulative balance, idempotency replay blocked, DB fields in sync, button disables, visual check.

**Commit:** `2c5778b`

### Task #3: CSRF Protection for Server HTML Forms

**Added CSRF to all ~40 POST forms across admin and company dashboards.**

**Implementation:** Double-submit cookie pattern via pure ASGI middleware (`server/app/core/csrf.py`):
1. Middleware sets `csrf_token` cookie on GET responses (random hex, JS-readable)
2. JavaScript in `base.html` + standalone login templates reads cookie and injects hidden input into all POST forms
3. On POST, middleware validates form field matches cookie
4. API routes (`/api/*`) exempt — they use JWT Bearer auth

**Files changed:**
- `server/app/core/csrf.py` — new ASGI middleware (no new packages needed)
- `server/app/main.py` — registered middleware
- `server/app/templates/base.html` — CSRF auto-injection script (covers all pages extending base)
- `server/app/templates/admin/login.html` — standalone injection script
- `server/app/templates/company/login.html` — standalone injection script

**Test results:** Login with CSRF works, POST without CSRF blocked (balance unchanged), API routes exempt (401 not 302).

**Commit:** `aec9b41`

### Task #4: Rate Limiting

Already implemented in commit `b30ce6e`. Slowapi on 9 auth endpoints (5/min). Just marked done.

### Other Actions
- Discarded accidental uncommitted reversions that removed CSRF/slowapi from earlier commits

## Session 33 — Task #1: URL Capture Fix (2026-04-06)

**Implemented URL capture for all 4 platforms, tested with live posts.**

Key changes: `script_executor.py` 3-tier extraction (CSS → JS → fallback), `url_pattern` field, platform scripts updated. LinkedIn uses activity page JS, Facebook uses activity log, Reddit uses JS-only with timestamp sorting. Legacy functions re-raise exceptions.

All 4 platforms verified: X `/status/`, LinkedIn `/feed/update/`, Facebook `pfbid`, Reddit `/comments/`.

## Deployed URLs
- **Production**: https://server-five-omega-23.vercel.app
- **Company dashboard**: /company/login
- **Admin dashboard**: /admin/login
- **User App**: localhost:5222

## Server Auth
- Local test company: `test@testco.com` / `TestCo2026!` (registered in session 34)
- Auth file: `config/server_auth.json` (encrypted)

## Key Constraints
- All AI must be free or very cheap (Gemini, Mistral, Groq free tiers)
- Father's Stripe account for payments
- US-only audience targeting
- Windows-primary, Mac support planned

## Test Commands
```bash
python scripts/user_app.py                    # Start user app on localhost:5222
python scripts/login_setup.py linkedin        # Re-login to LinkedIn (if session expired)
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd server && vercel deploy --yes --prod       # Deploy to production
task-master list                              # See all tasks
```
