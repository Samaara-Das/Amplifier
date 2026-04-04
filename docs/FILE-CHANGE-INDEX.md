# Amplifier — File Change Index

**Purpose**: Which files each task touches. Use this to plan your work, avoid conflicts (two tasks modifying the same function), and know exactly what to open.

---

## Index By File (What Tasks Touch Each File)

### Server Models

| File | Tasks That Modify It |
|---|---|
| `server/app/models/campaign.py` | #52/#63 (campaign_goal, tone), #64 (preferred_formats), #68 (campaign_type), FTC (disclaimer_text), Political (campaign_type, disclaimer_text) |
| `server/app/models/user.py` | #62 (subscription_tier), Political (zip_code, state, political_campaigns_enabled) |
| `server/app/models/payout.py` | No changes needed (session 26 complete) |
| `server/app/models/__init__.py` | #68 (register CampaignPost model) |
| `server/app/models/campaign_post.py` | #68 (NEW FILE — repost campaign posts) |

### Server Services

| File | Tasks That Modify It |
|---|---|
| `server/app/services/matching.py` | #51/#59 (uses richer profile data), #62 (subscription_tier priority), Political (geo filtering), #58 (quality gate check before matching) |
| `server/app/services/billing.py` | #62 (subscription tier affects features, not billing directly) |
| `server/app/services/campaign_wizard.py` | #52/#63 (persist campaign_goal), #58 (quality gate), Political (political wizard mode) |
| `server/app/services/payments.py` | #62 (Stripe subscription for paid tier), Launch/Stripe (live keys + Connect onboarding) |

### Server Routers

| File | Tasks That Modify It |
|---|---|
| `server/app/routers/campaigns.py` | #52/#63 (accept campaign_goal, tone), #64 (preferred_formats), #68 (campaign_type, campaign_posts CRUD), FTC (disclaimer_text), Political (political fields) |
| `server/app/routers/invitations.py` | #76 (decline reason), #68 (show repost content in invitation) |
| `server/app/routers/auth.py` | #71 (password reset endpoints) |
| `server/app/routers/admin/financial.py` | No changes needed (session 26 complete) |
| `server/app/routers/admin/review.py` | #58 (quality gate results in review queue) |
| `server/app/routers/company/campaigns.py` | #68 (repost campaign creation form), #58 (quality gate feedback), Political (political fields in form) |

### Server Templates

| File | Tasks That Modify It |
|---|---|
| `server/app/templates/company/campaign_create.html` | #52/#63 (goal, tone dropdowns), #64 (format selector), #68 (repost content input), FTC (disclaimer field), Political (political fields) |
| `server/app/templates/company/campaign_wizard.html` | #52/#63 (persist goal to campaign) |
| `server/app/templates/company/campaign_detail.html` | #37/#38 (verification), Political (political reporting) |
| `server/app/templates/admin/review_queue.html` | #58 (quality score display) |

### User App

| File | Tasks That Modify It |
|---|---|
| `scripts/user_app.py` | #70 (draft count fix), #71 (password reset UI), #72 (CSRF), #74 (rate limiting, campaign search), #75 (draft UX), #76 (invitation UX), #65 (preview UI), #79 (UX polish) |
| `scripts/background_agent.py` | #52/#63 (4-phase content agent), #61 (self-learning feedback), #68 (repost scheduling without AI gen) |
| `scripts/utils/local_db.py` | #64 (format_type on agent_draft), #61 (variant_id), #68 (campaign_posts table), Political (campaign fields), #70 (draft count query fix) |
| `scripts/utils/content_generator.py` | #52/#63 (replace with 4-phase agent), #61 (performance feedback input), FTC (append disclaimer) |
| `scripts/utils/server_client.py` | #68 (fetch campaign_posts for repost), Political (send zip/state on profile sync), #71 (password reset API call) |
| `scripts/utils/profile_scraper.py` | #51/#59 (replace CSS selectors with AI Vision) |
| `scripts/utils/metric_scraper.py` | #29/#30 (verification), #60 (accuracy + audit trail) |
| `scripts/utils/post_scheduler.py` | #28 (URL capture fixes), #52/#63 (strategy-driven scheduling) |
| `scripts/post.py` | #28 (URL capture fixes), #64 (new JSON scripts for threads/polls/carousels), #66 (X lockout detection) |
| `scripts/utils/session_health.py` | #67 (selector updates, retry logic) |

### Engine & AI

