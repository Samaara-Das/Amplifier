# Amplifier MVP Spec

## Context

Amplifier pivoted from a personal posting tool to a **user-facing campaign platform**. Companies create campaigns, users install the Amplifier app, connect their social media accounts, and earn money by posting campaign content. The core system (server, user app, posting engine) is already built but needs critical fixes, a new content generation approach, and polish before it's usable as an MVP.

### Key Architecture Decisions (Confirmed)
- **Content generation (text)**: Free AI APIs with fallback chain: Gemini → Mistral → Groq → Cerebras → SambaNova → Cloudflare → OpenRouter. Replaces Claude CLI + PowerShell. All have refreshing daily/monthly limits — users never run out.
- **Content generation (images)**: Free AI APIs with fallback chain: Gemini (500+ img/day) → Cloudflare Workers AI (SDXL/FLUX) → Pollinations AI (free, no signup) → PIL branded templates (last resort only).
- **Social media posting**: Current Playwright code (E2E tested). Post-MVP: migrate to Browser Use.
- **Metric collection**: Hybrid — official APIs for X + Reddit (free, easy), Browser Use + Gemini for LinkedIn + Facebook (API approval takes weeks).
- **Matching**: Uses ALL existing fields (required_platforms, min_followers, niche_tags) PLUS new fields (audience_region, categories). Region = where user's AUDIENCE is (not where user is).
- **Database**: PostgreSQL on Supabase (free tier). Replaces ephemeral Vercel SQLite.
- **Platforms (MVP)**: X, LinkedIn, Facebook, Reddit. TikTok/Instagram code preserved but disabled.
- **Distribution**: .exe installer via PyInstaller + Inno Setup.
- **UI**: Clean and functional polish (not full redesign).

---

## MVP Definition — "Done" Means This Works

One complete cycle, end to end:

```
Company registers on web dashboard
  → Creates campaign (brief, budget, payout rules, targeting by region + category)
  → Activates campaign
User installs .exe
  → Onboarding: register, connect platforms (OAuth for X/Reddit, browser login for LinkedIn/Facebook), set audience region + categories
  → Dashboard shows matched campaigns
  → Content auto-generated via Gemini free API (text + image)
  → User reviews, EDITS (text, hashtags, image), and approves in dashboard
  → App posts to X/LinkedIn/Facebook/Reddit via Playwright
  → App collects metrics via APIs (X, Reddit) and Browser Use (LinkedIn, Facebook)
  → Server calculates earnings from metrics
  → User sees earnings in dashboard
  → Company sees engagement stats in their dashboard
```

---

## What's IN (MVP)

| Feature | Status | Work Needed |
|---------|--------|-------------|
| 4-platform posting (X, LinkedIn, Facebook, Reddit) | Built, E2E tested | Disable TikTok/Instagram in config |
| Content generation via free APIs | **NEW** | Build Python module (replaces PowerShell + Claude CLI) |
| Image generation | Partially built | Add Gemini image gen + keep existing PIL templates |
| Campaign matching (region + categories) | Partially built | Update models + matching algorithm |
| Metric collection — X + Reddit via APIs | **NEW** | Register developer apps, implement OAuth + API calls |
| Metric collection — LinkedIn + Facebook via Browser Use | **NEW** | Replace hardcoded selectors with AI-driven extraction |
| Billing/earnings calculation | Built | No changes |
| Company dashboard (6 pages) | Built | Add region + category targeting fields |
| Admin dashboard (6 pages) | Built | No changes |
| User dashboard (5 tabs) | Built | UI polish (clean + functional) |
| .exe installer | Scaffolded | Fix Playwright install, test, improve GUI |
| Onboarding | Built (CLI) | Add audience_region, categories, OAuth for X/Reddit |
| Human behavior emulation | Built | No changes |
| Auto-engagement (likes/reposts) | Built | No changes |
| Server on Supabase PostgreSQL | Not started | Set up Supabase, migrate, redeploy |

## What's OUT (Post-MVP)

