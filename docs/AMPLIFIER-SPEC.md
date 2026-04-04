# AmpliFire — Complete System Specification

**Version**: 1.0
**Date**: April 3, 2026
**Status**: Three implementations exist (v1 deployed, v2 shelved, v3 Phase 1 complete)

---

## 1. What AmpliFire Is

AmpliFire is a **decentralized advertising marketplace** where companies pay for authentic organic social media reach and everyday people earn money by posting AI-generated branded content on their real accounts.

**The core thesis**: Billions of social media users with 100-2,000 followers each represent a massive, untapped distribution channel. Coordinating thousands of normal people to post authentic, platform-native content about products creates massive collective reach at a fraction of influencer rates. AmpliFire automates the entire pipeline — from campaign brief to published post to billing — with AI and on-device automation.

### 1.1 Three Actors

| Actor | What They Do | What They Get |
|-------|-------------|---------------|
| **Company** | Creates campaign with product brief, budget, payout rates, targeting criteria | Authentic organic reach across thousands of real accounts. Pays only for measured engagement. |
| **Creator (Amplifier)** | Accepts campaigns matched to their niche. Reviews AI-generated content. Posts to their real social accounts. | Earns money from post engagement (impressions, likes, shares, clicks). Cash out at $10+. |
| **Platform (AmpliFire)** | Matches companies to creators, generates content, automates posting, scrapes metrics, calculates billing | Takes 20% of all earnings as platform cut. |

### 1.2 End-to-End Flow

```
COMPANY                           AMPLIFIRE                          CREATOR
                                                                     
1. Create campaign          ───►  AI generates brief from URLs  ───► Matched by niche + profile
   (product, budget, rates)       AI scores creator fit                
                                                                     
2. Budget locked            ◄───  Invitations sent (3-day TTL)  ───► Accepts (max 3 active)
                                                                     
                                  AI generates content           ───► Reviews / edits / approves
                                  (per-platform, UGC-style)          (or auto-posts if full-auto)
                                                                     
3. Tracks performance       ◄───  Posts to social media          ◄── On-device automation
                                  Scrapes engagement at               (human emulation)
                                  T+1h, T+6h, T+24h, T+72h          
                                                                     
4. Pays per engagement      ───►  Calculates billing             ───► Earns 80% of engagement value
   (from campaign budget)         Takes 20% cut                       Cashes out at $10+
```

### 1.3 The Key Insight

Most people on social media aren't influencers — they're normal people with 200-2,000 followers. But collectively, thousands of normal people generate massive reach at a fraction of influencer rates. AmpliFire turns this long tail into a distribution channel.

- 1,000 users x 500 followers = 500K potential impressions
- Each user's post is authentic (real person, real account, real followers)
- Performance-based billing (companies pay for engagement, not posts)
- All automation happens on the user's device (no credential sharing, no API abuse)

### 1.4 How It's Different

| Traditional Influencer Marketing | AmpliFire |
|---|---|
| Pay upfront per post ($500-$50K) | Pay per engagement (performance-based) |
| Negotiate with each influencer | AI matches + generates + posts automatically |
| Need 10K+ followers to qualify | Anyone with a social media account can earn |
| Content created by influencer (variable quality) | AI-generated, platform-native, brand-guided content |
| Manual tracking via screenshots | Automated metric scraping + billing |
| Expensive ($500-$50K per influencer) | Micro-earnings across thousands of users ($0.50-$50/user/campaign) |

---

## 2. System Architecture

AmpliFire has three major components: a cloud server (marketplace), a creator app (on-device), and web dashboards (company + admin).

### 2.1 High-Level Architecture

```
Internet
    │
    ├── Vercel (serverless) ──── FastAPI / NestJS server
    │       │
    │       └── Supabase PostgreSQL (aws-1-us-east-1)
    │               Connection: transaction pooler (port 6543)
    │               Config: NullPool + prepared_statement_cache_size=0
    │
    ├── Company browser  ──►  Company Dashboard (server-rendered Jinja2)
    │                          Campaign creation, AI wizard, analytics, billing
    │
    ├── Admin browser    ──►  Admin Dashboard (server-rendered Jinja2)
    │                          User/company/campaign management, fraud, payouts
    │
    └── Creator's Device
            │
            ├── App UI (Flask web on desktop / Jetpack Compose on Android)
            ├── Background Agent (async task orchestration)
            ├── On-Device Automation
            │     Desktop: Playwright (persistent browser profiles)
            │     Android: Accessibility Service (JSON-scripted, OTA-updatable)
            ├── AI Content Generation (on-device, free tier APIs or WebView scraping)
            ├── Local Database (SQLite / Room)
            └── Metric Scraper (revisits posts to collect engagement)
```

### 2.2 Design Principles

1. **User-side compute.** All AI content generation, browser/app automation, and credential handling happen on the creator's device. The server never sees passwords or runs browsers. This eliminates platform ban risk at scale and keeps credentials private.

2. **AI-native everything.** Campaign briefs are AI-generated from company URLs. Content is AI-generated per platform. Matching uses AI scoring of profiles against briefs. The human is in the loop for quality control, not for grunt work.

3. **Performance-based billing.** Companies pay for real engagement (impressions, likes, shares, clicks), not for posts. This aligns incentives — creators want high-engagement content, companies want ROI, AmpliFire wants both.

4. **Platform-native content.** A tweet is not a LinkedIn post is not a Reddit thread. Every piece of content is generated specifically for the platform it will appear on, with the right tone, length, format, and culture.

5. **Human emulation.** Automation uses persistent profiles/sessions, character-by-character typing with random delays, feed browsing before/after posting, and randomized behavior to avoid platform detection.

6. **Zero AI cost for creators.** Content generation uses free-tier AI APIs (Gemini, Mistral, Groq) or free AI via hidden WebView scraping (Gemini web interface). No API keys required from creators.

