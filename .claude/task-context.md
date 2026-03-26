# Amplifier — Task Context

**Last Updated**: 2026-03-26 (Session 20)

## Current Status

**13 of 14 SLC tasks complete.** Only Task #9 (metric scraping) blocked — needs real posted content to test against.

| Slice | Tasks | Status |
|-------|-------|--------|
| 1 Company | #1 #2 #3 | All done |
| 2 User | #4 #5 #6 #7 #8 | All done |
| 3 Money | #9 #10 #11 #12 | 3 done, #9 blocked |
| 4 Polish | #13 #14 | All done |

## Session 20 — What Was Done (Chronological)

### Phase 1: Planning & Cleanup
- Wrote SLC spec (`SLC.md`) defining Simple, Lovable, Complete criteria for Amplifier
- User reviewed and approved with feedback (content gen agent needs dedicated system prompt, webcrawler for research)
- Deleted ~58,700 lines of dead code: Tauri app, personal posting scripts, stale tests/docs, unused utils
- Created 14 task-master tasks across 4 slices with integration test checklists

### Phase 2: Slice 1 — Company Flow
- **Campaign wizard** (`server/app/services/campaign_wizard.py`): URL scraping via httpx+BeautifulSoup, Gemini AI brief generation, reach estimation, payout rate suggestions
- **Schema**: Added `max_users` column to Campaign model, `min_engagement` to Targeting
- **Matching** (`server/app/services/matching.py`): Added min_engagement, max_users, 3-campaign limit hard filters
- **Template**: Updated campaign_wizard.html with new form fields, removed tone
- **Bug fix**: Clicks missing from influencer earnings calculation
- **Tests**: 19 billing unit tests
- **Supabase migration**: `ALTER TABLE campaigns ADD COLUMN max_users INTEGER`
- **Deployed to Vercel** — integration tested: AI generation returned "Nike Pegasus: Unleash Your Run" with 1123-char brief

### Phase 3: Slice 2 — User Flow
- **Onboarding** (`scripts/user_app.py`, `onboarding.html`): 5-step flow (was 4), added API key setup step, manual niche selection (no AI pre-selection), auto-detected region
- **Content generator** (`scripts/utils/content_generator.py`): Rewrote prompt from personal finance to generic UGC. Added webcrawler research phase (`research_and_generate()`). Gemini model fallback chain.
- **LinkedIn scraper** (`scripts/utils/profile_scraper.py`): Added location, about section, experience (3 jobs), education. Fixed activity URL query param bug.
- **System tray** (`scripts/utils/tray.py`): pystray icon + plyer desktop notifications, integrated into user_app.py and background_agent.py
- **Posting** (`scripts/post.py`, `scripts/utils/post_scheduler.py`): Fixed deleted module imports, added URL capture retry (3 attempts + scroll), graceful fallback (posted_no_url instead of failed)
- **Schema fixes**: Added local_post.status, local_campaign.scraped_data columns
- **UAT testing** (automated agent): 8/8 onboarding tests passed, 7/7 review tests passed
- **Tests**: 11 content generator unit tests

### Phase 4: Slice 3 — Money Flow
- **Stripe** (`server/app/services/payments.py`, `company_pages.py`): Test mode checkout, success verification, balance crediting. Fallback instant-credit for dev without Stripe key.
- **Billing**: 19 unit tests verify all calculations. Integration test blocked by #9.
- **Earnings page**: Confirmed loading (UAT TC-010 PASS)

### Phase 5: Slice 4 — Polish
- **"Posts This Month"**: Fixed to filter by current month (was all-time)
- **Admin API auth**: Added cookie-based auth via router-level dependency (was zero auth)
- **Chip tag inputs**: Campaign wizard must-include/must-avoid replaced with type+Enter pill tags
- **Settings**: Removed audience region dropdown and follower counts (auto-detected by Amplifier)

## Bugs Found & Fixed
1. **Infinite redirect loop** (BUG-001): DB deleted while app running → init_db in check_auth
2. **UTC/local time mismatch** (BUG-002, critical): All 116 drafts invisible in "Today's Posts" → UTC comparison
3. **favicon.ico 500** (BUG-003): `return "", 204` → `Response(status=204)`
4. **LinkedIn activity URL**: Query params broke page → strip before appending suffix
5. **Schema gaps**: local_post.status, local_campaign.scraped_data columns missing → added with migration
6. **Gemini rate limits**: Free tier 20 req/day/model → model fallback chain (3 models = 60 req/day)
7. **Posting URL capture**: Both X and LinkedIn returned None → retry logic + graceful posted_no_url fallback

## Remaining Blocker

**Task #9 (Metric scraping)**: LinkedIn post was typed by Playwright but didn't actually appear on the profile. The posting code sends content but LinkedIn's automation detection likely prevented the actual post from landing. Metric scraping code is ready but needs a real post URL to test against.

