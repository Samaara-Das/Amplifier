# Amplifier — SLC Specification

**Date**: 2026-04-05
**Status**: Living document — updated to match current codebase

---

## 1. Product Overview

Amplifier is a two-sided marketplace where **companies pay people to post about their products on social media**. Companies create campaigns with budgets. Amplifier's AI matches campaigns to the right users. Users accept campaigns, AI generates tailored content, and Amplifier posts it to their social accounts automatically via Playwright browser automation. Users earn money based on real engagement metrics scraped from their posts.

### Money Flow

```
Company adds funds (Stripe Checkout) --> company.balance_cents
Company activates campaign            --> balance deducted --> campaign.budget_remaining
AI matches campaign to users           --> invitations sent (3-day TTL)
User accepts, AI generates content     --> posts scheduled
Playwright posts to platforms           --> post URLs captured
Metric scraper scrapes engagement       --> metrics submitted to server
Server billing engine calculates        --> payout records created (7-day hold)
Hold period passes                      --> earning becomes "available"
User requests withdrawal ($10 min)      --> Stripe Connect transfer (or test mode)
```

### Three Components

| Component | Tech | Who Uses It | Where It Runs |
|-----------|------|-------------|---------------|
| **Server** | FastAPI + Jinja2 + Supabase PostgreSQL | Companies (web), Admins (web) | Vercel |
| **User App** | Flask (localhost:5222) + local SQLite | Users earning money | User's Windows desktop |
| **Posting Engine** | Playwright + JSON scripts | Background agent | User's Windows desktop |

---

## 2. Company Side

### Registration & Login

- Email + password authentication via `/api/auth/company/register` and `/api/auth/company/login`
- JWT token returned on success (`HS256`, 24-hour expiry)
- Lands on campaign list page (`/company/dashboard`)

### Campaign Creation

Two paths:

**Manual creation** via `POST /api/company/campaigns` (schema: `CampaignCreate`):

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | Yes | Max 255 chars |
| `brief` | text | Yes | Full campaign description |
| `assets` | JSON | No | `{image_urls: [], links: [], hashtags: [], brand_guidelines: ""}` |
| `budget_total` | float | Yes | Minimum $50 (enforced in `campaigns.py:MINIMUM_CAMPAIGN_BUDGET`) |
| `payout_rules` | PayoutRules | Yes | `rate_per_1k_impressions`, `rate_per_like`, `rate_per_repost`, `rate_per_click` |
| `targeting` | Targeting | No | `min_followers`, `min_engagement`, `niche_tags`, `required_platforms`, `target_regions` |
| `content_guidance` | text | No | Tone, must-include/avoid phrases |
| `penalty_rules` | JSON | No | `{post_deleted_24h: 5.00, off_brief: 2.00, fake_metrics: 50.00}` |
| `start_date` / `end_date` | datetime | Yes | Campaign duration |
| `max_users` | int | No | Cap on accepted users |

Campaigns are created as `status=draft` with `screening_status=approved` (content screening is auto-approved; manual review is deferred).

**AI wizard** via `POST /api/company/campaigns/ai-wizard` (schema: `WizardRequest`):

1. Company provides: product description, name, features, campaign goal, public URLs, target niches/regions, must-include/avoid phrases, budget range, platform requirements
2. Server deep-crawls company URLs via BFS (`campaign_wizard.deep_crawl_urls()`) -- httpx + BeautifulSoup, up to 10 pages, 2 hops deep. Extracts titles, content, images, metadata, nav links. Works on Vercel serverless (no browser needed).
3. Gemini generates: campaign title, comprehensive brief (500-1000 words), content guidance (200-400 words), suggested payout rates, suggested budget. Uses model fallback chain: `gemini-2.5-flash` -> `gemini-2.0-flash` -> `gemini-2.5-flash-lite`.
4. Gemini also runs content screening (keyword flagging, category classification). Results stored in `ContentScreeningLog`.
5. Returns generated draft for company to review/edit before creating the campaign via the manual endpoint.

**Reach estimation** via `POST /api/company/campaigns/reach-estimate` and `GET /api/company/campaigns/{id}/reach-estimate`:

- Counts eligible users using the same hard filters as matching
- Estimates impressions at 5-15% of total follower counts
- Suggests payout rates based on niche tier (high-value: finance/crypto/tech, engagement: beauty/fashion/fitness, default)

### Campaign Status Transitions

```
draft --> active --> paused --> active (resume)
draft --> active --> cancelled
draft --> cancelled
active --> completed (budget exhausted with auto_complete)
active --> paused (budget exhausted with auto_pause)
```

Activation requires: `company.balance >= campaign.budget_total`. Budget is deducted from company balance on activation (not on draft creation). Activation is blocked if `screening_status` is `flagged` or `rejected`.

### Campaign Management