---

## 3. The Server (Marketplace)

The server is the central marketplace that connects companies with creators, handles authentication, campaign management, matching, billing, trust scoring, and admin operations.

### 3.1 Tech Stack

| Component | v1 (Current, Deployed) | v2 (Shelved) |
|-----------|----------------------|--------------|
| Framework | FastAPI (Python) | NestJS 11 (TypeScript) |
| ORM | SQLAlchemy 2.0 (async) | Prisma 7.3 |
| Database | Supabase PostgreSQL (prod), SQLite (dev) | PostgreSQL |
| Cache | None | Redis (ioredis) |
| Auth | JWT (python-jose, bcrypt) | JWT (passport-jwt, bcrypt), Google OAuth |
| Payments | Stripe Connect (stub) | PayPal Payouts API (working), Stripe |
| AI | Google Generative AI (Gemini) | N/A (AI is on-device) |
| Deployment | Vercel serverless | Docker (not deployed) |

### 3.2 Data Models

#### Server Database (11 models in v1, 53 models in v2)

**Core Models (v1 — deployed):**

| Model | Purpose | Key Fields |
|-------|---------|------------|
| **Company** | Advertiser accounts | id, name, email, password_hash, balance, status, created_at |
| **Campaign** | Advertising campaigns | id, company_id, title, brief, content_guidance, assets (JSON), budget_total, budget_remaining, payout_rules (JSON), targeting (JSON), penalty_rules (JSON), status, screening_status, max_users, invitation/accepted/rejected/expired_count, campaign_version, ai_generated_brief, budget_exhaustion_action, company_urls (JSON), start_date, end_date |
| **User** | Creator accounts | id, email, password_hash, platforms (JSON), follower_counts (JSON), niche_tags (JSON), audience_region, trust_score, mode, earnings_balance, total_earned, status, scraped_profiles (JSON), ai_detected_niches (JSON), last_scraped_at |
| **CampaignAssignment** | Creator-campaign relationship | id, campaign_id, user_id, status, content_mode, payout_multiplier, invited_at, responded_at, expires_at |
| **Post** | Published social posts | id, assignment_id, platform, post_url, content_hash, posted_at, status |
| **Metric** | Engagement measurements | id, post_id, impressions, likes, reposts, comments, clicks, scraped_at, is_final |
| **Payout** | Earnings records | id, user_id, campaign_id, amount, period_start, period_end, status, breakdown (JSON) |
| **Penalty** | Trust violations | id, user_id, post_id, reason, amount, description, appealed, appeal_result |
| **CampaignInvitationLog** | Invitation audit trail | id, campaign_id, user_id, event, event_metadata (JSON) |
| **AuditLog** | Admin action tracking | id, action, target_type, target_id, details (JSON), admin_ip |
| **ContentScreeningLog** | AI content moderation | id, campaign_id, flagged, flagged_keywords (JSON), screening_categories (JSON), reviewed_by_admin, review_result, review_notes |

**Additional Models in v2 (not deployed):**
- User subscriptions (FREE/PREMIUM tiers)
- Social account OAuth tokens (encrypted)
- Devices and push notification tokens
- Content media assets (images, audio, video, thumbnails)
- Activity logs
- Fraud alerts with severity levels
- Tracking links with click/conversion events
- Brand portal users with role-based access (OWNER/ADMIN/MEMBER/VIEWER)
- Content seeds (brand-provided templates, scripts, talking points)
- Brand deposits and billing
- Admin users with role hierarchy (SUPER_ADMIN > ADMIN > FINANCE > MODERATION > SUPPORT)

### 3.3 Campaign Lifecycle

```
draft → active → paused → active (resume)
                → completed (budget exhausted or manually)
                → cancelled (refunds remaining budget)
```

**Campaign Status Rules:**
- `draft`: Created but not launched. No budget deduction. Can be edited or deleted freely.
- `active`: Budget deducted from company balance. Matching enabled. Invitations sent.
- `paused`: Matching disabled. Existing assignments continue. Can resume.
- `completed`: Final state. Budget reconciled. All assignments closed.
- `cancelled`: Remaining budget refunded to company. All pending invitations expired.

**Content Screening:**
- AI screens campaign brief for flagged keywords (violence, hate, explicit, misinformation, financial claims, health claims)
- Flagged campaigns enter review queue (`screening_status: flagged`)
- Admin approves or rejects with notes
- Rejected campaigns refund budget

### 3.4 Campaign Matching Algorithm

**Hard Filters (all must pass):**
1. Campaign is active with remaining budget (>$0)
2. User not already invited to this campaign
3. Campaign `accepted_count < max_users`
4. User has at least 1 of the campaign's required platforms connected
5. User meets minimum follower count per platform (if specified)
6. User meets minimum engagement rate (if specified)
7. User's audience region matches campaign target regions
8. User is below their tier's active campaign limit (Seedling: 3, Grower: 10, Amplifier: unlimited)
9. User status is not suspended/banned

**AI Scoring (Gemini):**
- Reads user's full scraped profile (bio, recent posts with engagement, followers/following, platform-specific data)
- Reads campaign brief, content guidance, targeting criteria
- Scores 0-100 on: topic relevance, audience fit, authenticity
- Key instruction: "Most users are normal people, not influencers. Low followers or infrequent posting should NOT be penalized."
- Results cached 24 hours per (campaign, user) pair
- On AI failure: falls back to niche-overlap scoring (each overlapping niche = +30 points, base 10)

**Invitation Flow:**
1. User polls `GET /api/campaigns/mine` → triggers matching if < 3 active campaigns
2. New matches create CampaignAssignment with `status=pending_invitation`, `expires_at=now+3days`
3. User sees invitations in dashboard with campaign details, payout rates, required platforms
4. User accepts (max 3 active) or rejects
5. Stale invitations auto-expire on next fetch

