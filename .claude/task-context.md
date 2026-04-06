# Amplifier — Task Context

**Last Updated**: 2026-04-06 (Session 34)

## Current State

**Tasks #1–4 complete. Next up: Task #5 (Invitation UX) or #6 (Metrics accuracy).**

37 total tasks: 4 done, 24 pending, 9 deferred. Detailed product specs exist for 16 tasks across 4 batches in `docs/specs/`.

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
| 6 | Metrics accuracy (deleted post detection, rate limits) | pending | high |
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

### Deferred (9 tasks — post-launch)
29-36: Political campaigns, self-learning, video gen, Flux.1, GDPR, ARIA, CSV export, mobile responsive
37: Local lightweight LLM for user-side AI

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