- **Update** (`PATCH /api/company/campaigns/{id}`): title, brief, assets, content_guidance, status. Content edits increment `campaign_version` (user app detects changes). Content screening auto-approves edits.
- **Clone** (`POST /api/company/campaigns/{id}/clone`): duplicates all fields, resets status to draft, zeros counters. Checks balance.
- **Delete** (`DELETE /api/company/campaigns/{id}`): only draft or cancelled campaigns. Refunds budget_total for drafts.
- **Budget top-up** (`POST /api/company/campaigns/{id}/budget-topup`): adds funds, resumes auto-paused campaigns, resets budget alert flag.
- **CSV export** (`GET /api/company/campaigns/{id}/export`): downloads campaign performance report with per-post metrics, user info, and earnings. Supports date range filtering.

### Campaign Detail (Company View)

- Invitation stats: total invited, accepted, rejected, expired, pending (calculated from denormalized counters on Campaign model)
- Per-user invitation status with timestamps
- Budget management: 80% alert flag (`budget_alert_sent`), exhaustion action (`auto_pause` or `auto_complete`)

### Company Dashboard Pages (Jinja2)

7 router files in `server/app/routers/company/`: login, dashboard, campaigns, billing, influencers, stats, settings. 10 total HTML pages. Blue `#2563eb` theme, DM Sans font, gradient cards, SVG Heroicons navigation.

### Billing (Company Side)

- Companies add funds via Stripe Checkout (`payments.create_company_checkout()`)
- Verification via `payments.verify_checkout_session()` -- retrieves completed session, returns `{company_id, amount_cents, payment_status}`
- Balance stored on `Company.balance` (float, legacy) and `Company.balance_cents` (integer cents)
- Stripe is optional -- falls back to manual balance adjustment if not configured

---

## 3. User Side

### Registration & Login

- Email + password via `/api/auth/register` and `/api/auth/login`
- JWT token saved locally in `config/server_auth.json`
- User app Flask dashboard at `http://localhost:5222` (34 routes, 1538 lines in `scripts/user_app.py`)
- Auth guard redirects to `/login` if not logged in, to `/onboarding` if onboarding not complete

### Onboarding

5-step flow managed by the Flask app:

**Step 1 -- Connect Platforms**: 4 platform cards (X, LinkedIn, Facebook, Reddit). Click "Connect" opens Playwright with persistent profile (`profiles/{platform}-profile/`). User logs in manually, closes browser. On close, `profile_scraper.py` auto-scrapes: display name, bio, followers, following, profile picture, recent posts (up to 20) with engagement, average engagement rate, posting frequency. LinkedIn extended data: about, experience, education, profile viewers, post impressions. Reddit: karma, contributions, age. All stored locally in `scraped_profile` table and synced to server via `PATCH /api/users/me` (`scraped_profiles` JSON field).

**Step 2 -- Choose Niches**: 20 niche checkboxes, none pre-selected. AI-detected niches shown as suggestions but not auto-checked. Audience region auto-detected from IP/system locale, shown as read-only.

**Step 3 -- Operating Mode**: Semi-auto (default, user reviews drafts before posting) or Full-auto (AI generates and posts automatically).

**Step 4 -- API Keys**: User provides free API keys (Gemini, Mistral, Groq) with step-by-step instructions. Each key has a test button. At least 1 working key required. Keys encrypted at rest using machine-derived AES-256-GCM (`scripts/utils/crypto.py`) -- key derived from `username@hostname`, stored in `settings` table with automatic encrypt-on-save / decrypt-on-read for keys in `_SENSITIVE_KEYS` set.

**Step 5 -- Summary**: Shows all configured settings. "Start Amplifier" saves everything, syncs to server, starts background agent.

### Campaign Discovery & Invitations

- Background agent polls server every 10 minutes via `GET /api/campaigns/mine`
- Server runs AI matching (see Section 5 -- Matching) and returns `CampaignBrief` objects
- New invitations stored in local `local_campaign` table with `invitation_status=pending_invitation`
- User sees invitations in Campaigns tab with: title, brief, content guidance, payout rules, required platforms, expiry
- Accept: `POST /api/campaigns/invitations/{id}/accept` -- enforces max active campaigns (3 for seedling tier, see Reputation Tiers)
- Reject: `POST /api/campaigns/invitations/{id}/reject`
- Invitations expire after 3 days (`INVITATION_TTL` in `matching.py`); auto-expired on next poll

### Content Generation

When a campaign is accepted, `background_agent.generate_daily_content()` runs (checked every 120s):

1. **Research phase**: `ContentGenerator.research_and_generate()` extracts company URLs from campaign assets/scraped_data, deep-scrapes each via webcrawler CLI (`C:/Users/dassa/Work/webcrawler/crawl.py`), builds a research brief (capped at 3000 chars).

