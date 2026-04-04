# Amplifier — Remaining Work (Complete Task Specification)

**Date**: April 4, 2026
**Status**: 27 of 80 tasks done. 53 remaining.
**Current state**: Core loop built but unverified. v2/v3 upgrade sprint completed (JSON posting engine, financial safety, AI abstraction, image generation, reputation tiers). No automated tests. No real payments. URL capture broken on 3/4 platforms.

---

## How This Document Is Organized

5 tiers, from "must work before anyone uses this" to "growth features."

- **Tier 1**: Core loop verification — the code exists, never tested E2E
- **Tier 2**: Product gaps — things the SLC spec requires that are missing or broken
- **Tier 3**: Data integrity, testing, documentation
- **Tier 4**: Confirmed feature builds from FUTURE.md
- **Tier 5**: UX polish, admin verification, compliance
- **Launch tasks**: Stripe integration, Mac support, packaging, landing page

Each task includes its task-master ID, priority, dependencies, and full description.

---

## Tier 1: Core Loop Must Work

These are Explain/Verify task pairs. "Explain" walks through how the feature currently works and identifies gaps. "Verify" tests it against acceptance criteria with real data. Nothing else matters until these pass — the entire money loop (company pays → user posts → metrics scraped → billing runs → user earns) depends on every link in this chain working.

---

### Task #28 — Verify: Scheduled Posting
**Status**: In-progress (paused since Session 23)
**Priority**: High
**Depends on**: #27 (done)

Ask the user what the acceptance criteria is for scheduled posting so that we know when it's fully done. Then test against those criteria.

MUST TEST: Both semi-auto and full-auto modes work correctly. Semi-auto: AI generates content, user reviews and approves before posting. Full-auto: AI generates and posts automatically without review.

**Known issues from Session 23 testing:**
- URL capture fails on LinkedIn (timeout waiting for "View post" dialog)
- URL capture fails on Facebook (timeout, no post permalink exposed)
- URL capture fails on Reddit (redirect to /submitted/?created= not detected)
- X URL capture works (3/3 success)
- All posts were DELIVERED to all 4 platforms (0 delivery failures)
- The problem is exclusively URL capture, not posting itself

**What needs fixing:**
1. Fix URL capture for LinkedIn — "View post" dialog may not appear for text-only posts. Fallback to activity page `/in/me/recent-activity/all/` and grab first `a[href*="/feed/update/"]`
2. Fix URL capture for Facebook — React UI doesn't expose permalinks as `<a>` tags. Use profile URL as reliable fallback
3. Fix URL capture for Reddit — wait for URL change to contain `/submitted/?created=` or poll for `/comments/` in URL
4. Verify LinkedIn image actually uploads via ClipboardEvent paste
5. Re-test all platforms with URL capture fixes (text-only, image+text, image-only)

**Verified platform selectors (Session 23):**
- LinkedIn: `button "Start a post"` → `textbox "Text editor..."` → `button "Add media"` → `button "Post"`
- Facebook: `button "What's on your mind?"` → `textbox` → `button "Photo/video"` → `button "Post"`
- Reddit: `/user/{username}/submit` → `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button "Post"`
- X: `data-testid` attributes. `[data-testid="tweetButton"]`, `[data-testid="fileInput"]`

---

### Task #29 — Explain: Metric Scraping
**Status**: Pending
**Priority**: High
**Depends on**: #27 (done)

Walk through how metric scraping currently works — scraping schedule (T+1h/6h/24h/72h), per-platform scraping methods (API vs browser), data captured (impressions, likes, reposts, comments), server sync. If the user finds it's not implemented the way they want, fix it.

IMPACT AUDIT: After explaining, list which other features this touches and could break if changed.

