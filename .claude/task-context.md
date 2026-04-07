# Amplifier — Task Context

**Last Updated**: 2026-04-07 (Session 36)

## Current State

**Tier 2 complete (6/6 active tasks done). Task #7 (Repost) deferred. Next: Task #38 (E2E deleted post detection) then Tier 3.**

38 total tasks: 7 done, 21 pending, 10 deferred. Task #38 (E2E deleted post detection on all 4 platforms) is the immediate next item.

## Task List

### Tier 1: Fix Broken Foundation — COMPLETE
| # | Task | Status |
|---|------|--------|
| 1 | Fix URL capture (LinkedIn, Facebook, Reddit) | **done** |

### Tier 2: Security & Product Gaps — COMPLETE
| # | Task | Status |
|---|------|--------|
| 2 | Stripe top-up idempotency | **done** |
| 3 | CSRF tokens | **done** |
| 4 | Rate limiting | **done** |
| 5 | Invitation UX (countdown, expired, decline) | **done** |
| 6 | Metrics accuracy (deletion, rate limits, dedup) | **done** |
| 7 | Repost campaign UI | **deferred** |
| 8 | Admin payout void/approve | **done** |

### Pending: Task #38
| # | Task | Status | Priority |
|---|------|--------|----------|
| 38 | E2E deleted post detection (all 4 platforms) | pending | high |

### Tier 3: Features Needing Deeper Specs
| # | Task | Status | Priority | Depends on |
|---|------|--------|----------|------------|
| 9 | Metric scraping per platform | pending | high | 1 ✓ |
| 10 | Billing (earnings calc, verify E2E) | pending | high | 9 |
| 11 | Earnings display (sync, withdrawal) | pending | high | 10 |
| 12 | AI matching (scoring logic) | pending | high | — |
| 13 | AI profile scraping | pending | high | — |
| 14 | 4-phase content agent | pending | high | 13 |
| 15 | AI campaign quality gate | pending | medium | — |
| 16 | Content formats (threads, polls) | pending | high | 14 |
| 17 | Free/Pro tiers | pending | medium | — |
| 18 | Write test suite | pending | high | 10, 11 |

### Tier 4–5 and Deferred
- Tier 4: #19 (Stripe live), #20 (PyInstaller), #21 (Mac), #22 (Landing page)
- Tier 5: #23-28 (polish tasks)
- Deferred: #7, #29-40 (repost, political, video gen, GDPR, etc.)

## Session 36 — Tasks #8, #5, #7 deferred, scraper fixes (2026-04-07)

### Task #8: Admin Payout Void/Approve

Two new per-payout actions on admin financial dashboard:
- **Void**: sets status="voided", returns budget to campaign, deducts from user balance, requires reason, audit log
- **Force-approve**: sets status="available" immediately (skips 7-day hold), audit log
- Button visibility: Void for pending+available, Approve for pending only, none for paid/voided/failed
- Added `available` and `voided` badge cases + filter dropdown options

**Verified via Chrome DevTools**: button visibility correct for all 6 statuses, approve changes pending→available, void changes pending→voided with reason in audit log.

**Commits**: `7bc663d`

### Task #5: Invitation UX

**Countdown timer**: JS reads `expires_at`, formats as "Xd Yh" / "Xh Ym" / "EXPIRED" with color coding (default→yellow→red). Updates every 60s.

**Expired state**: Red "EXPIRED" badge, card dimmed (opacity 0.5), buttons replaced with "This invitation has expired". Server now returns expired invitations in GET /invitations (sorted to bottom).

**Decline reason**: Click Reject → panel expands with 4 quick-select buttons + text input. Reason stored on `CampaignAssignment.decline_reason` (new column) + invitation log. Company campaign detail shows aggregated decline reasons with counts.

**Bug fix**: Campaigns page auto-refreshed every 10s due to hash mismatch (page hash included invitations but endpoint didn't). Fixed hash formula + increased interval to 30s.

**Verified via Chrome DevTools**: countdown colors correct (yellow for 1-6h, red for <1h), expired card dimmed with badge, decline reason "Payout too low" stored in DB, all 6 acceptance criteria passed.

**Commits**: `e45633d`, `981c0bd`, `27082b0`

### Metric Scraper Accuracy Fixes (continuing from Session 35)

Real-world testing against 14+ external posts found 8 bugs total:

| Bug | Platform | Fix |
|-----|----------|-----|
| LinkedIn "This post cannot be displayed" | LinkedIn | Added to deletion phrases |
| Unicode ellipsis/curly quote mismatch | X | Normalize unicode before matching |
| "this post was deleted" variant missing | Reddit | Added deleted + [removed] variants |
| `[deleted]` in comments = false positive | Reddit | Removed from body text search |
| Viral posts don't load in 3s | X | Wait for `[role="group"]` element |
| `aria-label="Like: 8K people"` not matched | Facebook | Added `Like:` pattern |
| LinkedIn CSS class gone | LinkedIn | 4-strategy fallback for reactions |
| Wrong post metrics on quoted posts | X | Use FIRST `[role="group"]` only |
| Views outside role=group | X | Fallback `aria-label*="views"` search |
| Engagement bar not parsed | Facebook | Consecutive numeric lines extraction |

**Commits**: `ec9d348`, `6f84ff5`, `3006fc1`, `fda3184`, `54484bd`, `9440c60`

### Task #7: Repost Campaign — DEFERRED

Decided to defer repost campaigns to post-launch. Full spec preserved in task-master task #7 description including: formats (text/image/text+image), posting frequency (once/daily/weekly), company edit UI, user read-only display, background agent pipeline skip. Some foundational code exists but feature is out of scope for launch.

**Commits**: `bd39c87` (implementation), `ea4c3c7` (deferral)

## Key Decisions (Session 36)

- **Proper verification**: Always test by running real app flows (browser automation, user walkthroughs), not just API calls or unit tests. Saved to memory as feedback.
- **Repost deferred**: Too much complexity for medium-priority feature. Core value is AI-generated campaigns.
- **Task #38 added**: E2E deleted post detection pipeline verification on all 4 platforms.

## Deployed URLs
- **Production**: https://server-five-omega-23.vercel.app
- **Company dashboard**: /company/login
- **Admin dashboard**: /admin/login (password: "admin")
- **User App**: localhost:5222

## Server Auth
- Local test company: `testco_metric@test.com` / `Test1234!`
- Local test user: `test_metric@test.com` / `Test1234!` (user_id=1)
- Local test user: `dassamaara@gmail.com` / `Test1234!` (user_id=2)
- Admin token cookie value: `valid`

## Test Commands
```bash
python scripts/user_app.py                    # Start user app on localhost:5222
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd server && vercel deploy --yes --prod       # Deploy to production
task-master list                              # See all tasks
python scripts/test_metric_accuracy.py phase1  # Test live scraping
python scripts/test_metric_accuracy.py phase2  # Test deletion detection
python scripts/test_metric_accuracy_external.py # Test against external posts
```