2. **Text generation**: `ContentGenerator.generate()` uses `AiManager` (see Section 5 -- AI Abstraction). Prompt template (`CONTENT_PROMPT` in `content_generator.py`) generates UGC-style content per platform:
   - X: max 280 chars, 1-3 hashtags
   - LinkedIn: 500-1500 chars, story format, aggressive line breaks, 3-5 hashtags
   - Facebook: 200-800 chars, conversational, 0-2 hashtags
   - Reddit: title (60-120 chars) + body (500-1500 chars), community-member tone, no hashtags
   - `image_prompt`: description for image generation

3. **Daily variation**: `day_number` tracked from unique draft dates. Previous 12 draft hooks passed as anti-repetition context. Each day gets genuinely different content.

4. **Image generation**: Three modes via `ImageManager`:
   - **img2img**: Product photos from campaign assets downloaded (`_download_campaign_product_images()`), rotated daily (`_pick_daily_image()` -- index = `(day_number - 1) % len(images)`), transformed via `ImageManager.transform()` with 0.7 strength
   - **txt2img**: Generated from `image_prompt` via `ImageManager.generate()`
   - **PIL fallback**: Last resort, always available

5. **Draft storage**: Per-platform drafts saved to `agent_draft` table with `image_path` column.

6. **Semi-auto**: Drafts marked for review, desktop notification sent via `utils/tray.py`. User reviews in Campaigns tab.
   **Full-auto**: Drafts auto-approved, scheduled with 30-min spacing + 0-10 min jitter, starting 5 min from now.

### Posting

Background agent checks for due posts every 60 seconds (`execute_due_posts()`):

1. Marks all due posts as `status=posting` immediately (prevents duplicate execution from next tick)
2. Calls `post_scheduler.execute_scheduled_post()` for each
3. Opens Playwright with platform's persistent browser profile
4. Executes via JSON script engine (see Section 5 -- Posting Engine) or falls back to legacy hardcoded functions in `post.py`
5. Captures post URL by navigating to own profile
6. Stores result in `local_post` table
7. Syncs to server via `POST /api/posts` (batch registration with `assignment_id`, `platform`, `post_url`, `content_hash`, `posted_at`)
8. Desktop notification: "Posted to {platform} for {campaign}"

**Error handling**: `post_schedule` table tracks `error_code` (SELECTOR_FAILED | TIMEOUT | AUTH_EXPIRED | RATE_LIMITED | UNKNOWN), `execution_log` (JSON array of step results), `retry_count` / `max_retries` (default 3). `classify_error()` determines retry strategy with exponential backoff.

### Metric Scraping

Scraping schedule per post (`metric_scraper.py`):
- T+1h: verify post is live
- T+6h: early engagement
- T+24h: primary metric
- T+72h: final metric (used for billing, `is_final=True`)

Per-platform scraping:
- **X**: aria-labels on engagement button group (views, likes, reposts, replies)
- **LinkedIn, Facebook**: Browser Use + Gemini (falls back to Playwright selectors) via `metric_collector.py`
- **Reddit**: official APIs via `metric_collector.py`
- **Clicks**: hardcoded to 0 (not available via browser scraping)

Metrics synced to server via `POST /api/metrics` (batch submission). Server triggers `run_billing_cycle()` on every metric submission.

### Earnings & Withdrawals

- Earnings page shows: total earned, current balance, pending (estimated from non-final metrics)
- Per-campaign breakdown: campaign title, posts, impressions, engagement, earned, status
- Per-platform breakdown: earned per platform (aggregated from payout breakdown JSON)
- Payout history: withdrawal records
- Withdrawal via `POST /api/users/me/payout`: $10 minimum, deducts from `earnings_balance`, creates Payout record

### Dashboard Tabs

5 tabs in the Flask app: **Campaigns** (active campaigns, invitations, drafts, scheduling), **Posts** (posted content with URLs and metrics), **Earnings** (balances, breakdowns, withdrawals), **Settings** (platforms, mode, niches, API keys, region), **Onboarding** (first-run setup).

### Local Database

SQLite at `data/local.db` (`scripts/utils/local_db.py`). 13 tables:

| Table | Purpose |
|-------|---------|
| `local_campaign` | Campaign data from server (server_id, assignment_id, title, brief, assets, payout_rules, status, invitation fields, scraped_data, company_name) |
| `local_post` | Posted content (campaign_server_id, platform, post_url, content, content_hash, posted_at, status, synced flag) |
| `local_metric` | Scraped engagement data (post_id, impressions, likes, reposts, comments, clicks, scraped_at, is_final, reported flag) |
| `local_earning` | Earning records (campaign_server_id, amount, period, status) |
| `settings` | Key-value config store. API keys auto-encrypted for `_SENSITIVE_KEYS` (gemini_api_key, mistral_api_key, groq_api_key) |
| `scraped_profile` | Per-platform profile data (follower_count, following_count, bio, display_name, engagement_rate, posting_frequency, ai_niches, profile_data JSON) |
| `post_schedule` | Scheduling queue (campaign_server_id, platform, scheduled_at, content, image_path, draft_id, status lifecycle, error tracking, retry tracking) |
| `agent_user_profile` | User's own profile data for content personalization |
| `agent_research` | Campaign research cache (research_type, content, source_url) |
| `agent_draft` | AI-generated draft content (campaign_id, platform, draft_text, image_path, quality_score, iteration, approved/posted flags) |
| `agent_content_insights` | Content performance tracking (platform, pillar_type, hook_type, avg_engagement_rate) |
| `local_notification` | Background agent event feed (type, title, message, data JSON, read flag) |

