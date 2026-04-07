# Amplifier — Task Context

**Last Updated**: 2026-04-07 (Session 37)

## Current State

**Tier 2 complete + Task #38 done. Next: Task #9 (Metric Scraping) — first domino in the money loop.**

38 total tasks: 8 done, 20 pending, 10 deferred. Critical path: #9 → #10 → #11 → #18/#19.

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

### Task #38 — COMPLETE
| # | Task | Status |
|---|------|--------|
| 38 | E2E deleted post detection (all 4 platforms) | **done** |

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
- Deferred: #7, #29-37 (repost, political, video gen, GDPR, etc.)

## Session 37 — Task #38: E2E Deleted Post Detection (2026-04-07)

### What Was Done

Tested deleted post detection against real deleted posts on all 4 platforms. Found 2 bugs, fixed both, verified fixes.

### Test Methodology

1. Used existing live posts on all 4 platforms (user provided Facebook, Reddit, X URLs)
2. Created a test LinkedIn post via Playwright automation script
3. User deleted all 4 posts
4. Ran deletion detection test script against deleted URLs
5. Also ran against 5 live posts to verify no false positives

### Bugs Found and Fixed

| Platform | Bug | Root Cause | Fix |
|----------|-----|------------|-----|
| **Reddit** | User-deleted posts not detected | Reddit shows `u/[deleted]` + `author="[deleted]"` on `shreddit-post` element, but scraper only checked `removed="true"` (mod removals) and text phrases | Added `shreddit-post[author="[deleted]"]` and `is-author-deleted` attribute checks |
| **Facebook** | Author sees cached post content on deleted posts | Facebook serves stale content to the post author via share URLs. Permalink URLs show empty feed with "No more posts" but no explicit deletion message | Added "no more posts" detection for permalink URLs + "content isn't available right now" phrase |

### Key Finding: Facebook Caching Behavior

- **Share URLs** (`/share/p/...`): Facebook caches full post content for the author even after deletion — scraper can't detect deletion via share URLs
- **Permalink URLs** (`/permalink.php?story_fbid=...`): Shows empty feed with "No more posts" — detectable
- **Non-author visitors**: See standard "This content isn't available" message — already detected
- **Production impact**: Amplifier captures permalink URLs during posting, so the fix covers the real use case

### Test Results

**Deleted posts (true positives):** 4/4 detected
- X: Detected via "this page doesn't exist" phrase ✓
- LinkedIn: Detected via "this page doesn't exist" phrase ✓
- Facebook: Detected via "no more posts" on permalink ✓
- Reddit: Detected via `shreddit-post[author="[deleted]"]` ✓

**Live posts (true negatives):** 5/5 correctly left alone
- 2 Facebook posts: returned real metrics ✓
- 1 LinkedIn post: returned 2,026 impressions, 12 likes ✓
- 1 X post: returned 10 views ✓
- 1 Reddit post: returned 15 views, 1 upvote ✓

### Files Changed

- `scripts/utils/metric_scraper.py` — Added Reddit author deletion check + Facebook permalink detection
- `docs/specs/batch-1-money-loop.md` — Updated deletion detection signals table
- `docs/specs/batch-4-business-launch.md` — Updated deletion detection signals table
- `scripts/test_deletion_detection.py` — New test script (kept for regression testing)

**Commit**: `721c654`

## Session 36 — Tasks #8, #5, #7 deferred, scraper fixes (2026-04-07)

### Task #8: Admin Payout Void/Approve

Two new per-payout actions on admin financial dashboard:
- **Void**: sets status="voided", returns budget to campaign, deducts from user balance, requires reason, audit log
- **Force-approve**: sets status="available" immediately (skips 7-day hold), audit log
- Button visibility: Void for pending+available, Approve for pending only, none for paid/voided/failed

### Task #5: Invitation UX

**Countdown timer**: JS reads `expires_at`, formats as "Xd Yh" / "Xh Ym" / "EXPIRED" with color coding.
**Expired state**: Red badge, card dimmed, buttons replaced with "This invitation has expired".
**Decline reason**: Click Reject → panel expands with 4 quick-select buttons + text input. Stored on `CampaignAssignment.decline_reason`.

### Task #7: Repost Campaign — DEFERRED & HIDDEN

Deferred to post-launch. Toggle commented out in `campaign_create.html`. All backend code preserved.

### Metric Scraper Fixes (Session 35-36)

8 bugs fixed across all 4 platforms from real-world testing against 14+ external posts (metric extraction accuracy, not deletion detection).

## Key Decisions

- **Task #38 before #9**: User chose to verify deletion detection E2E before moving to metric scraping spec, completing the detection story fully.
- **Permalink URLs for Facebook**: Detection relies on permalink format (what Amplifier captures), not share URLs (which cache content).
- **Proper verification**: Always test by running real app flows, not just API calls or unit tests.
- **Repost deferred**: Hidden via 1-line change, not removed.

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
python scripts/test_deletion_detection.py     # Test deleted post detection (update URLs first)
python scripts/test_metric_accuracy.py phase1  # Test live scraping
python scripts/test_metric_accuracy.py phase2  # Test deletion detection
python scripts/test_metric_accuracy_external.py # Test against external posts
```
