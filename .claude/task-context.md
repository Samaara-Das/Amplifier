# Amplifier — Task Context

**Last Updated**: 2026-04-06 (Session 34)

## Current State

**Tasks #1 and #2 complete. Ready for Task #3 (CSRF verification).**

37 total tasks: 2 done, 26 pending, 9 deferred. Detailed product specs exist for 16 tasks across 4 batches in `docs/specs/`.

## Task List (37 total)

### Tier 1: Fix Broken Foundation — COMPLETE
| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Fix URL capture (LinkedIn, Facebook, Reddit) | **done** | high |

### Tier 2: Incomplete Security & Product Gaps (7 tasks)
| # | Task | Status | Priority |
|---|------|--------|----------|
| 2 | Stripe top-up verification + idempotency fix | **done** | high |
| 3 | Verify CSRF tokens in all Flask forms | pending | high |
| 4 | Install slowapi + apply rate limiting | pending | high |
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

## Session 34 — Task #2: Stripe Top-Up Idempotency Fix (2026-04-06)

### What Was Done

**Fixed the double-credit bug in company billing top-up flow.**

#### The Bug
- `/billing/success` handler credited `company.balance` on every visit with no idempotency check
- Refreshing the success URL, hitting back/forward, or replaying the session_id would credit the balance again
- No transaction records existed — zero audit trail

#### Fix: CompanyTransaction Model + Idempotency Check

**New model** (`server/app/models/company_transaction.py`):
- `id`, `company_id`, `stripe_session_id` (unique index), `amount_cents`, `type`, `created_at`
- Unique constraint on `stripe_session_id` is the idempotency key

**Billing router changes** (`server/app/routers/company/billing.py`):
- `/billing/success`: checks for existing `CompanyTransaction` with that `session_id` BEFORE crediting. If found → "Payment already processed" redirect, no credit.
- `/billing/topup` (test mode): creates transaction record with `test_{uuid}` session ID
- Both paths now update `balance` AND `balance_cents` together
- Transaction history fetched and passed to template

**Template changes** (`server/app/templates/company/billing.html`):
- Submit buttons disable on click + text changes to "Processing..."/"Adding..." (prevents rapid double-submit)
- New "Top-Up History" table showing date, amount, type badge, reference

**Model registration** (`server/app/models/__init__.py`):
- Added `CompanyTransaction` to imports and `__all__`

#### Also Fixed
- Discarded accidental uncommitted reversions that removed CSRF/slowapi work from earlier commits (`git checkout -- <7 files>`)

### Test Results (Chrome DevTools MCP)

| Test | What | Result |
|------|------|--------|
| 1 | Add $50 test funds | PASSED — Balance $50, 1 transaction row |
| 2 | Add $25 more | PASSED — Balance $75, 2 transaction rows |
| 3 | Replay session ID via `/billing/success` | PASSED — "Payment already processed", balance stays $75 |
| 4 | DB integrity (`balance` vs `balance_cents`) | PASSED — `balance=75`, `balance_cents=7500`, in sync |
| 5 | Double-submit button protection | PASSED — Button disables + text changes |
| 6 | Visual screenshot | PASSED — Top-Up History table renders cleanly |

### Key Decisions
1. **CompanyTransaction model** — lightweight idempotency table rather than full payment ledger. Sufficient for now, extensible for Task #19 (Stripe live).
2. **Test mode gets transaction records too** — same audit trail as production.
3. **Both balance fields updated** — `balance` (float) and `balance_cents` (int) kept in sync. Old companies (pre-fix) may have `balance_cents=0`.

### Commit
`2c5778b` — `fix: add idempotency to company billing top-up (Task #2)`

## Session 33 — Task #1: URL Capture Fix (2026-04-06)

### What Was Done

**Implemented URL capture for all 4 platforms, tested end-to-end with live posts.**

#### Key Changes
- `scripts/engine/script_executor.py`: 3-tier extraction (CSS → JS → page URL fallback), `url_pattern` field
- `scripts/engine/script_parser.py`: `url_pattern` field added to `ScriptStep`
- Platform scripts updated: LinkedIn (activity page JS), Facebook (activity log), Reddit (JS-only with timestamp sorting)
- `scripts/post.py`: Legacy functions re-raise exceptions instead of returning None
- `scripts/utils/post_scheduler.py`: Fixed `resolved_assignment_id` NameError

#### Verified Results
| Platform | Captured URL | Verified |
|----------|-------------|----------|
| X | `x.com/SamaaraDas/status/...` | ✅ |
| LinkedIn | `linkedin.com/feed/update/urn:li:share:...` | ✅ |
| Facebook | `facebook.com/permalink.php?story_fbid=pfbid...` | ✅ |
| Reddit | `reddit.com/user/SamaaraDas/comments/...` | ✅ |

### Key Decisions
1. Reddit views ARE scrapeable via Playwright (not PRAW)
2. Facebook activity log > profile page for chronological URL capture
3. JS-only for Reddit (CSS selectors match nav tabs, not posts)
4. Legacy functions must re-raise exceptions (returning None causes false posted_no_url)

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