---

## 4. Server Architecture

### Deployment

- **Production**: Vercel + Supabase PostgreSQL (US East, `aws-1-us-east-1.pooler.supabase.com:6543`)
- **Local dev**: SQLite (`amplifier.db` in server directory, or `/tmp/amplifier.db` on Vercel)
- Database connection: NullPool + `prepared_statement_cache_size=0` for pgbouncer compatibility
- SSL required for Supabase (`ssl.CERT_NONE` for self-signed certs)

### API Endpoints

~90 routes total across 8 routers mounted in `main.py`:

**Auth** (`/api/auth/`) -- 4 routes:
- `POST /register` -- user registration
- `POST /login` -- user login
- `POST /company/register` -- company registration
- `POST /company/login` -- company login

**Campaigns** (`/api/`) -- 13 routes:
- `POST /company/campaigns` -- create campaign
- `POST /company/campaigns/ai-wizard` -- AI campaign generation
- `POST /company/campaigns/reach-estimate` -- pre-creation reach estimate
- `GET /company/campaigns/{id}/reach-estimate` -- existing campaign reach estimate
- `GET /company/campaigns` -- list company's campaigns
- `GET /company/campaigns/{id}` -- campaign detail with invitation stats
- `PATCH /company/campaigns/{id}` -- update campaign
- `POST /company/campaigns/{id}/clone` -- clone campaign
- `DELETE /company/campaigns/{id}` -- delete campaign
- `POST /company/campaigns/{id}/budget-topup` -- add budget
- `GET /company/campaigns/{id}/export` -- CSV export
- `GET /campaigns/mine` -- user: poll for matched campaigns
- `PATCH /campaigns/assignments/{id}` -- user: update assignment status

**Invitations** (`/api/campaigns/`) -- 4 routes:
- `GET /invitations` -- pending invitations for user
- `POST /invitations/{id}/accept` -- accept invitation
- `POST /invitations/{id}/reject` -- reject invitation
- `GET /active` -- user's active campaigns

**Users** (`/api/users/`) -- 4 routes:
- `GET /me` -- get profile
- `PATCH /me` -- update profile (platforms, followers, niches, region, mode, scraped_profiles, ai_detected_niches)
- `GET /me/earnings` -- earnings summary with breakdowns
- `POST /me/payout` -- request withdrawal

**Posts/Metrics** (`/api/`) -- 2 routes:
- `POST /posts` -- batch register posted content
- `POST /metrics` -- batch submit scraped metrics (triggers billing cycle)

**Admin API** (`/api/admin/`) -- admin-authenticated routes for user/company/campaign management

**System** -- 2 routes:
- `GET /health` -- health check
- `GET /api/version` -- version endpoint for auto-update checks (version `0.1.0`)

### Admin Dashboard

11 router files in `server/app/routers/admin/`: login, overview, users, companies, campaigns, financial, fraud, analytics, review, audit, settings. 14 HTML pages, ~36 routes total.

**Financial router** has 5 routes:
- `GET /financial` -- financial overview
- `POST /financial/run-billing` -- trigger billing cycle
- `POST /financial/run-payout` -- trigger payout cycle
- `POST /financial/run-earning-promotion` -- promote pending earnings past hold period
- `POST /financial/run-payout-processing` -- process payouts via Stripe Connect

### Models (11 tables)

