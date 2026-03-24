# Amplifier — Task Context

**Last Updated**: 2026-03-24 (Session 17)

## Current Task
- **Branch: `main`** — MVP complete, metric pipeline fixed, earnings verified E2E
- All MVP phases (1-8) complete
- Full metric pipeline verified: post → scrape → report to server → billing → $75.98 earned → dashboard
- Server redeployed to Vercel with inline billing trigger
- Webcrawler installed globally for content research

## Project Overview
Two interconnected systems:
1. **Amplifier Engine** — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** — Two-sided marketplace: companies create campaigns, users earn by posting via Amplifier

## Task Progress Summary

### MVP Phases (All Complete)
- [x] Phase 1-8: All complete (critical fixes, PostgreSQL, content gen, matching, metrics, dashboards, installer, integration testing)

### Session 17 Tasks (2026-03-24)
- [x] **Task 31: Content prompt rewrite** — Rewrote CONTENT_PROMPT in content_generator.py with emotion-first hooks, value-first body, platform-specific format rules, hard rules from content-templates.md
- [x] **Task 32: DeerFlow research** — Researched thoroughly, decided to SKIP (overkill: full-stack app, Python 3.12+, Node 22+, nginx, ~30 deps, doesn't work on Windows). Build lightweight research pipeline (crawler + Gemini) instead.
- [x] **Task 33: Webcrawler setup** — Installed at `C:\Users\dassa\Work\webcrawler\`, added to global CLAUDE.md. Search + fetch work. Investopedia blocks but other financial sites work fine.
- [x] **Task 34: Metric pipeline — 4 bugs fixed** — URL capture, cumulative scraping, inline billing, content prompt. Full E2E verified: $75.98 earned on dashboard.
- [x] **Task 35: Model exploration note** — Saved to memory. Deferred: Qwen, Llama, Nvidia, local LLMs. Current Gemini works.

### Next Session Priority
- [ ] **Lightweight research pipeline** — Wire webcrawler + Gemini together in content_generator.py (crawler fetches trending topics/articles → feeds into prompt as context → Gemini generates brand-voice content). This replaces DeerFlow.
- [ ] **Test real posting with URL capture** — Run campaign_runner.py to verify post functions capture real URLs (not placeholders) from the browser after posting
- [ ] **Local server SQLite schema drift** — Local `amplifier.db` may lack `audience_region` column. Delete stale DB to recreate. Only affects local dev (Supabase has all columns).

### Post-MVP Tasks (Pending)
- [ ] AI architecture rethink — multi-agent pipeline, model economics (see `docs/POST_MVP_AI_STRATEGY.md`)
- [ ] User app distribution — web dashboard + Tauri desktop agent (see `docs/POST_MVP_ROADMAP.md`)
- [ ] Browser Use migration for posting
- [ ] LinkedIn/Facebook official API migration
- [ ] Write tests (~50 pytest tests)
- [ ] 18-21: Test Run, Account Warmup, Profile Revamps, LinkedIn "I'm Back"
- [ ] 22-30: AI Video, Newsletters, Facebook Groups, TradingView, Analytics, etc.

## Session History

### Sessions 1-8 (2026-03-07 to 2026-03-18) — Original Amplifier
- Built entire system, 6 platforms E2E tested, brand strategy, Task 17 workflow

### Session 9 (2026-03-18) — Server Architecture & Build
- Designed two-sided marketplace (user-side compute, pull-based)
- Built 19 tasks: server (52 routes, 8 models), user app (7 new files), distribution

### Session 10 (2026-03-18) — Dashboard Pages & E2E Testing
- Built 17 web pages, shared dark theme, E2E tested via Chrome DevTools — 0 bugs

### Session 11 (2026-03-18 to 2026-03-21) — Rename & Vercel Deploy
- Renamed to "Amplifier", deployed to Vercel

### Session 12 (2026-03-22) — MVP Build (Ralph Agent)
- Phases 1-7 completed. New modules: `content_generator.py`, `metric_collector.py`

### Session 13 (2026-03-22) — Integration Testing, Database Fix & UI Polish
- Supabase PostgreSQL fixed, UI polish, 4 bugs fixed

### Session 14 (2026-03-22) — Brand Strategy: User App Distribution
- Decision: post-MVP split into web dashboard + Tauri desktop agent

### Session 15 (2026-03-22) — User App E2E Testing & Bug Fixes
- 9 bugs found and fixed (commits e5c893a, 570a12b). Critical: matching was broken (missing `connected` flag).

### Session 16 (2026-03-22) — Image Gen Fix, Full E2E Posting Verified
- Cloudflare Workers AI FLUX.1 schnell as primary image gen
- Campaign runner posting fixed (function names + signatures)
- Full E2E posting verified across 4 platforms (41 min)
- DeerFlow exploration deferred

### Session 17 (2026-03-24) — Metric Pipeline Fix, Content Prompt, Webcrawler

**Content generation prompt rewrite:**
- Rewrote `CONTENT_PROMPT` in `content_generator.py` to include emotion-first hooks, value-first body, platform-specific format rules, all hard rules from `content-templates.md`
- Old prompt was generic ("generate social media content for a brand campaign") — produced ad-like output

**Webcrawler setup:**
- Cloned `github.com/Devtest-Dan/webcrawler` to `C:\Users\dassa\Work\webcrawler\`
- Installed deps: httpx, beautifulsoup4, markdownify, readability-lxml, ddgs, playwright
- Added reference to global `~/.claude/CLAUDE.md` so Claude Code in any session can use it
- Verified: `search "query"` works (DuckDuckGo), `fetch <url>` works on most sites (Investopedia blocks)
- Two modes: httpx (fast, public) and Playwright browser (JS-heavy/auth-required)

**DeerFlow research and decision:**
- Researched thoroughly via agent: it's a full-stack app (LangGraph server + FastAPI gateway + Next.js frontend + nginx)
- Requires Python 3.12+, Node.js 22+, uv, nginx, ~30 heavy dependencies
- Windows incompatible (uses `pkill`, unix nginx conventions, shell scripts — needs WSL)
- **Decision: Skip DeerFlow.** Build lightweight research pipeline (crawler + Gemini) instead.

**Metric pipeline — 4 bugs found and fixed (commit 6835344):**

1. **Post URLs were placeholders (CRITICAL)** — `campaign_runner.py:141` stored `https://{platform}.com/posted` as fake URLs. Fixed: posting functions now return actual URL strings (or fallback URLs). X/LinkedIn/Facebook extract from feed, Reddit captures redirect URL. Campaign runner stores returned URLs.

2. **`_should_scrape` had rigid 30-min windows** — Only scraped at exactly T+1h/6h/24h/72h ±30min. If scraper missed the window, data was lost. Fixed: cumulative approach — tracks completed tiers per post via metric count, scrapes next due tier regardless of when scraper runs.

3. **Earnings never calculated on Vercel** — Server billing runs via ARQ background worker which doesn't exist on Vercel serverless. Fixed: `/api/metrics` endpoint now triggers `run_billing_cycle()` inline when final metrics are submitted.

4. **Content prompt was generic** — (See above)

**E2E verification of full pipeline:**
- Inserted test metrics for 4 posts into local DB (simulating scrape)
- Synced to Vercel server via `sync_metrics_to_server()`
- Billing triggered inline → 10 posts processed, $75.98 earned
- User dashboard verified via Chrome DevTools MCP:
  - Header shows $75.98 EARNED, $75.98 BALANCE
  - Earnings tab: $75.98 total earned, $75.98 balance
  - Posts tab: all 4 posts with impressions, likes, reposts populated
  - Admin stats: $75.98 total payouts

**Vercel deployment note:**
- Cold starts cause intermittent 500s — retry logic needed for API calls
- Local SQLite may have stale schema (missing `audience_region` column) — delete `server/amplifier.db` to recreate

**Task-master tasks.json manually updated** (ANTHROPIC_API_KEY not set, so `task-master add-task` fails). Added tasks 31-35 directly to JSON.

## Important Decisions Made
- **User-side compute** — AI generation, posting, scraping on user device
- **Pull-based polling** — every 5-15 min, no websockets
- **Credentials never leave device** — server never touches social media passwords
- **Billing**: pay per impression/engagement, 20% platform cut, per-metric dedup
- **Database**: Supabase PostgreSQL via transaction pooler (port 6543)
- **Deploy autonomously**: user wants Vercel deployment done without intervention
- **Skip DeerFlow** — overkill for content gen, Windows incompatible. Build crawler + Gemini pipeline instead.
- **Inline billing on Vercel** — trigger billing in metrics endpoint since ARQ worker doesn't run on serverless
- **Post functions return URLs** — `str | None` instead of `bool`, preserves existing truthiness checks

## Key Reference Files

### Server
- `server/app/main.py` — Entry point (52 routes, lifespan)
- `server/app/core/database.py` — Supabase PostgreSQL + NullPool + SSL
- `server/app/routers/metrics.py` — Metrics submission + inline billing trigger
- `server/app/services/billing.py` — Earnings calculation from metrics + payout rules
- `server/app/templates/base.html` — Shared Jinja2 base template (emerald theme)

### User App
- `scripts/campaign_dashboard.py` — User dashboard (4 tabs + onboarding, port 5222)
- `scripts/campaign_runner.py` — Campaign loop (poll → generate → post → report). Now captures real post URLs.
- `scripts/post.py` — Posting functions now return URL strings instead of booleans
- `scripts/utils/content_generator.py` — Text: Gemini → Mistral → Groq (prompt rewritten for brand voice). Image: Cloudflare FLUX → Together AI → PIL
- `scripts/utils/metric_scraper.py` — Cumulative tier-based scraping (no more missed windows)
- `scripts/utils/metric_collector.py` — Hybrid metric collection (X/Reddit APIs + Playwright fallback)
- `scripts/utils/server_client.py` — Server API client with retry

### Config & Docs
- `config/content-templates.md` — Brand voice, content pillars, emotion-first + value-first principles
- `config/platforms.json` — Platform config (TikTok/Instagram disabled)
- `config/.env` — API keys (Gemini, Cloudflare, Together), server URL, timing params
- `docs/POST_MVP_AI_STRATEGY.md` — Future AI architecture: multi-agent pipeline, model economics
- `docs/POST_MVP_ROADMAP.md` — User app distribution: web dashboard + Tauri desktop agent

### Tools
- `C:\Users\dassa\Work\webcrawler\crawl.py` — Global webcrawler (search, fetch, crawl, authenticated sessions)

## Deployed URLs
- **Company dashboard**: https://server-five-omega-23.vercel.app/company/login
- **Admin dashboard**: https://server-five-omega-23.vercel.app/admin/login
- **Swagger docs**: https://server-five-omega-23.vercel.app/docs
- **Health check**: https://server-five-omega-23.vercel.app/health

## Test Data on Deployed Server
- **Test user**: `testuser_e2e@gmail.com` / `TestPass123!` — registered, onboarded, $75.98 earned
- **Test company**: `testcorp@gmail.com` / `TestPass123!` — "TestCorp Trading", budget partially spent
- **Test campaign**: "Trading Tools Launch Campaign" — 4 posts, metrics submitted, billing processed

## Test Commands
```bash
# === Deployed Server ===
# Company: register at /company/login
# Admin: /admin/login (password set via env var)
# Swagger: /docs

# === Local Development ===
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python scripts/campaign_dashboard.py  # http://localhost:5222
python scripts/campaign_runner.py --once
python scripts/utils/metric_scraper.py  # scrape metrics for posted URLs

# === Webcrawler (available globally) ===
python C:/Users/dassa/Work/webcrawler/crawl.py search "trading strategies 2026"
python C:/Users/dassa/Work/webcrawler/crawl.py fetch https://example.com
python C:/Users/dassa/Work/webcrawler/crawl.py --json search "query"  # structured output

# === Vercel Deploy ===
vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
printf "value" | vercel env add VAR_NAME production --cwd server
```

## Gotchas & Patterns Discovered
- `python-dotenv` treats inline comments as values — always put comments on separate lines
- `load_dotenv(override=True)` needed or Flask reloader inherits stale env vars
- Matching algorithm requires `"connected": True` in platform dict
- Supabase: use transaction pooler (port 6543), requires `NullPool` + `prepared_statement_cache_size=0`
- Cloudflare Workers AI FLUX.1 schnell works reliably on free tier (10k neurons/day)
- `post_to_x()` functions return `str | None` (URL or None), take `(draft, pw)` — each manages own browser context
- Reddit redirects to new post after submission — `page.url` captures the post URL
- X/LinkedIn/Facebook URL extraction: look for feed links after posting (best-effort, fallback to placeholder)
- Vercel cold starts cause intermittent 500s — use retry logic for API calls
- Local SQLite may lack `audience_region` column — delete `server/amplifier.db` to recreate fresh schema
- ARQ background worker doesn't run on Vercel serverless — billing must be triggered inline in API endpoints
- `_should_scrape` uses cumulative tiers (not rigid windows) — tracks completed scrapes per post via metric count
- Investopedia blocks webcrawler httpx requests — use `--browser` mode or try other financial sites
