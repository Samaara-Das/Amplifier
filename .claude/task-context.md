# Amplifier — Task Context

**Last Updated**: 2026-03-25 (Session 19)

## Current Task
- **Branch: `flask-user-app`** — Rebuilt user app as Flask web app (replaced buggy Tauri desktop app)
- All 8 pages built and working: Login, Dashboard, Onboarding, Campaigns, Campaign Detail, Posts, Earnings, Settings
- Daily content generation system implemented (1 post/platform/campaign/day)
- Background agent running: polls campaigns, generates content, schedules posts, scrapes metrics
- **Currently testing**: approved drafts being posted by background agent (6 posts scheduled for today)
- **Known bugs**: Niche tag checkboxes don't toggle on onboarding page (low priority)

## Critical Decision: Tauri → Flask (Session 19)

The Tauri desktop app had fundamental state management bugs (auth leaks, shared platform profiles, stuck UI states) caused by its 3-layer architecture (JS → Rust → Python sidecar). After discovering multiple bugs during UAT, decided to **replace Tauri with a direct Flask web app** that calls Python functions with zero bridge layers.

**Why Flask won**: All backend code (posting, scraping, AI generation, server API) is Python. Flask calls it directly. No Rust, no JSON-RPC, no sidecar. Single process, single language, testable.

**The Tauri code is preserved on `main` branch** — `flask-user-app` branch has the new Flask app.

## Flask User App — Architecture

```
scripts/user_app.py              # Flask app, port 5222, ~800 lines
scripts/templates/user/          # 9 Jinja2 templates
  base.html                      # Sidebar layout (matches Tauri theme)
  login.html                     # Standalone register/login
  onboarding.html                # 4-step wizard
  dashboard.html                 # Stats, platform health, activity
  campaigns.html                 # Invitations + Active + Completed tabs
  campaign_detail.html           # Daily drafts: approve/reject/edit per platform
  posts.html                     # All posts with metrics table
  earnings.html                  # Balance, breakdown, withdraw
  settings.html                  # Mode, platforms, profile, API key
scripts/static/css/user.css      # Copied from Tauri (blue/white theme)
scripts/static/js/user.js        # Status polling, browser notifications
```

**Direct Python calls** (no bridge):
- `server_client.py` → Server API (register, login, poll, accept, reject, report)
- `local_db.py` → Local SQLite (campaigns, drafts, posts, metrics, settings)
- `content_generator.py` → Gemini AI content generation
- `profile_scraper.py` → Playwright profile scraping
- `background_agent.py` → Daemon thread for automation

## Session 19 — What Was Done (Chronological)

### Phase 1: UAT Testing of Tauri App
- Tested 12 core user flows against server API + sidecar handlers
- Found 10 bugs in scrapers, selectors, and state management
- Fixed: double browser on connect, Reddit headless blocked, LinkedIn/Facebook/X selector issues
- Verified: Register, login, invitations, accept/reject, content generation, earnings, withdraw all work via API

### Phase 2: Decision to Replace Tauri
- User found more Tauri bugs: stale auth, shared profiles across users, stuck buttons
- Diagnosed root cause: 3-layer architecture (JS → Rust → Python) with no state reset boundaries
- Decided: Flask web app, not rebuild Tauri. Ship today, not rebuild for 2 weeks.

### Phase 3: Built Flask User App (5 phases)
1. **Skeleton + Auth** — base.html, login.html, dashboard.html, before_request auth guard
2. **Onboarding** — 4-step wizard (connect platforms, profile/niches, mode, summary)
3. **Campaigns + Content Review** — invitations, accept/reject, content generation, per-platform editing
4. **Posts + Earnings + Settings** — all remaining pages with full data
5. **Background Agent** — daemon thread integration, auto content generation

### Phase 4: Scraper Fixes
- **All 4 scrapers now run headless** with stealth flags (navigator.webdriver override)
- Reddit stealth works — no more headed browser window
- LinkedIn: body text parsing fallback (CSS selectors keep breaking). Name extracted from URL slug.
- X: retweet filtering — skips `socialContext="You reposted"`, only counts original posts
- Facebook: bio filters UI noise ("Add Bio", "Edit details")
- Following count now scraped for all 4 platforms (was only X before)
- Removed `clicks` from metric scraping (not available via browser scraping)
- Added impressions/views: X (aria-label), LinkedIn (body text), Reddit (body text), Facebook (video views only)

### Phase 5: Daily Content Generation System
- **Changed from one-time to daily**: 1 unique post per platform per campaign per day
- Background agent generates content every 2 minutes for campaigns without today's drafts
- AI prompt includes `day_number` and previous hooks to avoid repetition
- Drafts stored in `agent_draft` table (not `local_campaign.content`)
- Users approve/reject/edit individual drafts per platform
- Approved drafts → `post_schedule` → background agent posts at scheduled time
- **Removed manual mode** — only semi_auto and full_auto remain

### Phase 6: Posting Pipeline Connection
- **Critical bug found**: approved drafts were NOT being scheduled for posting
- Fix: `_schedule_draft()` inserts into `post_schedule` when draft is approved
- Batch approve also schedules all drafts with 30-min spacing
- Full-auto mode auto-schedules after generation