| Model | Table | Key Fields |
|-------|-------|------------|
| `Company` | `companies` | id, name, email, password_hash, balance (float), balance_cents (int), status (active/suspended) |
| `Campaign` | `campaigns` | id, company_id, title, brief, assets (JSON), budget_total, budget_remaining, payout_rules (JSON), targeting (JSON), content_guidance, penalty_rules (JSON), status (draft/active/paused/completed/cancelled), company_urls (JSON), ai_generated_brief, budget_exhaustion_action, budget_alert_sent, screening_status (pending/approved/flagged/rejected), campaign_version, invitation_count, accepted_count, rejected_count, expired_count, max_users, start_date, end_date |
| `User` | `users` | id, email, password_hash, device_fingerprint, platforms (JSON), follower_counts (JSON), niche_tags (JSON), audience_region, trust_score (0-100, default 50), mode (semi_auto/full_auto/manual), tier (seedling/grower/amplifier), successful_post_count, earnings_balance (float), earnings_balance_cents (int), total_earned (float), total_earned_cents (int), status (active/suspended/banned), scraped_profiles (JSON), ai_detected_niches (JSON), last_scraped_at |
| `CampaignAssignment` | `campaign_assignments` | id, campaign_id, user_id, status (pending_invitation/accepted/content_generated/posted/paid/rejected/expired), content_mode (ai_generated/user_customized/repost), payout_multiplier (deprecated, always 1.0), invited_at, responded_at, expires_at |
| `Post` | `posts` | id, assignment_id, platform, post_url, content_hash (SHA256), posted_at, status (live/deleted/flagged) |
| `Metric` | `metrics` | id, post_id, impressions, likes, reposts, comments, clicks, scraped_at, is_final |
| `Payout` | `payouts` | id, user_id, campaign_id (nullable), amount (float), amount_cents (int), period_start, period_end, status (pending/available/processing/paid/voided/failed), available_at, breakdown (JSON with metric_id, post_id, platform, per-metric counts, platform_cut_pct, earning_cents, budget_cost_cents) |
| `Penalty` | `penalties` | id, user_id, post_id (nullable), reason (content_removed/off_brief/fake_metrics/platform_violation), amount (float), amount_cents (int), description, appealed, appeal_result |
| `CampaignInvitationLog` | `campaign_invitation_log` | id, campaign_id, user_id, event (sent/accepted/rejected/expired/re_invited), metadata (JSON) |
| `AuditLog` | `audit_log` | id, action, target_type (user/company/campaign/payout/penalty/system), target_id, details (JSON), admin_ip |
| `ContentScreeningLog` | `content_screening_logs` | id, campaign_id (unique), flagged, flagged_keywords (JSON), screening_categories (JSON), reviewed_by_admin, review_result (approved/rejected), review_notes |

### Services

| Service | File | Purpose |
|---------|------|---------|
| Billing | `billing.py` | Earnings calculation in integer cents, billing cycle, earning promotion (7-day hold), earning voiding, tier promotion |
| Matching | `matching.py` | Campaign-to-user matching (hard filters + Gemini AI scoring + niche fallback) |
| Payments | `payments.py` | Stripe Checkout for companies, Stripe Connect for user payouts, payout processing |
| Trust | `trust.py` | Trust score adjustments, penalty creation, deletion fraud detection, metrics anomaly detection |
| Campaign Wizard | `campaign_wizard.py` | Deep URL crawling, Gemini brief generation, reach estimation, payout rate suggestions |
| Storage | `storage.py` | Supabase Storage file uploads (campaign assets), text extraction from PDF/DOCX/TXT |

### Configuration

`server/app/core/config.py` (Settings via pydantic_settings):

| Setting | Default | Notes |
|---------|---------|-------|
| `database_url` | `sqlite+aiosqlite:///./amplifier.db` | PostgreSQL in production |
| `jwt_secret_key` | `change-me-to-a-random-secret` | Set in Vercel env |
| `jwt_algorithm` | `HS256` | |
| `jwt_access_token_expire_minutes` | `1440` (24h) | |
| `platform_cut_percent` | `20.0` | Amplifier takes 20% of earnings |
| `min_payout_threshold` | `10.0` | Minimum withdrawal amount |
| `stripe_secret_key` | `""` | Optional, test mode |
| `supabase_url` | `""` | For Storage uploads |
| `supabase_service_key` | `""` | For Storage uploads |

### Encryption

**Server-side** (`server/app/utils/crypto.py`): AES-256-GCM authenticated encryption. Key derived via PBKDF2-HMAC-SHA256 from `ENCRYPTION_KEY` env var (100K iterations, salt: `amplifire-encryption-salt-v1`). Format: `iv_hex:ciphertext_hex`. Functions: `encrypt()`, `decrypt()`, `is_encrypted()`, `encrypt_if_needed()`, `decrypt_safe()`.

**Client-side** (`scripts/utils/crypto.py`): Same AES-256-GCM algorithm. Key derived from machine-specific data (`username@hostname`), making encrypted values tied to the specific device. Same API as server-side for consistency.

---

## 5. Technical Architecture

### Posting Engine

JSON-driven declarative posting engine in `scripts/engine/`. Platform posting flows are defined in JSON files (`config/scripts/`), not hardcoded Python.

**Posting scripts** (4 files): `x_post.json`, `linkedin_post.json`, `facebook_post.json`, `reddit_post.json`.

**Engine modules** (6 files):
- `script_parser.py` -- data models: `PlatformScript`, `ScriptStep`, `SelectorTarget`, `Selector`, `WaitCondition`, `DelayRange`. Parses JSON into executable structures. Supports variable resolution (`{{content}}`, `{{image_path}}`).
- `selector_chain.py` -- resilient element finding with fallback chains. Each step can try 3+ selectors before failing. Strategy: `single` or `fallback_chain`.
- `human_timing.py` -- anti-detection timing. Random delays, character-by-character typing (30-80ms per char).
- `error_recovery.py` -- retry with backoff. Error classification and recovery decisions.
- `script_executor.py` -- main executor. Iterates steps, dispatches to handlers, collects results.

