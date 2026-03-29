# Amplifier — Task Context

**Last Updated**: 2026-03-29 (Session 23)

## Current Task

**Task #28 — Verify: Scheduled Posting** (in-progress)

Testing all post types (text-only, image+text, image-only) on all 4 platforms. Testing 1 platform at a time in order: X → LinkedIn → Facebook → Reddit.

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting (#27-#28), Metrics (#29-#30) | **#27 done, #28 in-progress** |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |
| Future | AI scrapers, content gen, video gen, tiers | #51-#66 | All pending |

**14 of 36 verify tasks done. 22 remaining + 16 future tasks.**

## Session 22 Summary (Previous Session)

Tasks #19-#22 completed (Matching + Campaign Polling). Key work:
- Matching: fully AI-driven, niche unification, platform format fix, scraped profiles sync
- Polling: invitation flow bug fixed, rich display, auto-reload, per-campaign notifications
- 8 docs created, FUTURE.md expanded, tasks.json encoding fixed
- LinkedIn reconnect auto-reset, Mistral import fix

## Session 23 — What Was Done (Current Session)

### Task #23/#24: AI Content Generation (Explain + Verify)
- **Explained** current single-prompt system, identified gaps vs SLC spec
- **Documented full requirements** for 4-phase AI agent rebuild (research, strategy, creation, review)
- Campaign goal drives content strategy (leads vs virality vs awareness vs engagement)
- Image intelligence: AI analyzes campaign images via vision API, matches to relevant posts
- Must-include items woven naturally, not forced into every post
- Content must look like real UGC (hooks, stories, imperfect language)
- Free API credit management (Gemini → Mistral → Groq fallback, stay within free limits)
- **Marked done** — current system documented, rebuild deferred to Task #63
- **Task #63 created**: Build 4-phase AI content agent (research before building — evaluate existing tools like Jasper, CrewAI, FeedHive for leverage)

### Task #25/#26: Content Review/Approval (Explain + Verify)
- **Verified**: approve/reject/edit/restore/unapprove/approve-all all work
- **Added Unapprove button** for approved (not yet posted) drafts — sets back to pending, removes from schedule
- **Fixed Reddit JSON display** — title+body rendered instead of raw JSON in both Today's Posts and Past Posts
- **Added company name** to campaign invitations and detail pages (required eagerly loading Company relationship)
- **Auto-reload** on campaigns + detail pages via hash polling (10s interval)
- **Per-campaign desktop notifications** when content is generated
- **Template auto-reload** enabled for development (TEMPLATES_AUTO_RELOAD + use_reloader)
- **Hot reload** enabled — Python code changes auto-restart app (use_reloader with WERKZEUG_RUN_MAIN check)

### Task #27: Explain: Scheduled Posting
- Walked through posting pipeline: scheduling → due detection → Playwright execution → URL capture → server sync
- Identified issues: X lockout detection needed, image attachment not wired up, scheduling not goal-driven
- **Task #66 created**: X lockout detection and user notification

### Task #28: Verify: Scheduled Posting (IN PROGRESS)

#### CRITICAL BUG FIXED: `human_delay` was sync, broke ALL posting
- `human_delay()` used `time.sleep()` but was called with `await` throughout ALL 4 platform posting functions
- This caused `TypeError: 'NoneType' object can't be awaited`, silently crashing every post attempt
- **Fix**: Changed to `async def human_delay()` using `asyncio.sleep()`
- This was THE root cause of all posting failures across all platforms

#### Other posting fixes:
- **human_type .first**: X compose has 2 `role=textbox` elements, strict mode failed. Added `.first`
- **Reddit posts to user profile**: Changed from random subreddit (spam-filtered) to `u/username/submit`
- **Reddit auto-detects username**: Navigates to `/user/me/`, extracts username from redirect URL
- **Image path support**: All 4 platforms now accept `draft.get("image_path")` for pre-existing images
- **LinkedIn URL capture**: Now checks home feed first (faster), then activity page as fallback
- **LinkedIn image upload**: Updated selectors — "Add media" button with file chooser
- **Empty text handling**: All platforms skip typing if text is empty (supports image-only posts)
- **Reddit image posts**: Switch to "Images & Video" tab, upload via file input
- **Reddit body optional**: Body field no longer required (supports image-only with just title)

#### Selector research via Chrome DevTools MCP:
- **LinkedIn**: `button "Start a post"` → `textbox "Text editor for creating content"` → `button "Add media"` (file chooser) → `button "Post"`
- **Facebook**: `button "What's on your mind?"` → `textbox` in dialog → `button "Photo/video"` (creates hidden `input[type="file"]`) → `button "Post"`
- **Reddit**: `/user/{username}/submit` → `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button "Post"`. Has "Images & Video" tab for image posts.
- **X**: Uses `data-testid` attributes (stable). `[data-testid="tweetButton"]` for post, `[data-testid="fileInput"]` for image.

#### Full test run (12 tests — 3 types × 4 platforms):
| Platform | Text-only | Image+Text | Image-only | URL Capture |
|----------|-----------|------------|------------|-------------|
| X | SUCCESS ✓ | SUCCESS ✓ | SUCCESS ✓ | 3/3 ✓ |
| LinkedIn | PARTIAL | SUCCESS | PARTIAL | 1/3 (timeout) |
| Facebook | FAILED | FAILED | FAILED | 0/3 (timeout) |
| Reddit | PARTIAL | PARTIAL | PARTIAL | 0/3 (no redirect) |

All posts were delivered (0 failures) but URL capture broken for LinkedIn/Facebook/Reddit.

#### Remaining to-dos for Task #28:
1. Test 1 platform at a time (X → LinkedIn → Facebook → Reddit)
2. For each: verify text-only, image+text, image-only posts
3. Fix URL capture for LinkedIn, Facebook, Reddit
4. Verify LinkedIn image actually uploads
5. Show all results with captured URLs
6. Delete all test posts via Chrome DevTools MCP

#### Test posts deleted:
- LinkedIn: 3 test posts deleted via Chrome DevTools MCP
- Facebook: 1 test post moved to trash
- Reddit: test posts auto-removed by spam filter
- X: test posts removed (likely by X automation detection)

### New Future Tasks Created This Session
- **#57**: Official social media APIs for profile data
- **#58**: AI campaign quality gate (85% min before activation)
- **#59**: AI browser agent scraping (browser-use or similar)
- **#60**: Metrics accuracy for billing (critical for trust)
- **#61**: Self-learning content generation
- **#62**: Free and paid tiers
- **#63**: Build 4-phase AI content agent (MAJOR)
- **#64**: Upgrade posting for all content formats + TikTok/Instagram
- **#65**: Platform-specific content preview in review UI
- **#66**: X lockout detection and user notification

### Key Decisions This Session
- Content gen rebuild deferred to Task #63 (after all verify tasks)
- Build vs buy decision required for content agent (evaluate Jasper, CrewAI, FeedHive before building custom)
- Tools should be chosen based on 3-6 month model trajectory (cheaper, faster, on-phone)
- Campaign goal drives content strategy (not hardcoded)
- Image intelligence: AI analyzes images via vision API, matches to relevant posts
- Scheduling determined by content agent strategy, not fixed 30-min spacing
- Reddit posts to user profile (avoids subreddit spam filters)
- All platforms support 3 content types: text-only, image+text, image-only

### Bugs Found & Fixed This Session
1. **human_delay sync (CRITICAL)** — `time.sleep()` called with `await`, crashed ALL posting silently
2. **human_type strict mode** — X has 2 textboxes, needed `.first`
3. **Reddit spam filter** — posts to subreddits got filtered, switched to user profile
4. **LinkedIn URL timeout** — feed page `goto` used default `wait_until="load"`, too slow
5. **Facebook timeout** — all `goto` calls timing out (30s), needs `wait_until="domcontentloaded"`
6. **Company relationship not loaded** — `campaign.company.name` failed in async, added `selectinload`
7. **Reddit JSON display** — raw JSON shown in draft review, now renders title + body

## Key Reference Files
- `scripts/post.py` — Platform posting functions (X, LinkedIn, Facebook, Reddit)
- `scripts/utils/post_scheduler.py` — Post scheduling and execution
- `scripts/background_agent.py` — Polling, content gen, posting loop
- `scripts/utils/content_generator.py` — AI content generation (single-prompt, to be rebuilt)
- `scripts/tests/test_all_post_types.py` — Full posting test suite (12 tests)
- `scripts/tests/test_matching_e2e.py` — E2E matching test (3 users × 3 campaigns)
- `docs/` — 8 comprehensive docs (architecture, API, models, user app, setup, matching, content gen, posting)
- `FUTURE.md` — 12 future feature specs with tool comparisons

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222

## Test Commands
```bash
# Run user app (with hot reload)
python scripts/user_app.py

# Run server locally
cd server && GEMINI_API_KEY=<key> python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Test posting (all platforms, all types)
python scripts/tests/test_all_post_types.py

# Test single platform
cd scripts && HEADLESS=false python -c "
from post import post_to_linkedin
# ... (see test_all_post_types.py for examples)
"

# E2E matching test
python scripts/tests/test_matching_e2e.py setup && python scripts/tests/test_matching_e2e.py test && python scripts/tests/test_matching_e2e.py cleanup

# Deploy
vercel deploy --yes --prod --cwd server
```