- TikTok posting (needs VPN, code preserved)
- Instagram posting (complex dialog flow, code preserved)
- Stripe payments (manual payouts for MVP)
- Background jobs / Redis (admin triggers billing/trust checks manually)
- Browser Use migration for posting (Task 31)
- LinkedIn/Facebook official API migration (when developer apps get approved)
- Additional free AI APIs for text + image generation (expand fallback chain further)
- Website-to-API tool (Firecrawl/Apify) as insurance if free APIs get shut down or go paid — scrape web UIs as fallback
- AI video generation
- Email notifications
- Account warmup
- Newsletter/article generation
- Content A/B testing
- Auto-update mechanism

---

## Company Journey (MVP)

1. Go to `https://<vercel-url>/company/login`
2. Click "Register" → enter company name, email, password
3. Arrives at campaigns list (empty)
4. Click "Create Campaign" → fill form:
   - Title, brief (instructions for content creators)
   - Content guidance (tone, must-include phrases, forbidden phrases)
   - Payout rules: rate per 1K impressions, per like, per repost, per click
   - Targeting: required platforms, min followers, **target regions**, **categories**
   - Budget, start date, end date
5. Campaign created in "draft" status → click "Activate"
6. Monitor campaign: see user count, posts, impressions, engagement, budget remaining
7. **See which influencers are posting**: campaign detail page shows list of assigned users with their platform handles, post URLs, and engagement stats per user
8. Billing page shows budget allocation history
9. Settings page to edit company name/email

**What's already built**: Most of the above. Company dashboard is functional.

**Changes needed**:
- Add target_regions and categories fields to the campaign creation form
- Add influencer list to campaign detail page (data exists in campaign_assignments + posts tables, just needs a UI view)

---

## User Journey (MVP)

### Installation
1. Download `Amplifier-Setup.exe` from download page
2. Run installer → installs to Program Files
3. Installer runs `playwright install chromium` automatically (CURRENTLY BROKEN — must fix)
4. Desktop shortcut created

### First Launch / Onboarding
1. User double-clicks Amplifier shortcut
2. App detects not logged in → shows onboarding in dashboard (not CLI)
3. **Step 1 (Auth)**: Register with email + password (or login)
4. **Step 2 (Platforms)**: Connect social media accounts:
   - **X**: OAuth flow — user authorizes Amplifier app → gets read/write access + metrics
   - **Reddit**: OAuth flow — user authorizes Amplifier app → gets read/write access + metrics
   - **LinkedIn**: Manual browser login (OAuth API approval pending) → session saved in Playwright profile
   - **Facebook**: Manual browser login (OAuth API approval pending) → session saved in Playwright profile
   - Enter username/handle for each connected platform
5. **Step 3 (Profile)**:
   - Select audience region: "Where is most of your audience?" (US, UK, India, EU, Global, etc.)
   - Select categories: checkboxes (beauty, fashion, tech, finance, fitness, gaming, food, travel, etc.)
   - Enter follower counts per connected platform
6. **Step 4 (Mode)**: Choose operating mode
   - Semi-auto (default, recommended): content generated automatically, you review before posting. 2.0x payout.
   - Full-auto: content generated and posted automatically. 1.5x payout.
   - Manual: you write your own content. 2.0x payout.
7. **Step 5 (API Key)**: Get a free Gemini API key
   - Link to ai.google.dev → user copies key → pastes into app
   - Stored in local `.env` file
   - Required for content generation to work
8. **Step 6 (Verify)**: Dashboard shows profile summary, confirms server connection

### Daily Use
1. Dashboard opens in browser (localhost:5222)
2. **Campaigns tab**: Shows matched campaigns with brief, payout rules, status
3. Campaign runner polls server every 10 min in background
4. When new campaign matched:
   - Content auto-generated via Gemini API (text + image per platform)
   - Status changes to "content_generated"
   - User sees "Review & Approve" button
5. User reviews content → can **edit** text, hashtags, and image per platform → approves or skips
6. Approved (and optionally edited) content posted to connected platforms (30-90s between platforms, human emulation active)
7. **Posts tab**: Shows post history with URLs, platform, engagement metrics
8. **Earnings tab**: Shows total earned, pending, available balance, paid out, breakdown by campaign
9. **Settings tab**: Change mode, poll interval, see connected platforms