### Phase 7: Additional Features
- Restore rejected drafts (undo accidental reject)
- Browser notifications (Notification API) when new content is generated
- Auto-scrape + AI niche classification after platform connect
- Scraping blocks Next button on onboarding until complete
- Metric scraping continues while campaign is active (removed 72h cutoff)

## Key Decisions (Session 19)
- **Flask over Tauri** — Direct Python calls, no bridge layers. Ship fast.
- **Daily content generation** — 1 post/platform/campaign/day (not one-time)
- **No manual mode** — Only semi_auto (review before post) and full_auto (auto-post)
- **Stealth headless** — All scrapers run headless with anti-detection flags
- **Body text fallback** — LinkedIn/Reddit scrapers use body text parsing when CSS selectors fail
- **Continuous metric scraping** — No 72h cutoff, scrape while campaign active
- **Draft-based content** — `agent_draft` table replaces `local_campaign.content` for recurring content

## Lessons Learned
1. **Read the product spec before implementing** — Implemented AI niche detection wrong because assumed its purpose instead of reading docs
2. **3-layer architectures multiply bugs** — Tauri (JS→Rust→Python) made every bug 3x harder to debug
3. **CSS selectors are fragile** — LinkedIn changes DOM frequently. Body text parsing is more resilient.
4. **Kill zombie processes** — Flask 500 errors were caused by 20+ old Flask processes on the same port
5. **Stealth flags work** — `navigator.webdriver` override + `AutomationControlled` disable bypasses Reddit's headless detection
6. **Auto-scrape after connect** — Don't make users click extra buttons. Scrape automatically when they close the login browser.
7. **Retweets inflate engagement** — X profile shows reposts as part of the timeline. Must filter by `socialContext` to get accurate engagement rates.

## Pending / Known Issues
- [ ] Niche tag checkboxes don't toggle on onboarding (label/div onclick conflict — partially fixed but needs verification)
- [ ] 6 posts scheduled for today — need to verify they actually post
- [ ] Content generator needs GEMINI_API_KEY in config/.env (load_dotenv added)
- [ ] Gemini free tier rate limits (20 requests/day/model) — may need paid key for production
- [ ] Facebook doesn't expose impressions on personal profiles (only pages)
- [ ] Posts tab shows old campaign_runner posts from testing — may need cleanup

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **Swagger**: https://server-five-omega-23.vercel.app/docs
- **User App**: `python scripts/user_app.py` → http://localhost:5222

## Key Reference Files

### Flask User App (NEW — branch: flask-user-app)
- `scripts/user_app.py` — Flask app (~800 lines, 25+ routes)
- `scripts/templates/user/` — 9 Jinja2 templates
- `scripts/static/css/user.css` — Blue/white theme (from Tauri)
- `scripts/static/js/user.js` — Status polling, notifications

### Backend (unchanged, used by Flask directly)
- `scripts/utils/server_client.py` — Server API (14 functions)
- `scripts/utils/local_db.py` — Local SQLite (13 tables, 30+ functions)
- `scripts/utils/content_generator.py` — Gemini content generation (with daily variation support)
- `scripts/utils/profile_scraper.py` — 4 platform scrapers (all headless with stealth)
- `scripts/utils/metric_scraper.py` — Post metric scraping (continuous, not 72h cutoff)
- `scripts/utils/niche_classifier.py` — AI niche classification
- `scripts/utils/post_scheduler.py` — Region-based scheduling + execution
- `scripts/background_agent.py` — Daemon thread: poll, generate, post, scrape, health check

### Server (deployed on Vercel)
- `server/app/main.py` — 82 routes
- `server/app/services/matching.py` — AI matching (Gemini scoring + hard filters + trust/engagement bonus)
- `server/app/services/billing.py` — Earnings calculation from metrics

## Test Commands
```bash
# Run Flask user app
cd C:/Users/dassa/Work/Auto-Posting-System && python scripts/user_app.py

# Run all tests
python -m pytest tests/ -v

# Deploy to Vercel
vercel deploy --yes --prod --cwd server

# Test scrapers
cd scripts && python -c "
import asyncio, sys; sys.path.insert(0, '.')
from utils.profile_scraper import *
from playwright.async_api import async_playwright
async def t():
    async with async_playwright() as pw:
        for n, s in [('X', scrape_x_profile), ('LI', scrape_linkedin_profile), ('FB', scrape_facebook_profile), ('RD', scrape_reddit_profile)]:
            d = await s(pw); print(f'{n}: {d[\"display_name\"]}, {d[\"follower_count\"]} followers')
asyncio.run(t())
"
```

## Content Generation Pipeline
```
Campaign accepted → status: assigned
  ↓ (background agent, every 2 min)
Daily content generated → 1 draft per platform in agent_draft table
  ↓ (semi_auto: user reviews; full_auto: auto-approved)
Draft approved → inserted into post_schedule with 30-min spacing
  ↓ (background agent, every 60s checks due posts)
Post executed → headless Playwright posts to platform
  ↓ (post_url captured)
local_post created → metric scraping begins
  ↓ (T+1h, 6h, 24h, 72h, then every 24h while campaign active)
Metrics scraped → synced to server → earnings calculated
```