**13 action types** (step types in `ScriptExecutor._get_handler()`):

| Action | Purpose |
|--------|---------|
| `goto` | Navigate to URL |
| `click` | Click element via selector chain |
| `text_input` | Type text with human-like delays |
| `file_upload` | Upload files via file input or target selector |
| `keyboard` | Press keyboard keys |
| `dispatch_event` | Dispatch DOM events (for intercepted clicks, e.g., X post button) |
| `wait_and_verify` | Wait for success signals (text or selector) |
| `scroll` | Mouse wheel scroll |
| `evaluate` | Run JavaScript on page or element |
| `wait` | Static wait |
| `screenshot` | Take screenshot for debugging |
| `extract_url` | Extract post URL after posting |
| `browse_feed` | Minimal feed browsing for human emulation |

**Execution flow**: `ScriptExecutor.execute(script)` -> iterates steps -> `_run_step_with_recovery()` (with retries via `error_recovery`) -> `_execute_step()` -> dispatches to handler. Returns `ExecutionResult` with success/failure, log of step results, and captured post URL.

**Legacy fallback**: `scripts/post.py` contains hardcoded per-platform posting functions. The posting pipeline tries `post_via_script()` first, falls back to legacy functions.

### AI Abstraction

**Text generation** (`scripts/ai/`):

- `provider.py` -- abstract base class `AiProvider` with `generate_text(prompt)`, `is_connected`, `is_rate_limited`
- `manager.py` -- `AiManager` registry with auto-fallback. `generate(prompt, preferred=None)` tries providers in registration order, skipping disconnected/rate-limited ones.
- 3 text providers: `gemini_provider.py`, `mistral_provider.py`, `groq_provider.py`
- `create_default_manager()` initializes from env vars: `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`
- Fallback chain: Gemini -> Mistral -> Groq

**Image generation** (`scripts/ai/`):

- `image_provider.py` -- abstract base class `ImageProvider` with `text_to_image()`, `image_to_image()`, `supports_img2img`
- `image_manager.py` -- `ImageManager` registry with auto-fallback. `generate()` for txt2img, `transform()` for img2img (only tries providers with `supports_img2img=True`, falls back to txt2img if all img2img providers fail).
- 5 image providers in `scripts/ai/image_providers/`:
  1. `gemini_image.py` -- Gemini Flash Image (primary, 500/day free, supports img2img)
  2. `cloudflare_image.py` -- Cloudflare Workers AI (secondary, 20-50/day free)
  3. `together_image.py` -- Together AI (if credit available)
  4. `pollinations_image.py` -- Pollinations (free, no signup)
  5. `pil_fallback.py` -- PIL templates (last resort, always available)

**UGC post-processing** (`scripts/ai/image_postprocess.py`):

Runs automatically after every successful image generation. 7-step pipeline:

1. Resize to platform-optimal dimensions (X: 1200x675, LinkedIn: 1200x627, Facebook: 1200x630, Reddit: 1080x1080)
2. Desaturation (13%) -- AI images are oversaturated (`ImageEnhance`, factor 0.87)
3. Color cast (warm/cool) -- mimic phone camera processing (numpy array manipulation)
4. Film grain (sigma=8) -- diffusion models cannot generate authentic grain (numpy noise)
5. Vignetting (strength=0.25) -- mimic phone lens characteristics (numpy gradient mask)
6. JPEG compression at quality 80 -- introduce natural artifacts
7. EXIF metadata injection via `piexif` -- mimic common phone cameras

Requires: `numpy>=1.24.0`, `piexif>=1.1.3`.

### Billing

All money math uses **integer cents** to eliminate float rounding. Legacy float columns preserved for backward compatibility.

**Earning calculation** (`billing.calculate_post_earnings_cents()`):

```
raw_cents = (impressions * rate_per_1k_imp_cents / 1000)
          + (likes * rate_per_like_cents)
          + (reposts * rate_per_repost_cents)
          + (clicks * rate_per_click_cents)

user_cents = raw_cents * (100 - platform_cut_pct) / 100
```

Platform cut: 20% (configurable via `settings.platform_cut_percent`).

**Billing cycle** (`billing.run_billing_cycle()`):
- Triggered on every metric submission (not batched, not cron)
- Incremental: tracks billed metric IDs via payout breakdown JSON to prevent double-billing
- Caps earnings to remaining campaign budget
- Auto-pauses or auto-completes campaign when `budget_remaining < $1.00`
- Flags 80% budget alert when `budget_remaining < 20% of budget_total`
- Creates Payout records with 7-day hold (`EARNING_HOLD_DAYS=7`)
- Increments `user.successful_post_count` and checks tier promotion