### Metric Collection (Background)
- After posting, the app collects engagement metrics at T+1h, 6h, 24h, 72h
- **X**: Uses X API v2 to read tweet metrics (impressions, likes, retweets, replies). OAuth token from onboarding.
- **Reddit**: Uses Reddit API to read post score, comments, upvotes. OAuth token from onboarding.
- **LinkedIn**: Uses Browser Use + Gemini to visit post URL and extract metrics (likes, comments, reposts). Falls back to old Playwright selectors if AI fails.
- **Facebook**: Uses Browser Use + Gemini to visit post URL and extract metrics (reactions, comments, shares). Falls back to old Playwright selectors if AI fails.
- T+72h collection is marked "final" → triggers billing calculation on server
- User sees updated metrics in Posts tab and earnings in Earnings tab

---

## Implementation Plan (Ordered by Priority)

### Phase 1: Critical Fixes (must do first — app won't run without these)

**1.1 Fix missing dependencies**
- File: `requirements.txt`
- Add: `httpx>=0.28.0` (server_client.py imports it, crashes without it)
- Add: `google-genai` (new content generation)
- Add: `groq` (fallback content generation)
- Add: `mistralai` (fallback content generation)
- Add: `browser-use` (AI-powered metric scraping for LinkedIn/Facebook)
- Add: `langchain-google-genai` (Browser Use + Gemini integration)
- Add: `tweepy` or `httpx` (X API v2 client — can use httpx directly)
- Add: `praw` (Reddit API client)
- Keep moviepy out (not needed for MVP — no TikTok video)

**1.2 Make server URL configurable**
- File: `scripts/utils/server_client.py` (line 20)
- Currently hardcoded to `http://localhost:8000`
- Read `CAMPAIGN_SERVER_URL` from `.env` (already partially done but not defaulting to Vercel URL)
- Default should be the deployed Vercel URL
- File: `config/.env` — add `CAMPAIGN_SERVER_URL=https://server-five-omega-23.vercel.app`

**1.3 Fix JWT secret**
- File: `server/app/core/config.py` (line 14)
- Currently: `"change-me-to-a-random-secret"`
- Set via Vercel env var (generate random 64-char string)
- Also set `ADMIN_PASSWORD` env var on Vercel (not "admin")

**1.4 Disable TikTok and Instagram**
- File: `config/platforms.json`
- Set `"enabled": false` for tiktok and instagram
- Keep all code intact — just skip them during posting

### Phase 2: Supabase PostgreSQL Setup

**2.1 Create Supabase project**
- Create free project on supabase.com
- Get connection string: `postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres`

**2.2 Update server for PostgreSQL**
- File: `server/app/core/config.py` — `DATABASE_URL` env var already supported
- File: `server/app/core/database.py` — already handles PostgreSQL via asyncpg
- Handle Supabase SSL requirement (add `?sslmode=require` to connection string)
- Run `init_tables()` once to create all 8 tables

**2.3 Set Vercel env vars**
- `DATABASE_URL` = Supabase connection string
- `JWT_SECRET_KEY` = random 64-char string
- `ADMIN_PASSWORD` = strong password
- Redeploy to Vercel

**2.4 Verify**
- Test registration, campaign creation, and data persistence across cold starts
- Confirm data survives Vercel redeploy

### Phase 3: Content Generation Module (biggest new code)

**3.1 Create `scripts/utils/content_generator.py`**

New Python module that replaces `scripts/generate_campaign.ps1`. Structure:

```python
class ContentGenerator:
    """Generate campaign content using free AI APIs with fallback chain."""

    def __init__(self):
        # Initialize available providers based on API keys in .env
        # Priority: Gemini (text + images) → Mistral (text) → Groq (text)

    async def generate(self, campaign: dict) -> dict:
        """Generate per-platform content from campaign brief.

        Returns: {
            "x": "tweet text (max 280)",
            "linkedin": "post text (800-1300 chars)",
            "facebook": "post text (200-800 chars)",
            "reddit": {"title": "...", "body": "..."},
            "image_prompt": "description for image generation"
        }
        """
        for provider in self.providers:
            try:
                return await provider.generate(prompt, campaign)
            except (RateLimitError, APIError):
                continue
        raise AllProvidersExhaustedError()

    async def generate_image(self, prompt: str, platform: str) -> str:
        """Generate image using Gemini or fall back to PIL templates.
        Returns path to generated image file.
        """
```