**Current implementation** (`scripts/utils/metric_scraper.py`, 552 lines):
- Scraping tiers: T+1h (verify live), T+6h (early engagement), T+24h (primary metric), T+72h (final, is_final=1 for billing)
- Per-platform: X (aria-labels on engagement buttons), LinkedIn (CSS selectors + regex fallback), Facebook (aria-labels + body text), Reddit (shreddit-post attributes)
- Launches persistent Playwright context per platform (reuses user's logged-in profile)
- Stores in `local_metric` table, syncs unreported metrics to server via `report_metrics()`

---

### Task #30 — Verify: Metric Scraping
**Status**: Pending
**Priority**: High
**Depends on**: #29

Ask the user what the acceptance criteria is for metric scraping so that we know when it's fully done. Then test against those criteria.

MUST TEST: Metrics are scraped at the correct intervals. Scraped values match what's visible on the platform. Metrics sync to server correctly. is_final flag set correctly at T+72h.

---

### Task #31 — Explain: Billing
**Status**: Pending
**Priority**: Medium
**Depends on**: #29

Walk through how billing/earnings calculation currently works — per-metric rates (CPM/CPE), platform cut (20%), budget capping, deduplication, payout creation, earning triggers. If the user finds it's not implemented the way they want, fix it.

**Current implementation** (`server/app/services/billing.py`):
- `calculate_post_earnings_cents()` — all math in integer cents
- `run_billing_cycle()` — incremental (each metric submission), dedup by metric ID in payout.breakdown, caps to remaining budget, auto-pause/complete on exhaustion
- `promote_pending_earnings()` — moves pending → available after 7-day hold (EARNING_HOLD_DAYS=7)
- `void_earnings_for_post()` — voids pending earnings when fraud detected during hold period, returns funds to campaign budget
- `_check_tier_promotion()` — auto-promotes user tier after each successful billing (20 posts → grower, 100 posts + trust >= 80 → amplifier)
- Amplifier tier gets 2x CPM multiplier

IMPACT AUDIT: After explaining, list which other features this touches and could break if changed.

---

### Task #32 — Verify: Billing
**Status**: Pending
**Priority**: Medium
**Depends on**: #31

Ask the user what the acceptance criteria is for billing so that we know when it's fully done. Then test against those criteria.

MUST TEST: Earnings calculated correctly in cents. Platform cut applied. Budget deducted. No double-billing. Hold period works (7 days). Budget exhaustion triggers auto-pause/complete. Tier CPM multiplier applied for amplifier users.

---

### Task #33 — Explain: Earnings/Stats
**Status**: Pending
**Priority**: Medium
**Depends on**: #31

Walk through how the earnings and statistics display currently works — total earnings, pending/paid breakdown, per-campaign earnings, withdrawal flow, stats calculations on user dashboard. If the user finds it's not implemented the way they want, fix it.

**Current implementation** (`scripts/user_app.py` earnings routes):
- `/earnings` page shows: total earned, available balance, pending balance, per-campaign breakdown, payout history
- `/earnings/withdraw` POST creates payout record ($10 minimum)
- Dashboard cards show: active campaigns, posts this month, total earned, platform health

IMPACT AUDIT: After explaining, list which other features this touches and could break if changed.

---

### Task #34 — Verify: Earnings/Stats
**Status**: Pending
**Priority**: Medium
**Depends on**: #33

Ask the user what the acceptance criteria is for earnings and statistics so that we know when it's fully done. Then test against those criteria.

MUST TEST: Numbers on earnings page match actual billing records. Pending vs available distinction works. Per-campaign breakdown is accurate. Withdrawal flow creates correct payout record.

---

### Task #35 — Explain: Stripe Top-up
**Status**: Pending
**Priority**: Medium
**Depends on**: #15 (done)

Walk through how company Stripe top-up currently works — checkout session creation, success verification, balance crediting, fallback instant-credit for dev, payment history. If the user finds it's not implemented the way they want, fix it.

**Current implementation** (`server/app/services/payments.py`):
- `create_company_checkout()` — creates Stripe Checkout session for top-up
- `verify_checkout_session()` — retrieves completed session, returns {company_id, amount_cents, payment_status}
- Company billing page at `/company/billing` with Stripe Checkout integration
- Test mode: instant balance credit if no Stripe key configured

IMPACT AUDIT: After explaining, list which other features this touches and could break if changed.

---

### Task #36 — Verify: Stripe Top-up
**Status**: Pending
**Priority**: Medium
**Depends on**: #35

Ask the user what the acceptance criteria is for Stripe top-up so that we know when it's fully done. Then test against those criteria.

MUST TEST: Checkout session creates correctly. Payment confirmation updates company balance. Balance reflects correctly on dashboard. Budget deduction on campaign activation works with the credited balance.

---

### Task #37 — Explain: Campaign Detail Page
**Status**: Pending
**Priority**: Medium
**Depends on**: #19 (done)

Walk through how the campaign detail page currently works — stats cards, per-platform breakdown, influencer table, invitation funnel, budget display, post performance. If the user finds it's not implemented the way they want, fix it.

NEEDED: Add image and file upload capability to the Edit Campaign form. Currently the campaign detail page shows campaign data but may not allow editing assets/images.

IMPACT AUDIT: After explaining, list which other features this touches and could break if changed.

---

### Task #38 — Verify: Campaign Detail Page
**Status**: Pending
**Priority**: Medium
**Depends on**: #37

Ask the user what the acceptance criteria is for the campaign detail page so that we know when it's fully done. Then test against those criteria.

MUST TEST: Stats cards show correct numbers. Per-platform breakdown matches actual posts. Creator table shows each user's posts and earnings. Invitation funnel counts are accurate. Budget display matches billing records.

---

## Tier 2: Product Gaps

These are features/fixes that any real user would hit immediately. The SLC spec defines them as v1 requirements.

---

### Task #66 — Detect X (Twitter) Account Lockout
**Priority**: High
**Dependencies**: None

When Amplifier opens X for posting or scraping, detect if the account is locked. X shows a minimal white page with heading like "Your account got locked" when automation is detected. Amplifier must:

1. Check for lockout page after navigating to X
2. If detected, skip posting/scraping for X
3. Send desktop notification: "Your X account is locked. Open X in your browser to unlock it."
4. Mark X session as "locked" in session health (prevents further posting attempts)
5. Periodically re-check (next session health cycle) to detect when user has unlocked

This was identified during Session 23 testing when X locked a test account during Playwright automation.

---

### Task #67 — Improve Session Health Check Reliability
**Priority**: Medium
**Dependencies**: None

Current `session_health.py` returns yellow (uncertain) for platforms that are actually logged in (LinkedIn, Reddit, X). Auth element selectors need updating to match current platform UIs. Reduce false-positive expired notifications.

Fixes needed:
- Retry logic before notifying (single check may fail due to page load timing)
- Use actual posting success as strongest signal of session health
- Update auth detection selectors per platform

---

### FTC Disclosure (No task ID — new work)

Content generator must auto-append advertising disclosure to every campaign post. US FTC requires `#ad` or `#sponsored` on paid promotional content. Implementation:
- Campaign model gains `disclaimer_text` field (e.g., "Paid for by [company]" or "#ad")
- Content generator appends disclaimer to every post
- Per-platform formatting: X in last line, LinkedIn at bottom, Reddit in footer, Facebook as tag
- Default if company doesn't specify: `#ad`

---

### Task #70 — Fix Draft Notification Count
**Priority**: Medium
**Dependencies**: None

Two bugs in the pending drafts notification:
1. `get_pending_drafts()` counts ALL unapproved drafts across all dates, not just today. Stale drafts from days ago inflate the count (showed 54 when only 12 were from today). Fix: filter to today only, or at minimum only count drafts from the last 24h.
2. Navigation badge should update in real-time or on page load, not just on poll.

---

### Task #71 — User App: Password Reset Flow
**Priority**: High
**Dependencies**: None

No way to reset a forgotten password — users are permanently locked out. Add:
- `POST /api/auth/forgot-password` — generate time-limited reset token
- `POST /api/auth/reset-password` — verify token + set new password
- Send reset link via email (or display token for MVP)
- Reset tokens expire after 1 hour

---

### Task #72 — User App: CSRF Protection
**Priority**: High
**Dependencies**: None

All POST forms in `user_app.py` have no CSRF tokens — vulnerable to cross-site request forgery. Add CSRF protection:
- Install `flask-wtf` or implement manual CSRF tokens
- Add hidden `csrf_token` field to every POST form
- Validate token on every POST endpoint

---

### Task #73 — User App: Encrypt Stored Credentials
**Priority**: High
**Dependencies**: None

API keys in local SQLite are now encrypted (done in session 26 via `_SENSITIVE_KEYS`). But auth tokens in `config/server_auth.json` are still plaintext. Fix:
- Encrypt server auth token at rest using `scripts/utils/crypto.py`
- Decrypt on read for API calls
- Consider using OS keychain (`keyring` library) as alternative

---

### Task #74 — User App: Rate Limiting + API Key Validation + Campaign Search
**Priority**: High
**Dependencies**: None

Three items:
1. Add rate limiting on login/register endpoints (5 attempts/min)
2. Test API key validity on save in settings — call the provider and verify before accepting
3. Add search by title and filter by status to campaign list on dashboard

---

### Task #75 — User App: Improve Content Draft UX
**Priority**: High
**Dependencies**: None

Five items:
1. Show campaign `content_guidance` alongside draft during review — user needs to see what the company expects
2. Add draft versioning — store original AI-generated + user-edited versions
3. Add character counts for all platforms (X: 280, LinkedIn: 3000, Facebook: 63206, Reddit title: 300, Reddit body: 40000)
4. Fix Reddit JSON format error handling with try/except in template rendering
5. Show generated image preview alongside draft text

---

### Task #76 — User App: Fix Invitation UX Gaps
**Priority**: High
**Dependencies**: None

Four items:
1. Add expiry countdown timers ("expires in 2h 15m") instead of raw timestamps
2. Clearly mark expired invitations with EXPIRED badge and gray them out
3. Capture optional decline reason when user rejects campaigns — send to company
4. Require at least 1 niche during onboarding for matching to work (currently allows 0 niches)

---

## Tier 3: Data Integrity, Testing & Documentation

---

### Task #60 — Ensure Metrics Accuracy for Billing
**Priority**: High
**Dependencies**: None

Metrics must be accurate — earnings and billing HEAVILY depend on them. Wrong metrics = wrong payouts = lost trust. Required:

1. Cross-validate scraped metrics against platform analytics (where available via APIs)
2. Handle edge cases: deleted posts, private accounts, rate-limited scraping
3. Consider using official APIs (X API v2, Reddit API) for metrics instead of scraping
4. Add metric sanity checks: flag anomalies (sudden 100x engagement spike = probably fake)
5. Audit trail: log every metric scrape with timestamp, source, raw values
6. T+72h metric marked `is_final=1` must be the billing source of truth

This is a prerequisite for trust in the billing system.

---

### Task #53 — Update SLC Spec
**Priority**: High
**Dependencies**: None (originally depended on #50, but can be done incrementally)

After all explain/verify tasks (#28-50) are complete, update `SLC.md` to accurately reflect what Amplifier does TODAY. This is the single living specification document. Remove anything that doesn't exist, add anything that was changed during verify tasks and the v2/v3 upgrade sprint.

The current SLC.md (dated March 25, 2026) is significantly outdated — it predates the JSON posting engine, image generation upgrade, earning hold periods, reputation tiers, AES encryption, and all other session 26 upgrades.

The result should be: if someone reads only this doc, they understand exactly what Amplifier does, how it works, and what its current limitations are.

---

### Task #54 — Write Tests for All Verified Features
**Priority**: High
**Dependencies**: #53

After all explain/verify tasks are done and docs are updated, write automated tests to lock down the verified behavior. Cover:

1. Company wizard + AI generation
2. Campaign matching (hard filters + AI scoring)
3. User onboarding + scraping
4. Content generation pipeline (text + image, all 3 modes)
5. Posting pipeline (JSON script engine + legacy fallback)
6. Metric scraping (per-platform selectors)
7. Billing calculation (cents math, hold periods, tier CPM, budget capping, dedup)
8. Earnings display
9. Stripe top-up flow
10. Admin pages (CRUD operations)

Tests should test the actual behavior confirmed during verify tasks — not hypothetical behavior. No test suite currently exists; all verification is manual against real platforms.

---

## Tier 4: Confirmed Feature Builds

These are from FUTURE.md. The code architecture supports them but they're not built yet. Each requires new code, not just verification.

---

### Tasks #51 + #59 — AI-Powered Profile Scraping
**Priority**: High
**Dependencies**: None

**What it replaces**: Current profile scrapers (`scripts/utils/profile_scraper.py`, 1,645 lines) use CSS selectors and regex to extract data from social media pages. These break constantly when platforms change their DOM. The scraper misses data, picks up wrong text (e.g., group names instead of post content), and can't understand context.

**What to build**: Replace brittle selector-based scraping with AI-powered extraction.

**Approach (from FUTURE.md):**
1. Navigate to each profile page with Playwright (existing flow)
2. Take a screenshot or extract body text
3. Send to Gemini Vision API: "Extract this person's profile data: name, bio, followers, recent posts with engagement, content themes, audience demographics"
4. Parse the structured JSON response
5. AI can also classify niches, detect content quality, estimate audience demographics

**Two complementary approaches from tasks #51 and #59:**
- Task #51: Gemini Vision on screenshots — send screenshot, get structured data back. No selectors at all.
- Task #59: AI browser agent (browser-use, AgentQL, Skyvern, or custom Playwright + LLM pipeline) — AI navigates the profile like a human, scrolling through posts, reading bios, understanding context.

**Cost consideration**: Gemini 2.0 Flash has free tier. One API call per platform per scrape. ~4 calls per onboarding = negligible cost.

**Advantages over current scraping:**
- Robust: no selectors to break when platforms update their UI
- Deeper: AI understands context, tone, audience — not just numbers
- Better anti-detection: AI browsing patterns look more human
- More data: extracts insights that selectors can't (content quality, posting style, audience sentiment)

**Tools to evaluate at implementation time**: browser-use, Playwright + Gemini Vision, AgentQL, Skyvern, or custom Playwright + LLM pipeline.

---

### Tasks #52 + #63 — 4-Phase AI Content Agent
**Priority**: High (Critical — core value proposition)
**Dependencies**: #54

**What it replaces**: Current `ContentGenerator` uses a single prompt to generate text + image_prompt. No research beyond URL scraping. No strategy adaptation based on campaign goal. No learning from performance. Same prompt structure regardless of whether the goal is "viral views" or "lead generation."

**What to build**: Replace the single-prompt content generator with a sophisticated 4-phase AI agent system.

**Phase 1 — Research (weekly per campaign):**
- Deep-dive into the product using ALL campaign sources (brief, scraped URLs, uploaded files, images)
- Competitor research: what are competitors posting? What content formats work in this niche?
- Trend research: what's trending in this niche/industry right now?
- Image intelligence: analyze campaign images via vision API (Gemini Vision), understand what each shows
- Results cached and reused daily, refreshed weekly

**Phase 2 — Strategy (per campaign, refreshed weekly):**

Campaign goal drives everything:
- **LEADS**: links to product, strong CTAs, landing page mentions, conversion-focused
- **VIRALITY**: emotionally triggering, images/videos, high posting frequency, shareable hooks
- **BRAND AWARENESS**: natural product mentions, lifestyle content, consistent presence
- **ENGAGEMENT**: questions, polls, controversial takes, discussion starters

Decides per-platform: post type (text/image/video/thread/poll/carousel), posting frequency, tone, scheduling.

**This is where campaign goal and tone control the output format.** Currently, `campaign_goal` and `tone` are accepted by the wizard but not stored on the Campaign model and not used during content generation. The 4-phase agent fixes this:
- Campaign model gains `campaign_goal` field (brand_awareness, leads, virality, engagement)
- Campaign model gains `tone` field (professional, casual, edgy, educational, etc.)
- Campaign model gains `preferred_formats` field (JSON: per-platform format preferences)
- Strategy phase reads goal + tone + formats and produces a per-platform content plan
- Creation phase follows the strategy plan, not a generic prompt

**Phase 3 — Content Creation (daily):**
- Platform-native UGC that looks REAL (not polished marketing)
- Hooks: emotional triggers, curiosity gaps, contrarian takes, real-life scenarios, stories
- Imperfect language (casual, not corporate-perfect)
- Each platform has its own style (X: punchy, LinkedIn: story, Reddit: genuine, Facebook: conversational)
- NOT compulsory to use all assets/hashtags in every draft
- Images matched to posts by content relevance (not blindly attached)
- Content types: text-only, image-only, image+text, thread, poll, carousel (based on strategy phase)

**Phase 4 — Review (per draft):**
- Semi-auto: drafts shown to user with per-campaign desktop notification
- Full-auto: auto-approved and scheduled immediately

**Scheduling decision**: The content agent (Phase 2 Strategy) should determine the scheduled posting time for each draft, not the review/approval flow. The agent decides WHEN to post based on campaign goal, target region timezone, platform peak hours, and posting frequency strategy.

**Build vs Buy Decision (from FUTURE.md):**
BEFORE BUILDING: Research existing AI tools/frameworks that could handle this. Evaluate: Jasper API, Copy.ai API, CrewAI, AutoGen, LangGraph, FeedHive API, Predis.ai. Goal is leverage — use an existing tool if it does 80% of what we need. Only build custom if nothing fits (most are designed for single users, not a marketplace).

If building custom, use Gemini/Mistral/Groq APIs with the 4-phase ContentAgent architecture:
```
ContentAgent
├── ResearchPhase (weekly)
│   ├── product_deep_dive(campaign) → product_knowledge
│   ├── competitor_scan(niche) → competitor_insights
│   ├── trend_scan(niche) → trending_topics
│   └── image_analysis(images) → image_descriptions
├── StrategyPhase (weekly, uses research)
│   ├── goal_strategy(campaign_goal) → content_strategy
│   ├── platform_plan(platforms) → per_platform_config
│   └── scheduling_plan(region, platforms) → posting_schedule
├── CreationPhase (daily, uses strategy + research)
│   ├── generate_drafts(strategy, research) → drafts[]
│   ├── match_images(drafts, images) → drafts_with_images[]
│   └── quality_check(drafts) → filtered_drafts[]
└── ReviewPhase (per draft)
    ├── semi_auto → show to user, notify
    └── full_auto → approve + schedule
```

---

### Task #58 — AI Campaign Quality Gate
**Priority**: Medium
**Dependencies**: None

AI checks campaign completeness and quality before company can activate. Campaigns below 85% get specific feedback ("Add more product details", "Your brief is too vague") and cannot be activated until fixed.

**Quality rubric:**
- Does the brief explain what the product actually is?
- Are there enough details for a creator to write authentic content?
- Are payout rates reasonable for the niche?
- Are must-include items clear and achievable?
- Does the content guidance give useful direction?

**Open question**: Should this block creation entirely, or just warn? Should the threshold be configurable? Decide before implementing.

---

### Task #61 — Self-Learning Content Generation
**Priority**: Medium
**Dependencies**: #54

The content generation AI should learn and improve over time:

1. **Learn from others**: Study what competitors, industry leaders, and trending creators post in the same niche. Understand what formats, hooks, and topics get engagement.

2. **Learn from own performance**: Track which posts got high engagement vs low. Identify patterns: which hooks worked, which platforms performed best, which posting times converted. The `agent_content_insights` table already exists in the local database for this purpose.

3. **Experiment + double down**: Try different content styles (stories, lists, questions, controversial takes). Measure results. Do more of what works, stop doing what doesn't.

4. **Trend awareness**: Monitor social/political/cultural trends and incorporate relevant ones into content. Timely content outperforms evergreen content.

**Implementation**: Store post performance data in `agent_content_insights` table (already exists). Build a feedback loop: generate → post → measure → learn → generate better. Feed performance data back into the 4-phase content agent's Strategy Phase.

---

### Task #62 — Free and Paid Tiers
**Priority**: High
**Dependencies**: None

Design and implement tiered pricing for users (amplifiers) and optionally companies.

**Free Tier** (default):
- Limited number of active campaigns (e.g., 1-2)
- Basic content generation (text-only, standard AI models)
- Standard posting frequency
- Basic metrics dashboard
- Community support

**Paid Tier** (subscription or per-feature):
- Unlimited active campaigns (or higher cap)
- Advanced content generation (image+text, video, AI image gen)
- Higher posting frequency
- Priority campaign matching (higher visibility to companies)
- Advanced analytics and insights
- Faster metric scraping intervals
- Priority support

**Implementation:**
- Tier stored on user model (server-side) — integrates with existing reputation tier system (seedling/grower/amplifier are reputation-based; free/paid is subscription-based — these are orthogonal)
- Feature gates checked at: campaign acceptance, content generation, posting frequency
- Stripe subscription for paid tier (monthly billing)
- Free tier must be genuinely useful — not crippled. Users should earn real money on free tier.
- Paid tier unlocks scale and premium features, not basic functionality
- Companies may also have tiers (more campaigns, higher budgets, priority matching)

---

### Task #64 — All Content Formats Across 6 Platforms
**Priority**: High
**Dependencies**: #63

**What it replaces**: Current posting only supports basic text + single image per platform. Each platform has unique content formats that drive higher engagement.

**All 6 platforms must be supported**: X, LinkedIn, Facebook, Reddit, TikTok (re-enable), Instagram (re-enable).

**Formats to add per platform:**

**X (Twitter):**
- Text-only tweet (existing)
- Image + text tweet (existing)
- Multi-image tweet (up to 4 images)
- Thread posts (multi-tweet, linked together)
- Polls
- Quote tweets

**LinkedIn:**
- Text-only post (existing)
- Image + text post (existing)
- Document/carousel uploads (PDF slides — high engagement format)
- Polls
- Articles (long-form)
- Video posts

**Facebook:**
- Text-only post (existing)
- Image + text post (existing)
- Photo albums (multiple images)
- Polls
- Video posts
- Stories

**Reddit:**
- Text posts with title + body (existing)
- Link posts (title + URL)
- Image posts (existing)
- Polls
- Cross-posting to multiple subreddits

**Instagram (re-enable):**
- Single image + caption (existing, disabled)
- Carousels (multiple images/slides)
- Reels (short video)
- Stories

**TikTok (re-enable):**
- Video posts (existing, disabled)
- Slideshows (image sequence as video)
- Duets
- Stitches

**To implement:**
1. Update content generator (4-phase agent) to produce format-specific content (e.g., thread = array of tweets, carousel = array of slides)
2. Add new JSON scripts in `config/scripts/` for each format (e.g., `x_thread.json`, `linkedin_poll.json`)
3. Update `ScriptExecutor` if new action types are needed
4. Add format selection to campaign wizard (company can specify preferred formats)
5. AI should pick the best format per platform based on the content and campaign goal (from strategy phase)
6. Re-enable Instagram and TikTok in `config/platforms.json`

---

### Task #65 — Platform-Specific Content Preview in Review UI
**Priority**: Low
**Dependencies**: #63

Show draft content as a visual mockup of how it would appear on each platform (X tweet card, LinkedIn post card, Reddit post layout, etc.) instead of plain text. This is a UI improvement — drafts already work as plain text.

Implementation:
- CSS mockup templates per platform (tweet card with avatar, engagement buttons, etc.)
- Show character count with platform limit
- Preview generated image alongside text
- For threads: show each tweet in sequence
- For carousels: show slide navigation

---

### Task #68 — Repost Campaign Type
**Priority**: High
**Dependencies**: None

Add a new campaign type where companies provide pre-written posts per platform instead of AI-generating content. Simpler than AI campaigns (no content generation, no research, no strategy) and gives companies more control over exact messaging.

**Company side:**
- New campaign type selector: "AI Generated" (existing) vs "Repost" (new)
- For repost campaigns, company provides per-platform post content (text, images, links) directly in the campaign creation form
- Each campaign can have multiple posts (a content calendar the company defines)
- Company can specify posting order, frequency, and date range

**User side:**
- Repost campaigns show the actual posts in the invitation (so users know what they're agreeing to post)
- On accept, posts are scheduled automatically — no content generation step, no review step needed
- User can optionally preview before each post goes live (semi_auto mode) or let them auto-post (full_auto)
- Posts execute via existing Playwright posting engine (JSON script engine)
- Metrics scraped and billed the same as AI-generated campaigns

**Server side:**
- New `campaign_type` field on Campaign model: `"ai_generated"` (default) or `"repost"`
- New `campaign_posts` table: campaign_id, platform, content, image_url, post_order, scheduled_offset
- Matching works the same — repost campaigns still matched to users by niche/platform/followers
- Billing works the same — pay per impression/engagement

---

### Political Campaigns (No task ID — from docs/political-campaigns.md)
**Priority**: High (massive revenue opportunity)
**Dependencies**: US legal entity ($5-15K for FEC compliance setup)

Full specification in `docs/political-campaigns.md`. Key product changes:

**1. Geographic Micro-Targeting (highest priority):**
- Add `zip_code` and `state` fields to User model
- Zip-to-congressional-district mapping (free Census Bureau data)
- Campaign targeting gains: `target_states`, `target_districts`, `target_zip_codes`
- Matching engine filters by geography before niche/followers

**2. Political Content Generation Mode:**
- New content types: candidate promotion, issue framing, GOTV (voter mobilization), contrast, rapid response
- Each type needs platform-specific variants
- Critical: political content gen needs continuous daily news monitoring (not one-time URL scrape)
- Research pipeline must scrape news sources, monitor X/Reddit for political discourse, track opponent messaging

**3. FEC Compliance Disclaimers:**
- Campaign model gains `disclaimer_text` field (e.g., "Paid for by Smith for Congress")
- Content generator appends disclaimer to every post
- Per-platform formatting
- Admin review queue flags political campaigns for compliance check

**4. Rapid Campaign Deployment ("War Room" mode):**
- Pre-enrolled user pools (opt into rapid-response list)
- Template-based one-click launch
- Auto-approve + auto-schedule
- Target: campaign created to posts live in under 2 hours

**5. Political Reporting Dashboard:**
- Reach by district/state (map visualization)
- Estimated voter contacts
- Message penetration
- Platform breakdown per dollar
- Timeline view (message volume over time)

**6. Political Campaign Wizard:**
- Input: candidate name, office, district, party, key issues, opponent name, campaign website
- Scrapes: candidate website, opponent website, local news, voting record
- Generates: talking points per issue, platform-specific guidance, suggested posting cadence

**Architecture Decision (DECIDED):** One app, not a separate product. Political campaigns are a campaign type (`campaign_type: "political"`) within existing Amplifier. Users opt in via `political_campaigns_enabled` setting (default OFF). Full rationale in `docs/political-campaigns.md`.

**Pricing:** 25-30% platform cut (vs 20% for brands). $500 minimum campaign budget. 35% cut for rapid-response (<24h). Retainer option: $2K-$10K/month.

**Revenue projection (conservative, 2026 cycle):** ~$550K platform revenue from ~58 campaigns. 2028 presidential cycle would be 5-10x larger.

---

## Tier 5: UX Polish, Admin Verification & Compliance

Lower priority — admin dashboard and system tray work but haven't been formally verified. UX improvements that enhance but don't block the product.

---

### Task #39 — Explain: System Tray + Notifications
**Priority**: Low | **Depends on**: #17 (done)

Walk through how the system tray and desktop notifications currently work — tray icon, right-click menu, dashboard launch, notification triggers, background agent integration.

### Task #40 — Verify: System Tray + Notifications
**Priority**: Low | **Depends on**: #39

### Task #41 — Explain: Company Dashboard Stats
**Priority**: Low | **Depends on**: #15 (done)

Walk through how company dashboard statistics currently work — overview metrics, campaign counts, total spend, active users, recent activity.

### Task #42 — Verify: Company Dashboard Stats
**Priority**: Low | **Depends on**: #41

### Task #43 — Explain: Admin Overview
**Priority**: Low | **Depends on**: None

### Task #44 — Verify: Admin Overview
**Priority**: Low | **Depends on**: #43

### Task #45 — Explain: Admin Users
**Priority**: Low | **Depends on**: None

### Task #46 — Verify: Admin Users
**Priority**: Low | **Depends on**: #45

### Task #47 — Explain: Admin Campaigns
**Priority**: Low | **Depends on**: None

### Task #48 — Verify: Admin Campaigns
**Priority**: Low | **Depends on**: #47

### Task #49 — Explain: Admin Payouts
**Priority**: Low | **Depends on**: None

### Task #50 — Verify: Admin Payouts
**Priority**: Low | **Depends on**: #49

### Task #77 — User App: Data Integrity Improvements
**Priority**: Medium | **Dependencies**: None

Medium priority items:
1. Periodic local DB backup to a second file
2. Sync approved drafts to server so laptop crash doesn't lose them
3. Wrap SQLite operations in proper transactions
4. Check `campaign_version` on detail view to detect stale cached data

### Task #78 — User App: Settings, Metrics & Performance Improvements
**Priority**: Medium | **Dependencies**: None

Settings: auto-populate follower counts from scraped data, per-platform auto/manual mode, sync settings with server on startup. Metrics: manual metric entry fallback, resilient CSS selectors, 3-day profile refresh. Performance: campaign pagination, API response caching (5min TTL), lazy loading.

### Task #79 — User App: UX Polish and Integration Fixes
**Priority**: Medium | **Dependencies**: None

UX: rename confusing statuses (`pending_invitation` → "Invited", `content_generated` → "Draft Ready"), copy-to-clipboard for post URLs, mobile responsive, client-side form validation, CSV export for earnings. Integration: server-side post URL dedup, client-side invitation expiry warnings, campaign conflict detection.

### Task #80 — User App: Compliance, Accessibility & Testing
**Priority**: Low | **Dependencies**: None

Compliance: ToS acceptance on registration, privacy policy, GDPR data export/deletion, account deletion. Accessibility: ARIA labels, WCAG color contrast, keyboard navigation, form label associations. Testing: E2E tests (full flow), unit tests (scraping, generation, scheduling), mock server fixtures, load testing.

---

## Launch Tasks (No Task IDs — New Work)

These are not in the task-master list but are required for launch.

---

### Stripe Integration (Both Directions)
**Priority**: High

**Company side (partially done):**
- Live Stripe Checkout for balance top-ups (needs: live API keys, webhook endpoint for payment confirmation)
- Webhook handler: `POST /api/webhooks/stripe` to verify `checkout.session.completed` events
- Switch from test mode to live mode

**User side (stub):**
- Stripe Connect Express onboarding flow: user creates Stripe account, links bank, gets verified
- `create_user_stripe_account()` exists but needs: onboarding URL in user settings, return URL handling, account status tracking
- `process_pending_payouts()` exists but needs: real Stripe transfer calls with user's `stripe_account_id`, balance deduction on success, funds return on failure
- Add `stripe_account_id` field to User model (server)

---

### Package as Installer
**Priority**: High

Current state: user must have Python, pip, Playwright, and run scripts manually. Need a double-click installer.

Options:
- **PyInstaller**: Single .exe for Windows. Bundle Python + all deps. Already have `amplifier.spec` (may need updating).
- **Tauri** (future): Lightweight desktop wrapper with web UI. Better long-term but more work.

For launch: PyInstaller .exe is sufficient. User downloads, installs, runs. System tray icon appears. Dashboard opens in browser.

---

### Mac Support
**Priority**: High

Most code is already cross-platform. Windows-specific fixes needed:
1. Replace Windows Task Scheduler references with cross-platform scheduling (background agent already handles this)
2. Fix Windows font references in PIL (`arial.ttf` → bundled font or system-agnostic)
3. Test pystray on macOS (uses AppKit — should work)
4. Create Mac distribution (DMG or zip with launch script)
5. Test all Playwright automation on Mac (should work — Chromium is cross-platform)
6. Fix any hardcoded Windows paths (should be none — code uses `Path` objects)

---

### Landing Page
**Priority**: High (after product is packaged)

Static website on Vercel:
- Hero section explaining value prop (for companies AND users)
- "For Companies" → link to company dashboard signup
- "For Users" → download buttons (Windows .exe, Mac .dmg)
- How it works (3-step for each side)
- Pricing (20% platform cut, free to start)
- FAQ
- Link to API docs

---

## Summary

| Tier | Tasks | Count | Estimated Effort |
|---|---|---|---|
| **1: Core Loop** | #28-38 (verification) | 11 tasks | 5-7 days |
| **2: Product Gaps** | #66, #67, #70-76, FTC disclosure | 10 tasks | 5-7 days |
| **3: Integrity/Testing** | #53, #54, #60 | 3 tasks | 3-5 days |
| **4: Features** | #51/#59, #52/#63, #58, #61, #62, #64, #65, #68, Political | 12 tasks | 25-35 days |
| **5: Polish/Admin** | #39-50, #77-80 | 18 tasks | 5-7 days |
| **Launch** | Stripe, packaging, Mac, landing page | 4 tasks | 5-7 days |
| **Total** | | **58 tasks** | **48-68 days** |