### 3.5 AI Campaign Wizard

Companies can create campaigns manually or use the AI wizard:

1. Company provides: product description, goal, URLs, target niches, regions, platforms, budget range
2. Server deep-crawls company URLs (BFS, up to 10 pages, 2 hops deep)
3. Extracts: page content, metadata (OG tags), images, navigation links
4. Gemini generates comprehensive brief (500-1000 words), content guidance (200-400 words), suggested payout rates, targeting
5. Returns draft JSON for company review (does NOT create campaign)
6. Company edits, then calls POST /campaigns to create

**Payout Rate Suggestions (niche-based):**

| Niche Type | Impressions (per 1K) | Per Like | Per Repost | Per Click |
|---|---|---|---|---|
| High-value (finance, crypto, AI, tech) | $1.00 | $0.02 | $0.10 | $0.15 |
| Engagement (beauty, fashion, fitness) | $0.30 | $0.015 | $0.08 | $0.10 |
| Default (all other) | $0.50 | $0.01 | $0.05 | $0.10 |

### 3.6 Billing & Earnings

**Billing Formula:**
```
raw_earning = (impressions / 1000 x rate_per_1k_impressions)
            + (likes x rate_per_like)
            + (reposts x rate_per_repost)
            + (clicks x rate_per_click)

user_earning = raw_earning x 0.80    (creator gets 80%)
platform_cut = raw_earning x 0.20    (AmpliFire gets 20%)
company_cost = raw_earning           (full amount from campaign budget)
```

**Billing Mechanics:**
- **Incremental:** Runs on every metric submission (not batched). Prevents under-billing.
- **Deduplication:** Tracks billed metric IDs in Payout.breakdown. Same metric never billed twice.
- **Budget capping:** Earnings capped to remaining campaign budget. No over-spend.
- **Budget exhaustion:** When remaining < $1, campaign auto-pauses or auto-completes (configurable).
- **Budget alert:** When remaining < 20% of total, alert flag set.
- **Budget top-up:** Companies can add funds anytime. Resets alert. Resumes paused campaigns.
- **Minimum payout:** $10 balance required before cash-out.

**Payment Processing:**
- v1: Stripe Connect (stub — test mode only)
- v2: PayPal Payouts API (working — auto-processing cron every 5 minutes)
- Target: Stripe + PayPal + regional options (UPI for India)

### 3.7 Trust & Fraud Detection

**Trust Score:**
- Range: 0-100, starts at 50
- Adjusted by events:

| Event | Adjustment |
|---|---|
| Post verified live after 24h | +1 |
| Above-average engagement | +2 |
| Campaign completed | +3 |
| User customized content | +1 |
| Post deleted within 24h | -10 |
| Content flagged | -15 |
| Metrics anomaly detected | -20 |
| Confirmed fake metrics | -50 |

**Fraud Detection:**
1. **Deletion fraud:** Checks 24h-old "live" posts for deletion signals
2. **Metrics anomalies:** Flags users whose average engagement > 3x the platform average (with >=3 data points)
3. **Spot-checking (v3 planned):** Random sampling — 30% of Tier 1, 10% of Tier 2, 5% of Tier 3

**Penalties:**
- Created for negative trust events
- Amount = |trust_adjustment| x $0.50
- Reasons: content_removed, off_brief, fake_metrics, platform_violation
- Appeal workflow: user can appeal, admin approves/denies

**Reputation Tiers (now in v1):**

| Tier | Name | Unlock | Capabilities | CPM Rate |
|---|---|---|---|---|
| 1 | Seedling | Default | Full approval required. Max 3 campaigns. 30% spot-checked. | 1x |
| 2 | Grower | 20 successful posts | Auto-post toggle. Max 10 campaigns. 10% spot-checked. | 1x |
| 3 | Amplifier | 100 posts + trust ≥ 80 | Full auto. Unlimited campaigns. 5% spot-checked. | 2x premium |

Auto-promotion runs in `billing.py` (`_check_tier_promotion()`). Campaign limits enforced in `matching.py`. User model stores `tier` and `successful_post_count`.

### 3.8 API Surface

**v1 (deployed) — ~90 routes:**

| Group | Routes | Auth | Description |
|---|---|---|---|
| Auth | 4 | None | User + company register/login (JWT) |
| Company Campaigns | 13 | Company JWT | CRUD, AI wizard, reach estimates, cloning, export |
| User Campaigns | 4 | User JWT | Poll matched campaigns, invitations |
| Active Assignments | 2 | User JWT | Active campaigns, update assignment status |
| User Profile | 4 | User JWT | Profile CRUD, earnings, payout |
| Posts & Metrics | 2 | User JWT | Batch register posts, batch submit metrics |
| System | 2 | None | Health check, version |
| Admin Dashboard | 36 | Admin cookie | 11 modular routers: login, overview, users, companies, campaigns, financial (5 routes: list + run-billing + run-payout + run-earning-promotion + run-payout-processing), fraud, analytics, review queue, audit log, settings |
| Company Dashboard | ~22 | Company JWT cookie | 7 modular routers: dashboard, campaigns, billing, influencers, stats, settings |

**v2 (not deployed) — 24 NestJS modules:**
- Auth, Users, Tasks, Content, ContentPosts, Earnings, Payouts, SocialAccounts, Notifications, Platforms, UserPlatforms, Metrics, Tracking
- BrandAuth, BrandPortal, BrandCampaigns, BrandTasks, BrandSeeds, BrandBilling, BrandAnalytics
- Admin, Prisma, Redis

### 3.9 Web Dashboards

