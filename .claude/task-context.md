# Amplifier — Task Context

**Last Updated**: 2026-04-05 (Session 32)

## Current State

**Full audit completed. Task list reset. Detailed product specs written. Ready for implementation.**

The old 80-task list was audited and found to have ~20 tasks marked "done" that were incomplete or not implemented. The task list was reset to 37 tasks (28 active + 9 deferred). Detailed product specs were written for 16 tasks across 4 batches.

## Task List (37 total)

### Tier 1: Fix Broken Foundation (1 task)
| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Fix URL capture (LinkedIn, Facebook, Reddit) | pending | high |

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
| 9 | Metric scraping per platform | pending | high | 1 |
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

## Session 32 — What Was Done

### Full Audit of All 80 Tasks
- Ran comprehensive audit of every implemented feature
- Found ~20 tasks marked "done" that were incomplete or not implemented
- Key findings:
  - URL capture broken on 3/4 platforms (only X works)
  - CSRF tokens not verified in Flask forms
  - Rate limiting (slowapi) not installed
  - Invitation UX (countdown, expired badge) not implemented
  - Multiple Tier 5 items (#77-80) marked done but code doesn't exist
  - Repost campaign has backend but no company creation UI
  - Admin payouts are read-only (no void/approve)
  - Earnings display may not sync from server to local

### Task List Reset
- Removed all 80 old tasks from task-master
- Created 37 new tasks (28 active + 9 deferred) reflecting actual state
- Organized into 5 tiers by priority + launch tasks + deferred

### Detailed Product Specs Written (4 batches)
All specs at `docs/specs/`:

**Batch 1 — Money Loop** (`batch-1-money-loop.md`):
- Task #1: URL capture — test first, per-platform fix strategies
- Task #9: Metric scraping — every 24h for campaign lifetime, per-platform metrics (views X only, likes/comments all, reposts not Reddit), PRAW for Reddit, deleted post detection
- Task #10: Billing — formula with rate_per_comment added, rate_per_click removed, rate_per_1k_views X-only, 7-day hold, tier promotion, budget management
- Task #11: Earnings display — test first, server→local sync, withdrawal flow

**Batch 2 — AI Brain** (`batch-2-ai-brain.md`):
- Task #13: AI profile scraping — 3-tier token-efficient pipeline (text→elements→vision), per-platform extraction from real screenshots (X, LinkedIn, Facebook, Reddit), navigation: scroll AND click "Show all"/"...more"
- Task #12: AI matching — scoring weights (topic 40%, audience 25%, authenticity 20%, quality 15%), self-selected niches override profile, min score 40
- Task #14: Content agent — 4 phases (research with niche news, AI-driven strategy, creation, review), timeliness rule, anti-AI language
- Task #15: Quality gate — 2-layer (mechanical rubric 85/100 + server-side AI review for scams/harmful content)

**Batch 3 — Product Features** (`batch-3-product-features.md`):
- Task #16: Content formats — threads (X), polls (X, LinkedIn), link posts (Reddit). No LinkedIn carousel, no Facebook poll. Content agent decides format per-post.
- Task #5: Invitation UX — countdown timers with color coding, expired badge + gray-out, decline reason with quick-select
- Task #7: Repost campaign UI — partial platforms OK, all formats supported, users can't edit (read-only approve/reject)
- Task #8: Admin payouts — void (returns funds) and force-approve (skips hold) with audit logging

**Batch 4 — Business & Launch** (`batch-4-business-launch.md`):
- Task #17: Free/Pro tiers ($19.99/mo) — image gen on both tiers, post limit is gate (4 vs 20), 20% matching boost for Pro
- Task #19: Stripe live — existing father's Stripe account, company Checkout with idempotency, user Connect Express onboarding
- Task #22: Landing page — dual audience (companies + users), sections, mobile, SEO
- Task #6: Metrics accuracy — deleted post detection, rate limit handling, dedup

### Key Decisions Made This Session
1. **rate_per_click removed** — clicks can't be scraped from post pages
2. **Self-learning (#61) cancelled** — moved to deferred/post-launch
3. **Political campaigns removed** — out of scope
4. **Task #57 removed** — official APIs not part of implementation
5. **Image gen on both Free and Pro tiers** — no restriction
6. **Metric scraping: every 24h** (not tiered T+1h/6h/24h/72h schedule)
7. **Per-platform metrics**: views X only, likes all 4, comments all 4, reposts not Reddit
8. **Profile scraping: text-first** — 3-tier pipeline to minimize tokens (text→elements→vision)
9. **AI matching: self-selected niches override** profile analysis
10. **Quality gate: 2-layer** — mechanical rubric + server AI review
11. **Content agent: niche news** in research phase for timely content
12. **Repost campaigns: users can't edit** content (read-only)
13. **Father's Stripe account** available for Amplifier
14. **Local LLM** added as deferred task #37

### Session 31 Work (earlier in same day)
- Implemented #52/#63 (content agent), #61 (self-learning), #65 (preview UI), #51 (AI scraping), #53 (SLC spec)
- All later found to need deeper specs and re-implementation
- Removed click-based payouts
- Fixed Flask reloader tab spam
- Deployed to Vercel

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
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd server && vercel deploy --yes --prod       # Deploy to production
task-master list                              # See all tasks
```