**Text generation providers (MVP fallback chain):**
1. **GeminiProvider** — `google-genai` SDK, model `gemini-2.5-flash-lite` (free: 1,000 RPD, refreshes daily)
   - Also generates images — primary image provider
   - Requires API key (free at ai.google.dev, no credit card)
2. **MistralProvider** — `mistralai` SDK, model `mistral-small-latest` (free: 1B tokens/month, refreshes monthly)
   - Text only
   - Requires API key (free, phone verification only)
3. **GroqProvider** — `groq` SDK, model `llama-3.3-70b` (free: ~14,400 RPD, refreshes daily)
   - Text only
   - Requires API key (free, no credit card)
4. **CloudflareProvider** — Cloudflare Workers AI (free: 10,000 neurons/day, refreshes daily)
   - Text + image (SDXL, FLUX models)
   - Requires Cloudflare account (free, no credit card)

**Image generation providers (MVP fallback chain):**
1. **Gemini** — 500+ images/day free, high quality, native API
2. **Cloudflare Workers AI** — SDXL/FLUX models, ~10-20 images/day free
3. **Pollinations AI** — Free forever, no signup needed, URL-based API (`pollinations.ai/p/{prompt}`)
4. **PIL templates** — Existing `scripts/utils/image_generator.py`, absolute last resort only

**Post-MVP text providers (to expand the chain):**
- Cerebras (1M tokens/day free), SambaNova (200K tokens/day), OpenRouter (27+ free models), GitHub Models (GPT-4o access), Cohere (1K requests/month)

**Post-MVP image providers (to expand the chain):**
- AI Horde (unlimited, community-powered, slow), Freepik Mystic (20 images/day), Leonardo AI (150 tokens/day)

All refreshing limits (daily/monthly) mean users never permanently run out of credits.

**Prompt template:**
```
Generate social media content for a brand campaign.

CAMPAIGN BRIEF:
Title: {title}
Brief: {brief}
Content Guidance: {content_guidance}
Assets/Links: {assets}

Generate content for these platforms: {enabled_platforms}

OUTPUT FORMAT: JSON object with keys for each platform.
- x: Tweet (max 280 chars, punchy, native to X)
- linkedin: Post (800-1300 chars, professional, line breaks, 3-5 hashtags)
- facebook: Post (200-800 chars, conversational, engagement-driving)
- reddit: Object with "title" (60-120 chars) and "body" (500-1500 chars, no hashtags, value-first)

RULES:
- Each platform version must feel native to that platform
- Content must promote the campaign naturally — not feel like an ad
- Include relevant hashtags where appropriate (not Reddit)
- Be authentic and conversational, not salesy
```

**3.2 Update `scripts/campaign_runner.py`**
- Replace `_generate_content()` method (currently calls PowerShell subprocess)
- Import and use new `ContentGenerator` class
- Remove PowerShell dependency entirely for campaign flow
- Keep generate_campaign.ps1 in repo (not deleted, just unused for campaigns)

**3.3 API key management**
- File: `config/.env` — add optional API key fields:
  ```
  GEMINI_API_KEY=        # Free at ai.google.dev
  MISTRAL_API_KEY=       # Free at console.mistral.ai (optional)
  GROQ_API_KEY=          # Free at console.groq.com (optional)
  ```
- Onboarding step: Prompt user to get a free Gemini API key
  - Link to ai.google.dev
  - Paste key → saved to .env
  - Required — content generation needs at least one API key
- ContentGenerator auto-detects which keys are available and builds provider chain

### Phase 4: Matching Updates (region + categories)

**4.1 Update User model**
- File: `server/app/models/user.py`
- Add: `audience_region = Column(String(50), default="global")` — values: "us", "uk", "india", "eu", "global", etc.
- Rename concept: `niche_tags` → keep the column name but treat as "categories" in UI
  - Values: beauty, fashion, tech, finance, fitness, gaming, food, travel, education, lifestyle, etc.