| File | Tasks That Modify It |
|---|---|
| `scripts/engine/script_executor.py` | #64 (new action types if needed for threads/polls) |
| `scripts/ai/manager.py` | No changes needed |
| `scripts/ai/image_manager.py` | No changes needed |
| `config/scripts/x_post.json` | #64 (add x_thread.json, x_poll.json), #28 (selector updates if needed) |
| `config/scripts/linkedin_post.json` | #64 (add linkedin_poll.json, linkedin_carousel.json), #28 (selector updates) |
| `config/scripts/facebook_post.json` | #64 (add facebook_poll.json), #28 (selector updates) |
| `config/scripts/reddit_post.json` | #64 (add reddit_poll.json), #28 (selector updates) |
| NEW: `config/scripts/instagram_post.json` | #64 (re-enable Instagram) |
| NEW: `config/scripts/tiktok_post.json` | #64 (re-enable TikTok) |

### Templates (User App)

| File | Tasks That Modify It |
|---|---|
| `scripts/templates/user/campaigns.html` | #74 (search bar), #76 (invitation countdown, expired badge) |
| `scripts/templates/user/campaign_detail.html` | #65 (platform preview), #75 (guidance alongside draft, char count) |
| `scripts/templates/user/dashboard.html` | #70 (draft count fix), #79 (status label renames) |
| `scripts/templates/user/earnings.html` | #79 (CSV export button) |
| `scripts/templates/user/settings.html` | Political (zip/state fields, political toggle), #62 (subscription toggle) |
| `scripts/templates/user/login.html` | #71 (forgot password link) |

### Config

| File | Tasks That Modify It |
|---|---|
| `config/platforms.json` | #64 (re-enable instagram, tiktok) |
| `requirements.txt` | #72 (flask-wtf), #51 (browser-use or equivalent), #80 (testing deps) |
| `SLC.md` | #53 (full rewrite after all features) |
| `server/.env.example` | Launch/Stripe (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET) |

### New Files Created By Tasks

| Task | New Files |
|---|---|
| #51/#59 | `scripts/utils/ai_scraper.py` (or modify profile_scraper.py) |
| #52/#63 | `scripts/ai/content_agent.py` (4-phase agent), `scripts/ai/research_phase.py`, `scripts/ai/strategy_phase.py` |
| #58 | `server/app/services/quality_gate.py` |
| #61 | `scripts/ai/content_learner.py` (performance feedback processor) |
| #62 | `server/app/routers/subscriptions.py` (Stripe subscription management) |
| #64 | Multiple new JSON scripts: `x_thread.json`, `linkedin_poll.json`, `instagram_post.json`, `instagram_carousel.json`, `tiktok_post.json`, etc. |
| #65 | `scripts/templates/user/components/platform_preview.html` (Jinja2 partial) |
| #68 | `server/app/models/campaign_post.py`, `server/app/routers/company/repost.py` |
| Political | `server/app/services/political_wizard.py`, `server/app/routers/company/political.py` |
| Launch | `landing/` (landing page directory) |

---

## Conflict Map (Tasks That Touch The Same File)

These need careful ordering to avoid merge conflicts:

| File | Conflicting Tasks | Resolution |
|---|---|---|
| `server/app/models/campaign.py` | #52/#63, #64, #68, FTC, Political | Do schema migration ONCE in Phase C (all fields at once) |
| `server/app/models/user.py` | #62, Political | Do schema migration ONCE in Phase C |
| `scripts/user_app.py` | #70, #71, #72, #74, #75, #76, #65, #79 | These are all independent routes/templates — low conflict risk. Do #72 (CSRF) first since it touches every POST handler. |
| `scripts/utils/content_generator.py` | #52/#63, #61, FTC | #52/#63 replaces this file. Do FTC first (small change), then #52/#63 (major rewrite), then #61 (adds to #52/#63). |
| `scripts/post.py` | #28, #64, #66 | #28 fixes selectors (small). #64 adds new format scripts (additive). #66 adds lockout detection (small). Low conflict. |
| `server/app/services/matching.py` | #51/#59, #62, Political | #51/#59 changes what profile data is available (richer). Political adds geo filter. #62 adds subscription priority. All are additive to different parts of the function. |
| `server/app/routers/campaigns.py` | #52/#63, #64, #68, FTC, Political | All add new fields to CampaignCreate schema. Do schema migration once, then each task just reads the new fields. |