**Company Dashboard (v1 — 10 pages, deployed):**
1. Login/Register
2. Dashboard (KPIs, budget usage, ROI, alerts)
3. Campaigns List (search, filter, sort)
4. Create Campaign (multi-step form + AI wizard)
5. Campaign Detail (stats, per-platform breakdown, creator table, invitation funnel, budget management)
6. AI Campaign Wizard (step-by-step: URL → AI generates brief → review → create)
7. Billing (balance, Stripe checkout, top-up)
8. Influencers (cross-campaign creator performance)
9. Stats (analytics, platform breakdown, trends)
10. Settings (company profile)

**Admin Dashboard (v1 — 14 pages, deployed):**
1. Login
2. Overview (system KPIs, recent activity, alerts)
3. Users (paginated, search/filter/sort, suspend/unsuspend/ban, adjust trust)
4. User Detail (individual user with assignments, posts, payouts, penalties)
5. Companies (paginated, search/filter/sort, add/deduct funds, suspend/unsuspend)
6. Company Detail (campaigns, financial summary)
7. Campaigns (paginated, search/filter/sort, pause/resume/cancel)
8. Campaign Detail (assignments, posts with metrics)
9. Financial (payout dashboard, run billing cycle, run payout cycle)
10. Fraud Detection (penalties, trust check trigger, appeal management)
11. Analytics (per-platform stats, engagement, top performers)
12. Review Queue (flagged campaigns, approve/reject with refund)
13. Audit Log (admin action history with filters)
14. Settings (system configuration display)

---

## 4. The Creator App

The creator app runs on the creator's device, handles onboarding, campaign browsing, content review, automated posting, and metric reporting. Three implementations exist.

### 4.1 v1 — Desktop App (Python/Flask, Windows)

**Stack:** Flask web app (localhost:5222) + Playwright browser automation + SQLite

**32+ Flask routes covering:**
- Auth (login/register with server)
- Onboarding (5-step: connect platforms via browser login → scrape profiles → select niches → set region/mode → enter AI keys)
- Campaign lifecycle (poll server, accept/reject invitations, view details)
- Content review (approve/reject/edit/restore/unapprove drafts, bulk approve-all)
- Post scheduling and execution
- Earnings and withdrawal
- Settings (reconnect platforms, update profile, manage AI keys)

**Background Agent (always-running async):**

| Task | Interval | Description |
|---|---|---|
| Execute due posts | 60s | Find scheduled posts, execute via Playwright, sync to server |
| Generate daily content | 120s | Create drafts for active campaigns (per platform, anti-repetition) |
| Poll campaigns | 10min | Fetch new invitations from server, sync statuses |
| Check sessions | 30min | Verify platform login sessions are alive |
| Scrape metrics | Tiered | T+1h, T+6h, T+24h, T+72h engagement collection |
| Refresh profiles | 7 days | Re-scrape follower counts, bios, recent posts |

**Local Database (13 SQLite tables):**
- `local_campaign` — Server campaign mirror with local status
- `agent_draft` — AI-generated content per platform per day
- `post_schedule` — Scheduled post queue with retry tracking
- `local_post` — Published posts with URLs and server sync status
- `local_metric` — Scraped engagement with reporting status
- `local_earning` — Per-campaign earnings
- `scraped_profile` — Per-platform profile data (followers, bio, engagement rate, extended data)
- `settings` — Key-value config (mode, API keys, onboarding state)
- `local_notification` — Desktop notification queue
- `agent_research` — Campaign research findings
- `agent_user_profile` — Extracted user style notes
- `agent_content_insights` — Engagement analytics per platform/pillar
- (indexed: post_schedule by status+time, notifications by read+time)

### 4.2 v2 — Android App (Kotlin, ~85% Complete)

**Stack:** Kotlin + Jetpack Compose + Material3 + Hilt + Room

**14 Gradle modules:**
- `app/` — MainActivity, navigation (5 nav graphs), theme, DI
- `core/common` — Constants, extensions, Result wrapper
- `core/domain` — Models and repository interfaces (Auth, Campaign, Content, Earning, Metrics, Payout, SocialPlatform, Task, User)
- `core/data` — Repository implementations, Room database, secure token storage
- `core/network` — Retrofit API client (25 endpoints), DTOs, auth interceptor
- `core/media` — Media generation: OpenAI DALL-E 3 images, OpenAI TTS voiceover, FFmpeg video stitching
- `core/picoclaw` — Go AI agent integration (foreground service, HTTP API on port 8765, 4 media tools)
- `feature/auth` — Login, register, Google OAuth screens
- `feature/onboarding` — 4-screen welcome + accessibility + platform setup + completion
- `feature/dashboard` — Home screen with stats
- `feature/campaigns` — Campaign browser with filters
- `feature/content` — Content generation (video slideshow + static images), preview
- `feature/earnings` — Earnings summary + history
- `feature/payouts` — Overview, withdraw, payment methods
- `feature/settings` — Profile, notification prefs, social accounts
- `accessibility/` — AccessibilityService + 5 platform automators (TikTok + Instagram proven, YouTube + Twitter + Facebook scaffolded)

### 4.3 v3 — Android App (Kotlin, Phase 1 MVP Complete)

**Stack:** Kotlin + Jetpack Compose + Room + Hilt (single module, ~73KB)

**Key Innovation — Free AI via WebView:**
- Hidden Android WebView loads gemini.google.com
- Uses creator's existing Google session (cookies persist)
- Injects prompts via `evaluateJavascript()`, polls for response
- Completion detection: 3 consecutive identical text snapshots
- Zero API cost (~60 messages/day on free tier)
- Phase 2 adds: Copilot (~30/day), ChatGPT (~20/day), DeepSeek (~50/day) = ~160 total/day

**Key Innovation — Declarative JSON Script Engine:**
- Platform automation defined as JSON step sequences (not hardcoded)
- Each step: type (launch, click, text_input, media_select, wait_and_verify, scroll)
- Fallback selector chains per step (try resource ID → content description → text → position)
- Template variables: `{{caption}}`, `{{media_path}}`, `{{hashtags}}`
- Human-like timing: configurable min/max delays per step, character-by-character typing (30-90ms)
- Error recovery: popup dismissal, back-and-retry, max retries, graceful failure to manual queue
- **OTA-updatable**: When a platform updates its UI, push new JSON script — no app update needed