**4.2 Update Campaign targeting**
- File: `server/app/models/campaign.py`
- The `targeting` JSON column already exists. Add to its schema:
  ```json
  {
    "required_platforms": ["x", "linkedin"],
    "min_followers": {"x": 100},
    "niche_tags": ["beauty", "fashion"],
    "target_regions": ["us", "uk"]
  }
  ```
- No model change needed — targeting is already a JSON column. Just use the new fields.

**4.3 Update matching algorithm**
- File: `server/app/services/matching.py`
- Add hard filter: if campaign has `target_regions`, user's `audience_region` must be in the list (or user is "global")
- Categories matching already works via `niche_tags` overlap scoring

**4.4 Update company dashboard campaign creation form**
- File: `server/app/routers/company_pages.py` (create campaign route)
- File: `server/app/templates/company/create.html`
- Add: target regions multi-select (US, UK, India, EU, Global, etc.)
- Add: categories multi-select (beauty, fashion, tech, finance, etc.)
- These get stored in the campaign's `targeting` JSON

**4.5 Update user onboarding**
- File: `scripts/onboarding.py`
- Add audience region prompt: "Where is most of your audience based?"
- Update categories prompt with expanded list
- Send to server via `update_profile()` which already calls `PATCH /api/users/me`

**4.6 Update server user profile endpoint**
- File: `server/app/routers/users.py`
- Accept `audience_region` in profile update
- File: `server/app/schemas/` — update UserUpdate schema

### Phase 5: Metric Collection — Hybrid Approach

**Why hybrid?** Official APIs are more reliable and faster, but LinkedIn and Facebook require lengthy app approval processes. So we use APIs where easy (X, Reddit) and Browser Use where APIs aren't available yet (LinkedIn, Facebook).

**5.1 Register developer apps**

**X (Twitter) API:**
- Register at developer.twitter.com
- Create app → get API key + secret
- OAuth 2.0 PKCE flow for user authorization
- Scopes needed: `tweet.read`, `users.read`
- Free Basic tier: read tweet metrics (impressions, likes, retweets, replies)
- Store user's OAuth token locally after onboarding authorization

**Reddit API:**
- Register at reddit.com/prefs/apps
- Create "script" or "installed app" type
- OAuth2 flow for user authorization
- Scopes needed: `read`, `identity`
- Free, no rate limit issues for our volume
- Store user's OAuth token locally after onboarding authorization

**5.2 Create `scripts/utils/metric_collector.py`**

New unified module that handles all metric collection:

```python
class MetricCollector:
    """Collect post metrics using the best available method per platform."""

    async def collect(self, post_url: str, platform: str) -> dict:
        """Collect metrics for a post. Routes to the right method per platform.

        Returns: {"impressions": int, "likes": int, "reposts": int, "comments": int}
        """
        if platform == "x":
            return await self._collect_via_x_api(post_url)
        elif platform == "reddit":
            return await self._collect_via_reddit_api(post_url)
        elif platform in ("linkedin", "facebook"):
            return await self._collect_via_browser_use(post_url, platform)

    async def _collect_via_x_api(self, post_url: str) -> dict:
        """Use X API v2 to read tweet metrics. Fast, reliable, exact numbers."""
        # Extract tweet ID from URL
        # GET /2/tweets/{id}?tweet.fields=public_metrics
        # Returns: impression_count, like_count, retweet_count, reply_count

    async def _collect_via_reddit_api(self, post_url: str) -> dict:
        """Use Reddit API to read post metrics. Fast, reliable."""
        # Extract post ID from URL
        # GET /api/info?id=t3_{post_id}
        # Returns: score (upvotes), num_comments

    async def _collect_via_browser_use(self, post_url: str, platform: str) -> dict:
        """Use Browser Use + Gemini to extract metrics from page. Self-healing."""
        # Agent visits post URL, extracts visible engagement numbers
        # Falls back to old Playwright selectors if AI fails
```

**5.3 Keep existing scheduling logic**
- Keep the scraping schedule from `metric_scraper.py`: T+1h, 6h, 24h, 72h
- Keep `_should_scrape()` function and timing logic
- Keep local DB integration (add_metric, mark_metrics_reported)
- Keep server sync logic (report_metrics)
- Replace the 6 platform-specific scraping functions with `MetricCollector`