**Earning promotion** (`billing.promote_pending_earnings()`):
- Moves payouts from `pending` to `available` after `available_at` timestamp passes
- Runs periodically (triggered by admin or background task)

**Earning voiding** (`billing.void_earnings_for_post()`):
- Voids pending earnings for a specific post (fraud detected during hold period)
- Returns funds to campaign budget
- Only affects `pending` payouts (once `available`, cannot be voided)

### Trust & Fraud Detection

Trust score: 0-100, default 50, stored on `User.trust_score`.

**Trust events** (`trust.TRUST_EVENTS`):

| Event | Adjustment |
|-------|------------|
| `post_verified_live_24h` | +1 |
| `above_avg_engagement` | +2 |
| `campaign_completed` | +3 |
| `user_customized_content` | +1 |
| `post_deleted_24h` | -10 |
| `content_flagged` | -15 |
| `metrics_anomaly` | -20 |
| `confirmed_fake_metrics` | -50 |

Negative events create `Penalty` records with `$0.50 per trust point lost`. If trust drops below 10, user is flagged for ban review (not auto-banned).

**Fraud detection**:
- `detect_deletion_fraud()` -- finds posts marked `live` older than 24h for spot-checking (returns up to 100)
- `detect_metrics_anomalies()` -- flags users whose average engagement is >3x the overall average across all campaigns (requires 5+ users and 3+ metrics per user)
- `run_trust_check()` -- runs both checks, called by admin trigger

### Reputation Tiers

Three tiers with auto-promotion (`billing.TIER_CONFIG`):

| Tier | Threshold | Max Campaigns | CPM Multiplier | Auto-Post | Spot-Check % |
|------|-----------|---------------|----------------|-----------|-------------|
| **Seedling** | Default (new users) | 3 | 1.0x | No | 30% |
| **Grower** | 20 successful posts | 10 | 1.0x | Yes | 10% |
| **Amplifier** | 100 posts + trust >= 80 | Unlimited (999) | 2.0x | Yes | 5% |

Promotion logic in `billing._check_tier_promotion()`: runs on every billing cycle after incrementing `successful_post_count`. Promotion is one-way (no demotion implemented).

Tier limits enforced in `matching.get_matched_campaigns()`: if `active_campaign_count >= max_campaigns`, new matching is skipped and only existing assignments are returned.

### Matching

Pipeline in `matching.get_matched_campaigns()`:

**Stage 1 -- Hard Filters** (`_passes_hard_filters()`):
1. Campaign is `active` with `budget_remaining > 0`
2. User not already assigned to this campaign
3. `accepted_count < max_users` (if set)
4. User has at least 1 required platform connected
5. User meets per-platform min follower counts
6. User's region matches target regions (or campaign targets global, or user is global)
7. User meets min engagement rate
8. User has fewer than tier-max active campaigns

**Stage 2 -- AI Scoring** (`ai_score_relevance()`):
- Builds comprehensive prompt with full scraped profile data (bio, posts with engagement, followers, experience, education, personal details)
- Gemini judges topic relevance, audience fit, and authenticity
- Explicitly told most users are normal people (not influencers) -- low followers/engagement should not be penalized
- Returns score 0-100
- Model fallback: `gemini-2.5-flash` -> `gemini-2.0-flash` -> `gemini-2.5-flash-lite`
- Score cached for 24 hours per (campaign_id, user_id) pair (`_score_cache` dict)
- Cache invalidation on campaign edit or profile refresh

**Fallback**: If AI fails (returns -1.0 sentinel), falls back to niche-tag overlap scoring (`_fallback_niche_score()`: 30 points per overlapping niche tag, 10-point base if no targeting).

**Selection**: Sort by score descending, create `CampaignAssignment` with `status=pending_invitation` and `expires_at = now + 3 days`. Log event in `CampaignInvitationLog`. Also returns existing non-completed assignments.

---

## 6. Platform Support

### Enabled Platforms