**Data Model (3 Room entities):**

```
Campaign: id, title, brief, brandName, platforms (CSV), tone, hashtags, status, createdAt
Post: id, campaignId (FK), platform, contentText, mediaPath, status, postedAt, likes, comments, views, createdAt
AiTask: id, campaignId, platform, taskType, prompt, result, status, createdAt
```

**Post Status State Machine:**
```
QUEUED → APPROVED → POSTING → POSTED → VERIFIED (Phase 3)
                             → FAILED
```

**5 UI Screens (Jetpack Compose + Material 3 dark theme):**
1. Dashboard — engine status, local stats (queued/posted/campaigns), active campaign cards
2. Campaigns — create campaigns, list active/completed, delete
3. Queue — approval queue with approve/edit/reject/media-attach per post, badge count on nav
4. Analytics — posted count, platform breakdown
5. Settings — Accessibility Service status/enable, Gemini connection status/login

**Phase 1 Scope:** 2 platforms (Instagram + X), 1 AI provider (Gemini), local campaigns only, no backend sync, sideload APK distribution.

---

## 5. Content Generation

### 5.1 AI Provider Strategy

| Provider | Cost | Method | Daily Capacity | Used In |
|---|---|---|---|---|
| Google Gemini API | Free tier | REST API (gemini-2.5-flash) | High | v1 |
| Mistral API | Free tier | REST API (mistral-small-latest) | High | v1 (fallback) |
| Groq API | Free tier | REST API (llama-3.3-70b-versatile) | High | v1 (fallback) |
| Gemini Web | Free | Hidden WebView scraping | ~60/day | v3 |
| Copilot Web | Free | Hidden WebView scraping | ~30/day | v3 (Phase 2) |
| ChatGPT Web | Free | Hidden WebView scraping | ~20/day | v3 (Phase 2) |
| DeepSeek Web | Free | Hidden WebView scraping | ~50/day | v3 (Phase 2) |
| OpenAI API | Paid | GPT-4o-mini via PicoClaw Go agent | Unlimited | v2 (abandoned) |

### 5.2 Content Generation Prompt

The content prompt enforces UGC (user-generated content) style — authentic, personal, not corporate:

**Role:** Social media creator making authentic UGC posts about a product they genuinely use.

**Hook Patterns:** problem-solution, surprising result, social proof, curiosity gap, contrarian take.

**Body Structure:** Personal experience → 1-2 features/benefits → minor caveat (authenticity) → natural CTA.

**Hard Rules:**
- NO AI language ("game-changer", "leverage", "unlock", "dive in")
- NO corporate jargon or marketing speak
- NO excessive exclamation marks
- MUST feel like a real person wrote it on their phone

**Platform-Specific Formatting:**

| Platform | Format | Length | Style |
|---|---|---|---|
| X | Punchy hook + key benefit + 1-3 hashtags | Max 280 chars | Direct, opinionated |
| LinkedIn | Story format, aggressive line breaks, question at end, 3-5 hashtags | 500-1500 chars | Professional but personal |
| Facebook | Conversational, ask a question, 0-2 hashtags | 200-800 chars | Casual, friendly |
| Reddit | Title (60-120 chars, NOT clickbait) + Body (500-1500 chars) | 560-1620 chars | Community member, specifics, no hashtags/emojis |
| Instagram | Short caption + relevant hashtags | Under 200 chars | Visual-first, emojis OK |
| TikTok | Short description + trending hashtags | Under 150 chars | Trend-aware, Gen Z voice |

**Output Format (JSON):**
```json
{
  "x": "tweet text",
  "linkedin": "post text",
  "facebook": "post text",
  "reddit": {"title": "...", "body": "..."},
  "instagram": "caption text",
  "image_prompt": "vivid description for image generation"
}
```

**Anti-Repetition:** Previous post hooks injected into prompt to force completely different angles each day. Day number tracking enables daily variation.

### 5.3 Image Generation

**v1 Provider Chain (free tier, automatic fallback via ImageManager):**
1. Gemini Flash Image (txt2img + img2img, ~500 free/day)
2. Cloudflare Workers AI (FLUX.1-schnell)
3. Together AI (FLUX.1-schnell free)
4. Pollinations AI (turbo)
5. PIL branded template (dark gradient + white text) — last resort

Each provider implements the `ImageProvider` abstract base class (`scripts/ai/image_provider.py`) with `text_to_image()` and optionally `image_to_image()`. The `ImageManager` (`scripts/ai/image_manager.py`) handles registry, priority ordering, and auto-fallback — same pattern as text `AiManager`. Key methods: `generate()` (txt2img), `transform()` (img2img — only tries providers that set `supports_img2img=True`).

**Three generation modes (`scripts/utils/content_generator.py`):**
1. **img2img** — if a product image path is provided and the file exists, calls `ImageManager.transform()` using `build_img2img_prompt()` from the prompt framework
2. **txt2img** — enhanced UGC prompt via `build_simple_prompt()` + `get_negative_prompt()`, calls `ImageManager.generate()`
3. **PIL fallback** — last resort if all API providers are unavailable

**Campaign Image Pipeline (`scripts/background_agent.py`):**
- `_download_campaign_product_images()` downloads ALL images from `campaign.assets.image_urls` to `data/product_images/{campaign_id}/`. Caches on disk — re-downloads are skipped.
- `_pick_daily_image(images, day_number)` rotates through the list by day number (Day 1→image[0], Day 2→image[1], wraps around), so each day's post features a different product photo.

**UGC Post-Processing Pipeline (`scripts/ai/image_postprocess.py`):**