**5.4 OAuth token storage**
- X and Reddit OAuth tokens stored in `config/oauth_tokens.json`
- Tokens acquired during onboarding (user authorizes the app)
- Token refresh handled automatically (X uses refresh tokens, Reddit tokens expire in 1h but can be refreshed)

**5.5 Fallback chain**
- X: API → old Playwright selectors → skip (log warning)
- Reddit: API → old Playwright selectors → skip (log warning)
- LinkedIn: Browser Use → old Playwright selectors → skip (log warning)
- Facebook: Browser Use → old Playwright selectors → skip (log warning)
- Old platform-specific scraping functions preserved as fallback (not deleted)

### Phase 6: Dashboard UI Polish

**6.1 Clean up user dashboard**
- File: `scripts/campaign_dashboard.py`
- Improvements (clean + functional, not redesign):
  - Better typography and spacing
  - Consistent padding/margins
  - Clearer status badges and colors
  - Better table formatting (earnings, posts)
  - Campaign cards instead of raw table rows
  - Action buttons (approve/skip) more prominent
  - Trust score bar more visible
  - Responsive layout for different screen sizes
  - Loading states for async operations
  - Success/error notifications after actions
  - Modern look (clean fonts, subtle shadows, proper color hierarchy)

**6.2 Add post editing flow**
- Before approving, user can edit generated content per platform:
  - Edit text (textarea per platform)
  - Edit hashtags
  - Replace or remove generated image
  - Preview how the post will look on each platform
- Edited content saved to local DB, used during posting
- If user edits content, payout_multiplier stays at 2.0x (user_customized mode)

**6.3 Fix dashboard backend routes**
- Verify all action routes work: approve, skip, generate, poll, edit
- Ensure content preview shows generated text + image per platform

**6.4 Company dashboard — influencer visibility**
- File: `server/app/routers/company_pages.py` (campaign detail route)
- File: `server/app/templates/company/detail.html`
- Add influencer list to campaign detail page:
  - Show each assigned user's platform handles (from user.platforms JSON)
  - Show their post URLs (from posts table)
  - Show per-user engagement stats (impressions, likes, reposts)
  - Show assignment status (assigned, content_generated, posted, paid)
- Data already exists in campaign_assignments + posts + metrics tables — just needs a UI view

### Phase 7: Installer Fixes

**7.1 Fix Playwright browser installation**
- File: `installer.iss` (line 40)
- Current: tries `--install-browsers` (invalid flag)
- Fix: run `playwright install chromium` as post-install step

**7.2 Fix PyInstaller spec**
- File: `amplifier.spec`
- Add missing hidden imports: `httpx`, `google.genai`, `groq`, `mistralai`, `browser_use`, `praw`
- Remove moviepy (not needed for MVP — no TikTok video)
- Ensure .env.example is bundled

**7.3 Improve installer appearance**
- File: `installer.iss`
- Add app icon
- Don't delete user data on uninstall (remove lines 48-50 that delete data/, logs/, profiles/)

**7.4 Build and test**
- Run PyInstaller: `pyinstaller amplifier.spec`
- Run Inno Setup to create installer
- Test on clean Windows machine (or VM)

### Phase 8: Integration Testing

**8.1 Server-side setup**
- Create test company account on Vercel-deployed server
- Create test campaign with:
  - Title: "Test Campaign"
  - Brief: "Share a helpful tip related to our product"
  - Payout rules: $1 per 1K impressions, $0.05 per like
  - Targeting: US region, finance category, 0 min followers
  - Budget: $100
  - Activate campaign

**8.2 User-side test**
- Install .exe on test machine
- Run onboarding: register, connect at least 1 platform (X recommended — has OAuth + API metrics)
- Set audience_region: US, categories: finance
- Verify campaign appears in dashboard
- Let content generate via Gemini
- Review content in dashboard
- Edit text/hashtags on one platform to test edit flow
- Approve and post
- Verify post appears on platform
- Wait for metric collection (or trigger manually)
- Verify earnings appear in dashboard

**8.3 Company-side verification**
- Log into company dashboard
- Verify: user count increased, post appears, metrics show up
- Verify: campaign detail page shows which influencer(s) posted with their handles and engagement stats

