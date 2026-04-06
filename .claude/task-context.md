# Amplifier — Task Context

**Last Updated**: 2026-04-06 (Session 33)

## Current State

**Task #1 (URL Capture) completed and verified on all 4 platforms. Ready for Tier 2.**

37 total tasks: 1 done, 27 pending, 9 deferred. Detailed product specs exist for 16 tasks across 4 batches in `docs/specs/`.

## Task List (37 total)

### Tier 1: Fix Broken Foundation — COMPLETE
| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Fix URL capture (LinkedIn, Facebook, Reddit) | **done** | high |

### Tier 2: Incomplete Security & Product Gaps (7 tasks)
| # | Task | Status | Priority |
|---|------|--------|----------|
| 2 | Stripe top-up verification + idempotency fix | pending | high |
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
| 19 | Stripe live integration (Checkout + Connect) | pending | high | 2, 10 |
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

## Session 33 — Task #1: URL Capture Fix (2026-04-06)

### What Was Done

**Implemented URL capture for all 4 platforms, tested end-to-end with live posts.**

#### Script Executor Upgrade (`scripts/engine/script_executor.py`)
- `_handle_extract_url` now supports 3-tier extraction: CSS selectors → JavaScript → page URL fallback
- Added `url_pattern` field: extracted URLs must contain a substring (e.g., `/comments/` for Reddit, `/feed/update/` for LinkedIn) — prevents capturing wrong URLs
- Added `_normalize_href()` and `_validate_url()` helpers
- `url_pattern` field added to `ScriptStep` in `script_parser.py`

#### Platform-Specific Fixes

**X** — Already working. No changes needed.
- Selector: `article[data-testid='tweet'] a[href*='/status/']` on profile page

**LinkedIn** — Fixed via "View post" dialog + activity page JS fallback
- Primary: CSS selector for "View post" link in success dialog (works for image posts)
- Fallback: JS extraction on activity page for `urn:li:activity` or `urn:li:share` links
- `url_pattern: "/feed/update/"` prevents capturing analytics links
- Had to re-login via `login_setup.py linkedin` (session was expired)

**Facebook** — Fixed via activity log instead of profile page
- Navigate to `facebook.com/me/allactivity?category_key=MANAGEYOURPOSTS` (strict chronological order)
- JS scans links for `/posts/`, `pfbid`, `story_fbid` patterns, strips `comment_id` params
- Profile page fallback with innerHTML `pfbid` regex search
- Key insight: Facebook profile page doesn't guarantee chronological order; activity log does

**Reddit** — Fixed via JS-only extraction with timestamp sorting
- Removed CSS selectors entirely (they matched nav tab `/user/.../comments/` instead of posts)
- JS reads `shreddit-post` element `permalink` attributes with `created-timestamp` sorting
- Navigate to `submitted/?sort=new` to ensure newest post is first
- `url_pattern: "/comments/"` accepts both `/r/subreddit/comments/...` and `/user/.../comments/...`
- Key insight: posts to user profile use `/user/` not `/r/` — pattern must accept both

#### Bug Fixes
- **Legacy functions swallowing exceptions** (`post.py`): All 4 legacy platform posting functions caught exceptions and returned `None`, causing false `posted_no_url` status when posting actually failed. Changed to re-raise.
- **`resolved_assignment_id` NameError** (`post_scheduler.py`): Variable was only defined in the success branch but used in both success and no-url branches. Moved DB lookup before the if/else.
- **Double-posting on URL capture failure**: `post_via_script` now returns `""` (not `None`) when post succeeds but URL capture fails, preventing legacy fallback from posting again.

#### Spec Updates
- Reddit views are scrapeable (visible on post pages) — updated batch-1 spec, task-context, tasks 9 and 10
- `rate_per_1k_views` applies to X AND Reddit (not X-only)
- Playwright preferred over PRAW for Reddit metric scraping (PRAW can't get views)
- `metric_collector.py` updated to route Reddit to Playwright

### Verified Test Results (Live Posts)

| Platform | Captured URL | Verified |
|----------|-------------|----------|
| X | `x.com/SamaaraDas/status/2041144200289464455` | ✅ |
| LinkedIn | `linkedin.com/feed/update/urn:li:share:7446910068303953920/` | ✅ |
| Facebook | `facebook.com/permalink.php?story_fbid=pfbid0TNU9kgoLRJfVbMA2ej8nhjq2jshiKwcx2t2A9Ei8rSpQqeB4cCtorAdZCYnknYK6l&id=100086447984609` | ✅ |
| Reddit | `reddit.com/user/SamaaraDas/comments/1sdzj1b/url_capture_test_round_6/` | ✅ |

### Testing Iterations (6 rounds)
1. Round 1: X ✅, LinkedIn ❌ (session expired), Facebook ❌ (profile URL), Reddit ❌ (user page)
2. Round 2: LinkedIn re-login → ✅, Reddit selector matched wrong link, Facebook CSS+JS found nothing
3. Round 3: Reddit `url_pattern: "/r/"` rejected user-profile posts, Facebook innerHTML found old pfbid
4. Round 4: Facebook activity log approach → ✅, Reddit pattern changed to `/comments/` → ✅
5. Round 5: Reddit JS found correct URL but `url_pattern: "/r/"` rejected `/user/` posts
6. Round 6: All 4 platforms ✅ — user verified all URLs point to correct posts

### Key Decisions
1. **Reddit views ARE scrapeable** — visible on post pages, PRAW can't get them but Playwright can
2. **Activity log for Facebook** — profile page doesn't guarantee chronological order
3. **JS-only for Reddit** — CSS selectors too unreliable (match nav tabs, not posts)
4. **Legacy functions must re-raise** — returning None on failure causes false posted_no_url

### Uncommitted Changes (NOT part of Task #1)
These files have changes that revert CSRF/slowapi work — do NOT commit them as-is:
- `scripts/templates/user/login.html` — removes CSRF script
- `scripts/templates/user/onboarding.html` — removes CSRF script
- `server/app/main.py` — removes slowapi
- `server/app/routers/auth.py` — removes rate limiting
- `server/app/routers/admin/login.py` — removes rate limiting
- `server/app/routers/company/login.py` — removes CSRF
- `server/requirements.txt` — removes slowapi dep

These need investigation before committing — they may be accidental reversions.

## Deployed URLs
- **Production**: https://server-five-omega-23.vercel.app
- **Company dashboard**: /company/login
- **Admin dashboard**: /admin/login
- **User App**: localhost:5222

## Server Auth
- Primary: `dassamaara@gmail.com` / `1304sammy#`
- Company test: `amplifier.testco@gmail.com` / `TestCo2026!`
- Auth file: `config/server_auth.json` (encrypted)

## Key Constraints
- All AI must be free or very cheap (Gemini, Mistral, Groq free tiers)
- User's own API keys used for all user-app AI operations
- Server's keys used for matching and campaign wizard
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