Applied automatically after every successful generation to make AI images look like authentic phone photos:
1. Resize to platform-optimal dimensions (X: 1200×675, LinkedIn/Facebook: 1200×627, Reddit/Instagram: 1080×1080, TikTok: 1080×1920)
2. Slight desaturation (13%) — AI images are oversaturated
3. Warm or cool color cast — mimic phone camera processing
4. Film grain (numpy) — diffusion models cannot generate authentic grain
5. Subtle vignetting — mimic phone lens
6. JPEG compression at quality 80 — introduce natural artifacts
7. EXIF metadata injection (piexif) — mimic common phone cameras

**Photorealism Prompt Framework (`scripts/ai/image_prompts.py`):**
8-category framework with pools for REALISM_TRIGGERS, CAMERAS, LIGHTING, TEXTURES, COLORS, COMPOSITIONS, QUALITY_MARKERS. Helper functions: `build_ugc_prompt()`, `build_img2img_prompt()`, `build_simple_prompt()`, `get_negative_prompt()`.

**v2 Pipeline (paid, v2 Android only):**
1. DALL-E 3 generates images from prompt
2. OpenAI TTS generates voiceover
3. FFmpeg stitches into video slideshow
4. Supports both video slideshow and static image carousel content types

### 5.4 Research Phase

Before generating content, the system can enrich the campaign brief:
1. Extract URLs from campaign assets
2. Deep scrape each URL via web crawler (content, metadata, OG tags)
3. Build research brief from scraped data
4. Inject into generation prompt for more informed content
5. Falls back transparently if no URLs or scraping fails

---

## 6. Posting Automation

### 6.1 Desktop — Playwright Browser Automation (v1)

**How it works:** Launches real browser instances with persistent user profiles (established via one-time manual login). Each platform gets its own browser context. Posts are created by navigating the platform's compose UI and interacting with real DOM elements.

**Supported Platforms:** X, LinkedIn, Facebook, Reddit (enabled). TikTok, Instagram (code preserved, disabled).

**JSON Script Engine (`scripts/engine/`):**

Posting logic is now declarative — defined in JSON files in `config/scripts/` rather than hardcoded Python. Inspired by AmpliFire v3's `ScriptModel.kt`. The engine layer:

| Module | Role |
|---|---|
| `script_parser.py` | Parses JSON scripts into data models: `PlatformScript`, `ScriptStep`, `SelectorTarget`, `DelayRange`, `WaitCondition`, `ErrorRecoveryConfig`, `SuccessSignal` |
| `selector_chain.py` | Fallback selector chains — tries each selector (css, text, role, testid, aria_label, xpath) before failing |
| `human_timing.py` | Per-step configurable delays + character-by-character typing with random speed |
| `error_recovery.py` | Retry strategies: exponential backoff, popup dismiss, navigate-back |
| `script_executor.py` | Main executor supporting 13 action types: `goto`, `click`, `text_input`, `file_upload`, `keyboard`, `dispatch_event`, `wait_and_verify`, `scroll`, `evaluate`, `wait`, `screenshot`, `extract_url`, `browse_feed` |

**Scripts:** `config/scripts/x_post.json`, `linkedin_post.json`, `facebook_post.json`, `reddit_post.json`

`post.py` tries `post_via_script()` first; if no script exists or the script fails, it falls back to the legacy hardcoded platform functions. `post_scheduler.py` uses the unified `post_to_platform()` function.

**Human Emulation:**
- Character-by-character typing (30-120ms per character, per-step configurable)
- Per-step delay ranges (min/max ms) defined in JSON
- Feed browsing before/after posting
- Mouse movement simulation
- Randomized scroll patterns

**Platform-Specific Posting:**

| Platform | Compose Method | Image Upload | Post Confirmation | URL Capture |
|---|---|---|---|---|
| X | Navigate compose URL → type in textbox → Ctrl+Enter | Hidden `input[data-testid="fileInput"]` | Poll profile for new post | Profile page scan |
| LinkedIn | Click "Start a post" button → modal → type → Post | ClipboardEvent JS paste or file input | "View post" success dialog or activity page | Activity page |
| Facebook | Click "What's on your mind?" → modal → type → Post | "Photo/video" button → hidden file input | Modal closes | Profile URL fallback |
| Reddit | Navigate `/user/{username}/submit` → fill title + body → Post | Optional file upload | Redirect to `/submitted/?created=t3_XXX` | Redirect URL |