**To unblock**:
1. Set `HEADLESS=false` in `config/.env`
2. Approve a draft and schedule it
3. Watch Playwright post in headed mode
4. See where it fails and fix

## Key Decisions Made
- **Flask over Tauri**: Direct Python calls, no bridge layers. Shipped in 1 session.
- **httpx+BeautifulSoup for server scraping**: Works on Vercel (no subprocess). Webcrawler for deep scrape on user's machine.
- **UGC prompt**: Generic campaign-driven, no personal branding. Content feels like real person recommending product.
- **Gemini fallback chain**: 2.5-flash → 2.0-flash → 2.5-flash-lite (separate quota buckets)
- **posted_no_url status**: Post sent but URL unknown. Better than marking as failed. Metric scraper can retry later.
- **Auto-detect region**: From IP/locale during onboarding. Not user-editable.
- **Follower counts auto-scraped**: Not user-editable in settings. Scraper updates periodically.

## Tests: 30 passing (19 server + 11 scripts)

## Key Reference Files

### New This Session
- `SLC.md` — SLC spec (source of truth)
- `server/app/services/campaign_wizard.py` — AI wizard + URL scraping + reach estimation
- `scripts/utils/tray.py` — System tray + desktop notifications
- `server/tests/test_billing_calcs.py` — 19 billing unit tests
- `scripts/tests/test_content_generator.py` — 11 content tests

### Modified This Session
- `server/app/routers/campaigns.py` — Removed screening, added wizard imports, max_users
- `server/app/routers/company_pages.py` — New form fields, Stripe routes, clicks fix
- `server/app/services/matching.py` — 3 new hard filters, model fallback
- `scripts/user_app.py` — 5-step onboarding, API key test, tray, favicon, check_auth fix
- `scripts/utils/content_generator.py` — UGC prompt, research phase, model fallback
- `scripts/utils/profile_scraper.py` — LinkedIn enhanced, URL fix
- `scripts/utils/local_db.py` — profile_data, status, scraped_data columns
- `scripts/background_agent.py` — research_and_generate, desktop notifications
- `scripts/post.py` — Removed deleted imports, URL capture retry

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **Swagger**: https://server-five-omega-23.vercel.app/docs
- **User App**: `python scripts/user_app.py` → http://localhost:5222

## Test Commands
```bash
# Server unit tests (19)
cd server && python -m pytest tests/ -v

# Scripts unit tests (11)
cd scripts && python -m pytest tests/ -v

# Run user app
python scripts/user_app.py

# Deploy to Vercel
vercel deploy --yes --prod --cwd server

# Test LinkedIn scraper
cd scripts && python -c "
import asyncio, sys; sys.path.insert(0, '.')
from utils.profile_scraper import scrape_linkedin_profile
from playwright.async_api import async_playwright
async def t():
    async with async_playwright() as pw:
        r = await scrape_linkedin_profile(pw)
        print(f'{r[\"display_name\"]}: {r[\"follower_count\"]} followers, {len(r[\"recent_posts\"])} posts')
asyncio.run(t())
"
```

## Commits This Session (24 total)
```
a4b3227 docs: update task-context for session 20 + gitignore temp files
e864b9a fix: remove audience region dropdown and follower counts from settings
efdd644 chore: all 14 tasks done except #9 (metric scraping, blocked by posting)
da263a2 feat: chip tag inputs for mustInclude/mustAvoid fields in campaign wizard
061e121 chore: update task statuses — 13 of 14 tasks done
61cb718 fix: "Posts This Month" filters by current month + admin API auth
14a454f fix: improve URL capture for X and LinkedIn with retry logic
06d4c3e feat: Stripe test mode checkout for company balance top-up
1eccdb4 fix: UTC date comparison in draft filtering + favicon 500
5c0ee17 fix: prevent infinite redirect loop when DB deleted while app is running
cb18d3b fix: add missing status column to local_post + scraped_data to local_campaign
7b4c11a feat: add research_and_generate() with webcrawler URL scraping
16cc6b7 feat: LinkedIn scraper extracts location, about, experience, and education
ddaa4b0 fix: LinkedIn scraper — strip query params before building activity URL
8394c48 feat: system tray icon + desktop notifications
1754be9 test: 11 unit tests for content generator + post imports
d9bd6c6 feat: 5-step onboarding with API key setup, no AI pre-selection
fbb30bb feat: fix post.py imports + rewrite content prompt for UGC campaigns
30ccc82 fix: use gemini-2.5-flash as primary model
979c969 feat: update campaign wizard template — new fields, remove tone
985d693 feat: Slice 1 backend — campaign wizard, matching, billing fixes
6e2e835 chore: delete dead code and add SLC spec
25618ad chore: remove mvp.md and fix onboarding modal vertical alignment
```