---

## Files to Modify (Complete List)

### New Files
| File | Purpose |
|------|---------|
| `scripts/utils/content_generator.py` | Free API content generation with fallback chain |
| `scripts/utils/metric_collector.py` | Hybrid metric collection (APIs for X/Reddit, Browser Use for LinkedIn/Facebook) |

### Modified Files
| File | Changes |
|------|---------|
| `requirements.txt` | Add httpx, google-genai, groq, mistralai, browser-use, langchain-google-genai, praw |
| `config/platforms.json` | Disable TikTok + Instagram |
| `config/.env` | Add CAMPAIGN_SERVER_URL, GEMINI_API_KEY, X/Reddit API keys |
| `scripts/campaign_runner.py` | Use ContentGenerator instead of PowerShell |
| `scripts/onboarding.py` | Add audience_region, categories, OAuth for X/Reddit, Gemini API key |
| `scripts/campaign_dashboard.py` | UI polish (spacing, typography, cards, actions) |
| `scripts/utils/server_client.py` | Configurable server URL default |
| `scripts/utils/metric_scraper.py` | Use MetricCollector instead of platform-specific selectors |
| `server/app/models/user.py` | Add audience_region column |
| `server/app/services/matching.py` | Add region filter |
| `server/app/routers/users.py` | Accept audience_region in profile update |
| `server/app/routers/company_pages.py` | Add region + categories to campaign form |
| `server/app/templates/company/create.html` | Add targeting fields |
| `amplifier.spec` | Fix hidden imports, add new deps, remove moviepy |
| `installer.iss` | Fix Playwright install, fix uninstall data loss, improve GUI |

### Vercel Environment Variables to Set
| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `JWT_SECRET_KEY` | Random 64-char string |
| `ADMIN_PASSWORD` | Strong password (not "admin") |

### Files NOT Modified (preserved as-is)
- `scripts/post.py` — Current Playwright posting (works, E2E tested)
- `scripts/utils/human_behavior.py` — Human emulation (works)
- `scripts/utils/image_generator.py` — PIL image generation (works, used as fallback)
- `scripts/utils/local_db.py` — Local SQLite (works)
- `scripts/utils/draft_manager.py` — Draft lifecycle (works)
- `scripts/generate_campaign.ps1` — Preserved but unused in MVP
- `scripts/login_setup.py` — Platform login helper (works)
- `server/app/services/billing.py` — Billing engine (works)
- `server/app/services/trust.py` — Trust/fraud (works)
- `server/app/routers/admin_pages.py` — Admin dashboard (works)
- All TikTok/Instagram code in post.py, image_generator.py, metric_scraper.py (preserved, just skipped)

---

## Verification Checklist

- [ ] Server running on Vercel with Supabase PostgreSQL (data persists across deploys)
- [ ] Company can register, create campaign with region + category targeting, activate it
- [ ] User can install .exe, complete onboarding, connect at least 1 platform
- [ ] X OAuth flow works (user authorizes, token saved)
- [ ] Reddit OAuth flow works (user authorizes, token saved)
- [ ] LinkedIn/Facebook browser login works (session saved in profile)
- [ ] Campaign matching works with region + category filters (user sees matched campaign in dashboard)
- [ ] Content generated via Gemini free API (text + image)
- [ ] Fallback works: if Gemini fails, Mistral/Groq generates text; Cloudflare/Pollinations generates image
- [ ] User can review, edit (text, hashtags, image), and approve content in dashboard
- [ ] Approved content posts to platform via Playwright
- [ ] X metrics collected via API (impressions, likes, retweets)
- [ ] Reddit metrics collected via API (score, comments)
- [ ] LinkedIn metrics collected via Browser Use (likes, comments, reposts)
- [ ] Facebook metrics collected via Browser Use (reactions, comments, shares)
- [ ] Earnings calculated and visible in user dashboard
- [ ] Company sees engagement stats in their dashboard
- [ ] Company can see which influencers posted, their handles, post URLs, and per-user engagement
- [ ] Admin dashboard shows users, campaigns, stats
- [ ] Installer works on clean Windows machine
- [ ] No crashes, no missing dependencies