**Key Gotchas:**
- **X:** Overlay div intercepts pointer events — must use `dispatch_event("click")` not `.click()`
- **LinkedIn:** Shadow DOM — use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()`
- **Reddit:** Shadow DOM (faceplate web components) — Playwright locators pierce automatically
- **Instagram:** Multi-step dialog flow requiring `force=True` on all buttons
- **TikTok:** Draft.js editor requires `Ctrl+A → Backspace` to clear pre-filled filename

### 6.2 Android — Accessibility Service Automation (v2/v3)

**How it works:** Uses Android's Accessibility Service to interact with real native social media apps installed on the device. The service reads the UI tree and performs actions (click, type, scroll) just like a human user.

**Supported Platforms (v3):** Instagram, X (working). TikTok, Facebook, Reddit (Phase 2).

**Script-Driven Architecture (v3):**
- Each platform action is defined as a JSON file (e.g., `ig-post.json`, `x-post.json`)
- Steps: launch app → wait for UI → click compose → type caption → attach media → post → verify
- Fallback selector chains per step (resource ID → content description → text)
- Template variables substituted at runtime: `{{caption}}`, `{{media_path}}`
- OTA-updatable: push new JSON when platform UI changes

**Example Script Step (Instagram "tap create" button):**
```json
{
  "id": "tap_create",
  "type": "click",
  "target": {
    "strategy": "fallback_chain",
    "selectors": [
      { "by": "content_desc", "value": "Create" },
      { "by": "content_desc", "value": "New post" },
      { "by": "id", "value": "com.instagram.android:id/creation_tab" }
    ]
  },
  "delay_before_ms": { "min": 400, "max": 900 },
  "wait_for": { "content_desc": "Gallery", "timeout_ms": 3000 }
}
```

**Error Recovery:**
- `on_element_not_found`: retry with next selector in fallback chain
- `on_unexpected_screen`: press back and retry
- `on_popup`: dismiss and continue
- `on_failure` (after max_retries): queue for manual posting
- Max retries: 3 per script

**Media Handling:**
- Primary: Navigate gallery picker within app, find matching thumbnail
- Fallback: Android Share Intent to target app with media attachment (FileProvider URI)

### 6.3 Post Scheduling

**Region-Aware Peak Windows (v1):**

| Platform | Peak Hours (local time) |
|---|---|
| X | 8-10 AM, 12-1 PM, 5-7 PM |
| LinkedIn | 8-10 AM, 12-1 PM |
| Facebook | 12-2 PM, 7-9 PM |
| Reddit | 8-11 AM, 6-9 PM |

**Scheduling Rules:**
- Post during peak windows for campaign's target region
- Min 30 minutes between ANY two posts
- Min 60 minutes between same-platform posts for different campaigns
- 1-15 minute random jitter to avoid patterns
- Daily limit: `min(campaigns x 4, 20)` for ≤3 campaigns; `min(campaigns x 3, 20)` for more
- Lookahead: 3 days to find available slots

**Anti-Detection (v3 additional):**
- 15-45 minute random delays between cross-platform posts
- No posting during configurable quiet hours (sleep time)
- Occasional pauses simulating reading
- Natural scroll patterns with ease-in/out curves

---

## 7. Metric Collection & Reporting

### 7.1 Scraping Schedule

| Tier | Timing | Purpose | Final? |
|---|---|---|---|
| T+1h | 1 hour after posting | Verify post is live | No |
| T+6h | 6 hours after posting | Early engagement snapshot | No |
| T+24h | 24 hours after posting | Primary metric (most important) | No |
| T+72h | 72 hours after posting | Final metric (used for billing) | Yes |

### 7.2 Metrics Collected Per Platform

| Platform | Impressions | Likes | Reposts/Shares | Comments | Clicks | Method |
|---|---|---|---|---|---|---|
| X | Views (aria-label) | Likes (aria-label) | Reposts (aria-label) | Replies (aria-label) | N/A | Playwright selectors |
| LinkedIn | Impressions (CSS) | Likes (CSS) | Reposts (CSS) | Comments (CSS) | N/A | Playwright + regex fallback |
| Facebook | N/A (personal posts) | Likes (aria-label) | Shares (aria-label) | Comments (aria-label) | N/A | Playwright + body text |
| Reddit | Views (shreddit-post attr) | Score (shreddit-post attr) | N/A | Comments (comment-count) | N/A | Playwright selectors |

### 7.3 Server-Side Metrics (v2)

v2 uses real platform APIs with provider-agnostic interfaces:
- TikTok: OAuth + analytics API
- Instagram: OAuth + insights API
- YouTube: OAuth + analytics API
- Generic: Mock provider for testing

Hourly cron job syncs metrics. Earning promotion from PENDING to AVAILABLE after 7-day hold period.

---

## 8. Three Implementations Compared

| Aspect | v1 (Ours — Deployed) | v2 (Dan — Shelved) | v3 (Dan — Phase 1 Done) |
|---|---|---|---|
| **Server** | FastAPI + Supabase, ~90 routes, 11 models, Vercel **LIVE** | NestJS + Prisma, 24 modules, 53 models, Docker, NOT deployed | None (Phase 3 planned) |
| **Company Dashboard** | 10 pages, Jinja2 **LIVE** | Brand portal (6+ NestJS modules) | Not built (Phase 4) |
| **Admin Dashboard** | 14 pages, Jinja2 **LIVE** | JWT + role-based access (5 admin roles) | Not built (Phase 3) |
| **Creator App** | Flask web (desktop), 32+ routes | Kotlin Android, 14 Gradle modules, ~85-95% done | Kotlin Android, single module, Phase 1 complete |
| **Posting** | Playwright (browser), 4 platforms working | Accessibility Service, TikTok + IG working | Accessibility Service, IG + X working, JSON scripts |
| **AI Cost** | $0 (free API tiers) | $$$ (paid OpenAI APIs) — **deal-breaker** | $0 (free WebView scraping) |
| **AI Content** | Text + images (txt2img + img2img from product photos, daily rotation, UGC post-processing) | Text + images + video + voiceover | Text only (media from gallery) |
| **Payments** | Stripe (stub) | PayPal Payouts (working) | None (Phase 3) |
| **Auth** | JWT (email/password) | JWT + Google OAuth + 3 strategies | None (local only) |
| **Platforms** | X, LinkedIn, Facebook, Reddit | TikTok, Instagram (+ 3 scaffolded) | Instagram, X |
| **Tests** | None (manual) | 46 unit tests | 2 unit tests |
| **OTA Scripts** | JSON script engine (config/scripts/), not OTA yet | N/A | JSON scripts, OTA-planned |
| **Distribution** | Desktop (Python + Playwright) | Android APK | Android APK (sideload) |
| **Trust System** | Score 0-100, events-based | User tiers (FREE/PREMIUM) | 3 tiers (Seedling/Grower/Amplifier) |
| **Matching** | AI scoring (Gemini) + niche fallback | Hard filters | Not yet (Phase 3) |
| **Created** | 2026 (multiple sessions) | 2026-02-24 | 2026-03-11 |

### 8.1 Complementary Strengths

The three implementations are naturally complementary:

- **v1** has the most complete and deployed **server + marketplace + dashboards**
- **v2** has the most mature **server architecture** (53 models, proper OAuth, working PayPal, role-based admin)
- **v3** solves the **AI cost problem** ($0 via WebViews) and has the most promising **mobile automation** (declarative JSON scripts, OTA-updatable)

**The natural merge:** v1's server and dashboards as the backend, v3's Android app as the mobile client, with v3's free AI approach and v2's architectural patterns informing the combined product.

---

## 9. Deployment & Infrastructure

### 9.1 Server (v1 — Currently Deployed)

- **Host:** Vercel (serverless functions)
- **Database:** Supabase PostgreSQL (aws-1-us-east-1, transaction pooler port 6543)
- **Connection:** NullPool + `prepared_statement_cache_size=0` (pgbouncer compatibility)
- **Build:** `vercel deploy --yes --prod --cwd server`
- **Environment:** DATABASE_URL, JWT_SECRET_KEY, ADMIN_PASSWORD, GEMINI_API_KEY

**Live URLs:**
- Company dashboard: `server-five-omega-23.vercel.app/company/login`
- Admin dashboard: `server-five-omega-23.vercel.app/admin/login`
- API docs (Swagger): `server-five-omega-23.vercel.app/docs`

### 9.2 Creator App (v1 — Desktop)

- **Runtime:** Python 3.9+ with Playwright Chromium
- **Port:** localhost:5222 (Flask)
- **Data:** `data/local.db` (SQLite with WAL mode)
- **Browser profiles:** `profiles/` directory (persistent per platform)
- **Distribution:** Currently manual. Future: PyInstaller → Tauri (lightweight desktop agent for posting only, web dashboard for everything else).

### 9.3 Creator App (v3 — Android)

- **Min SDK:** 28 (Android 9.0 Pie)
- **Target SDK:** 35 (Android 15)
- **APK size:** ~2.4 MB (minified + shrunk)
- **Distribution:** Sideload APK (GitHub Releases). Google Play will reject Accessibility Service automation.
- **Database:** Room DB (`amplifire.db`)
- **AI:** Hidden WebView (Gemini, future: Copilot/ChatGPT/DeepSeek)

---

## 10. Product Roadmap

### Near-Term (v1 — Verification Phase)

| Task | Status | Description |
|---|---|---|
| Scheduled posting verification | In Progress | Fix URL capture for LinkedIn/Facebook/Reddit |
| Metric scraping verification | Pending | Verify T+1h/6h/24h/72h collection works E2E |
| Billing verification | Pending | Verify earnings calculation, budget deduction, dedup |
| Earnings/Stats verification | Pending | Verify user dashboard shows correct numbers |
| Stripe integration verification | Pending | Verify company top-up and user payout flow |
| Admin dashboard verification | Pending | Verify all 14 admin pages work correctly |

### Medium-Term (Combined Product)

| Phase | Focus | Key Deliverables |
|---|---|---|
| Merge v1+v3 | Android client → v1 server | v3 app connects to v1 API, onboarding, campaign sync |
| Multi-platform | Expand coverage | v3 adds TikTok, Facebook, Reddit scripts |
| Multi-AI | Reduce dependency | v3 adds Copilot, ChatGPT, DeepSeek providers |
| OTA Scripts | Eliminate app updates | Backend serves platform scripts, app auto-updates |
| Real Payments | Enable cash-out | Stripe Connect (v1 stub → real) + PayPal (from v2) |

### Long-Term (Scale)

| Phase | Focus | Key Deliverables |
|---|---|---|
| Corporate Dashboard | Web app for brands | Campaign wizard, analytics, ROI reporting, billing |
| Reputation System | Gamified trust | 3-tier system (Seedling/Grower/Amplifier), premium CPM rates |
| Content Media | Rich content | AI image generation, video slideshows, blog posts |
| Advanced Fraud | Automated enforcement | Engagement velocity analysis, screenshot proof verification |
| International | Global expansion | Multi-currency payments, regional compliance (FTC, ASCI) |

---

## 11. Open Questions & Risks

### Technical Risks

1. **Platform detection.** Both Playwright (desktop) and Accessibility Service (Android) can be detected by platforms. X has already locked an account during testing. Mitigation: human emulation, rate limiting, profile warming.

2. **AI free tier sustainability.** WebView scraping depends on platforms not adding CAPTCHAs or restricting free tiers. Mitigation: multi-provider fallback, optional paid API key field.

3. **OTA script fragility.** Platform UI changes can break JSON scripts. Mitigation: fallback selector chains (3+ selectors per element), rapid OTA push capability.

4. **Google Play rejection.** Accessibility Service automation will be rejected from Google Play. Distribution must be sideload (APK via website/GitHub). This limits discoverability.

### Business Risks

1. **Cold start problem.** Need companies AND creators simultaneously. Plan: seed with personal brand content (v1 engine), use free features to attract creators first.

2. **Legal compliance.** FTC (US) requires #ad/#sponsored disclosure. ASCI (India) has similar rules. Must auto-append disclosure text. Deferred to Phase 3.

3. **Revenue scale.** At 20% take rate with micro-earnings, need high volume to reach meaningful revenue. Target: 10,000 companies x $5,000 avg spend x 20% = $50M SOM (3-year).

4. **AI content quality.** Free-tier AI may produce lower-quality content than paid APIs. Mitigation: prompt engineering, creator review step, anti-AI-language guardrails.

### Open Decisions

1. **Payment rails.** Stripe? PayPal? UPI (India)? Crypto? Per-region? v2 has working PayPal, v1 has Stripe stub.

2. **Distribution strategy.** Sideload APK + website? F-Droid? Direct APK download with auto-update?

3. **Merge strategy.** Which server wins (v1 FastAPI or v2 NestJS)? How to combine v1's deployed marketplace with v3's Android client?

4. **Desktop vs mobile priority.** v1 is desktop-only (Playwright). v3 is Android-only (Accessibility Service). Which platform to prioritize, or both?