| Platform | Enabled | Posting | Metrics | Notes |
|----------|---------|---------|---------|-------|
| **X (Twitter)** | Yes | JSON script + legacy | aria-label scraping | `dispatch_event("click")` required for post button (overlay intercepts pointer events). Image upload via hidden `input[data-testid="fileInput"]`. |
| **LinkedIn** | Yes | JSON script + legacy | Browser Use + Gemini (fallback: Playwright) | Shadow DOM -- must use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()`. Image via file input or `expect_file_chooser`. |
| **Facebook** | Yes | JSON script + legacy | Browser Use + Gemini (fallback: Playwright) | Image upload via "Photo/video" button then hidden file input. |
| **Reddit** | Yes | JSON script + legacy | Official APIs | Shadow DOM (faceplate web components) -- Playwright locators pierce automatically. Posts to 1 random subreddit per run from configured list: Daytrading, Forex, StockMarket, SwingTrading, AlgoTrading. |
| **TikTok** | No (`enabled: false`) | Code preserved | N/A | Draft.js editor requires `Ctrl+A -> Backspace` to clear. Blocked in India (needs VPN). |
| **Instagram** | No (`enabled: false`) | Code preserved | N/A | Multi-step dialog flow. All buttons need `force=True` due to overlay intercepts. |

### Platform Profiles

Each platform has a persistent Playwright browser profile in `profiles/{platform}-profile/`. Established by one-time manual login via `scripts/login_setup.py`. Per-platform proxy support configured in `config/platforms.json` (used in `_launch_context()`).

---

## 7. Background Agent

`scripts/background_agent.py` -- always-running async process with 6 task loops:

| Task | Interval | Function | What It Does |
|------|----------|----------|-------------|
| **Due posts** | 60s | `execute_due_posts()` | Checks `post_schedule` for queued posts past `scheduled_at`, executes them, syncs to server |
| **Content generation** | 120s | `generate_daily_content()` | Checks accepted campaigns for missing today's drafts, generates per-platform content + images, schedules in full-auto mode |
| **Campaign polling** | 10 min | `poll_campaigns()` | Polls `GET /api/campaigns/mine`, stores new invitations, detects server-side status changes |
| **Session health** | 30 min | `check_sessions()` | Launches headless browser per platform, checks for auth selectors vs login indicators, reports green/yellow/red status |
| **Metric scraping** | 60s (checks due) | `run_metric_scraping()` | Calls `metric_scraper.scrape_all_posts()`, syncs metrics to server |
| **Profile refresh** | 7 days | `refresh_profiles()` | Re-scrapes stale profiles, syncs to server. AI niche classification removed (user selects manually). |

All tasks store notifications in `local_notification` table. Desktop notifications via `utils/tray.py` (Windows toast).

---

## 8. Current Limitations

### Not Implemented / Stubs
- **Stripe Connect for user payouts**: Code exists (`payments.create_user_stripe_account()`, `payments.process_payout()`), but `stripe_account_id` is always `None` on users. Payouts in test mode are auto-marked as `paid` without real money transfer.
- **Content screening**: Auto-approves all campaigns (`screening_status = "approved"` on creation). `ContentScreeningLog` model exists but AI screening during wizard is keyword-based only, not enforced as a gate.
- **Redis**: Setting exists (`redis_url`) but not used anywhere in the codebase.
- **Subscription tiers (free/pro)**: Not implemented. All users get the same features.
- **Google/OAuth authentication**: Email + password only.
- **Email notifications**: Not implemented.
- **Auto-start on Windows login**: Not implemented.
- **Mobile app**: Not built.
- **Campaign quality gate service**: `campaign_quality.py` referenced in CLAUDE.md but not present in the services directory.

### Known Issues
- **X account locked during posting**: Playwright automation detected by X. Must fix before user onboarding (stealth browser, official API, or alternative method needed).
- **Clicks hardcoded to 0**: Not available via browser scraping. Metric collection for clicks requires official platform APIs.
- **TikTok blocked in India**: Requires VPN. Disabled in `platforms.json`.
- **No test suite**: Verify changes by running against real platforms.
- **Windows-only**: PowerShell for generation, Windows fonts in image generator, Task Scheduler for automation. Windows-derived machine key for encryption.

### Disabled Features (Code Preserved)
- TikTok posting (`enabled: false` in `platforms.json`)
- Instagram posting (`enabled: false` in `platforms.json`)
- `scripts/generate_campaign.ps1` (replaced by `content_generator.py`)
- `scripts/campaign_runner.py` (replaced by `background_agent.py`)

---

## 9. Configuration

| File | What It Controls |
|------|-----------------|
| `config/platforms.json` | Platform enable/disable, URLs, timeouts, proxy, subreddits |
| `config/.env` | Timing params (browse duration, typing delays, post intervals), headless mode, API keys (GEMINI_API_KEY, MISTRAL_API_KEY, GROQ_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, TOGETHER_API_KEY) |
| `config/content-templates.md` | Brand voice, content pillars, emotion-first + value-first principles, platform format rules |
| `config/server_auth.json` | User's JWT token and email (written by login, read by server_client) |
| `server/.env` / `server/.env.example` | Database URL, JWT secret, Stripe keys, admin password, platform cut %, Supabase credentials, server URL |
| `data/local.db` | User-side SQLite database (all local state) |

### Vercel Environment Variables

| Variable | Status |
|----------|--------|
| `DATABASE_URL` | Set -- Supabase transaction pooler |
| `JWT_SECRET_KEY` | Set -- encrypted |
| `ADMIN_PASSWORD` | Set -- encrypted |
| `GEMINI_API_KEY` | Required for AI matching and campaign wizard on server |

### Deployed URLs

- Company dashboard: `https://server-five-omega-23.vercel.app/company/login`
- Admin dashboard: `https://server-five-omega-23.vercel.app/admin/login`
- Swagger docs: `https://server-five-omega-23.vercel.app/docs`
