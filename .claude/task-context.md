# Amplifier — Task Context

**Last Updated**: 2026-03-22 (Session 16)

## Current Task
- **Branch: `main`** — MVP built, E2E tested, all critical bugs fixed, deployed
- All MVP phases (1-8) complete
- User app E2E tested: onboarding → campaign matching → content generation → posting all working
- Server deployed to Vercel with Supabase PostgreSQL
- **Full pipeline verified E2E**: poll → generate (Gemini) → image (Cloudflare FLUX) → post (4 platforms) → report to server

## Project Overview
Two interconnected systems:
1. **Amplifier Engine** — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** — Two-sided marketplace: companies create campaigns, users earn by posting via Amplifier

## Task Progress Summary

### MVP Phases (All Complete)
- [x] Phase 1: Critical Fixes (deps, configurable server URL, disable TikTok/Instagram)
- [x] Phase 2: PostgreSQL/Supabase support
- [x] Phase 3: Content generation via free AI APIs (Gemini → Mistral → Groq)
- [x] Phase 4: Region + category matching
- [x] Phase 5: Hybrid metric collection (X/Reddit APIs + Browser Use)
- [x] Phase 6: Dashboard polish, post editing, influencer visibility
- [x] Phase 7: Installer fixes
- [x] Phase 8: Integration testing (full E2E on deployed server)

### Additional Completed
- [x] Supabase PostgreSQL connected (transaction pooler)
- [x] Company login fix (was broken due to SQLite in /tmp/)
- [x] UI polish — emerald green accent, DM Sans font, visual enhancements
- [x] User app E2E testing — 9 bugs found and fixed across 2 commits
- [x] Company dashboard form preservation on validation error
- [x] Flash message cleanup on tab switch
- [x] Image generation fixed — Cloudflare Workers AI FLUX.1 schnell (free tier) as primary, Together AI + Pollinations as fallbacks
- [x] Campaign runner posting fix — function names and signatures corrected
- [x] Full E2E posting verified — Facebook, LinkedIn, Reddit (r/AlgoTrading), X all posted successfully
- [x] Server sync verified — 4 posts reported, assignment status updated to "posted"

### Next Session Priority
- [ ] **Content generation quality** — AI-generated content reads like generic ads, not emotion-first brand-voice content. Fix the prompt in `content_generator.py` to match `config/content-templates.md`
- [ ] **Metric scraping** — run `metric_scraper.py` on the 4 posted URLs to verify engagement collection works
- [ ] **Earnings verification** — check that earnings show up on the user dashboard after metrics are collected

### Session 17 Tasks (2026-03-24)
- [x] **Task 31: Fix content generation prompt** — Rewrote CONTENT_PROMPT in content_generator.py with emotion-first hooks, value-first body, platform-specific format rules, hard rules from content-templates.md
- [ ] **Task 32: Integrate DeerFlow** — ByteDance multi-agent framework for research-backed content generation
- [x] **Task 33: Set up webcrawler globally** — Installed at `C:\Users\dassa\Work\webcrawler\`, added to global CLAUDE.md for all sessions
- [ ] **Task 34: Verify metric scraping + earnings** — Run metric_scraper.py, confirm earnings on dashboard
- [x] **Task 35: Explore free/cheap LLMs (deferred)** — Saved note: Qwen, Llama, Nvidia, local LLMs. Current Gemini works. Revisit when free tier gets restricted or video gen needed.

### Post-MVP Tasks (Pending)
- [ ] **AI architecture rethink** — Design content generation/posting architecture around future model economics. Models are getting cheaper fast; some are already free (e.g. Xiaomi MiMo v2 Flash — free on Kiko Claw). See `docs/POST_MVP_AI_STRATEGY.md`.
- [ ] **User app distribution rethink** — Move user dashboard to web, ship lightweight Tauri desktop agent for posting only (see `docs/POST_MVP_ROADMAP.md`)
- [ ] Browser Use migration for posting
- [ ] Website-to-API fallback tool
- [ ] Expand free API fallback chain
- [ ] LinkedIn/Facebook official API migration
- [ ] Write tests (~50 pytest tests)
- [ ] Campaign marketplace/browse view
- [ ] 18-21: Test Run, Account Warmup, Profile Revamps, LinkedIn "I'm Back"
- [ ] 22-30: AI Video, Newsletters, Facebook Groups, TradingView, Analytics, etc.

## Session History

### Sessions 1-8 (2026-03-07 to 2026-03-18) — Original Amplifier
- Built entire system, 6 platforms E2E tested, brand strategy, Task 17 workflow

### Session 9 (2026-03-18) — Server Architecture & Build
- Designed two-sided marketplace (user-side compute, pull-based)
- Built 19 tasks: server (52 routes, 8 models), user app (7 new files), distribution
- Fixed 4 bugs: passlib crash, matching duplicates, billing dedup, tab switching

### Session 10 (2026-03-18) — Dashboard Pages & E2E Testing
- Built 17 web pages (company 6, admin 6, user 5), shared dark theme
- E2E tested all 17 pages via Chrome DevTools — 0 bugs found

### Session 11 (2026-03-18 to 2026-03-21) — Rename & Vercel Deploy
- Renamed to "Amplifier" (35 files, GitHub repo)
- Deployed to Vercel (SQLite in /tmp/ for initial demo)

### Session 12 (2026-03-22) — MVP Build (Ralph Agent)
- Ralph script executed 6 iterations completing Phases 1-7 of MVP spec
- New modules: `content_generator.py`, `metric_collector.py`
- MVP spec finalized: `mvp.md` at repo root

### Session 13 (2026-03-22) — Integration Testing, Database Fix & UI Polish
- Full E2E cycle verified via Chrome DevTools MCP on deployed server
- Supabase PostgreSQL connection fixed (5 commits: NullPool + transaction pooler + SSL)
- UI polish: emerald green accent, DM Sans font, gradient cards, 16 files changed
- 4 bugs fixed (vercel.json, PIL import, Supabase connection, rootDirectory)

### Session 14 (2026-03-22) — Brand Strategy: User App Distribution
- Decision: post-MVP split into web dashboard + Tauri desktop agent
- Created `docs/POST_MVP_ROADMAP.md` with 3-phase plan

### Session 15 (2026-03-22) — User App E2E Testing & Bug Fixes

**Testing method:** Chrome DevTools MCP on localhost:5222

**Full E2E flow tested:**
1. Dashboard starts — all 4 tabs render (Campaigns, Posts, Earnings, Settings)
2. Onboarding — register user `testuser_e2e@gmail.com` against live Vercel server
3. Profile setup — niche tags (trading, finance, stocks, crypto), follower counts, platform connections
4. Mode selection — Semi-Auto
5. Campaign creation on company side (TestCorp Trading, $500 budget, Finance category, X platform)
6. Campaign polling — successfully matched (1 campaign found)
7. Content generation — proper error when no API keys set

**9 bugs found and fixed (commits e5c893a, 570a12b):**

Critical (matching was completely broken):
1. **Onboarding tab hidden after login** — `{% if not logged_in %}` hid steps 2-4. Fixed: `{% if not onboarding_complete %}` with explicit `onboarding_done` flag.
2. **Platform `connected` flag missing** — matching checked `v.get("connected")` but it was never set. Campaigns NEVER matched. Fixed: add `"connected": True` in `onboarding_profile`.

High:
3. **Onboarding didn't auto-advance** — after registration, user dumped to Campaigns tab. Fixed: `onboarding_step` context var + JS auto-switch.
4. **Silent content generation errors** — `except: pass` swallowed all errors. Fixed: show error in flash message.
5. **.env inline comments parsed as values** — `python-dotenv` included `# comment` as value, causing Unicode crash (em dash `—`). Fixed: move comments to separate lines in `config/.env`.

Medium:
6. **Raw JSON error messages** — server validation errors shown as raw pydantic JSON. Fixed: parse into friendly messages.
7. **Stale env var caching** — `load_dotenv(override=False)` didn't refresh. Fixed: `override=True`.
8. **Campaign form cleared on error** — all fields lost on "Insufficient balance". Fixed: pass form data back to template, add `value` attrs + `checked` attrs for checkboxes.
9. **Flash messages persist across tabs** — alerts stayed visible. Fixed: clear `.alert` elements in `switchTab()` JS.

**Not a bug (investigated):**
- Floating-point payout display (0.009999...) — only in Chrome a11y tree, visually displays correctly as $0.01.

**Remaining Minor Issues:**
1. Admin password on Vercel is encrypted — value unknown (user set it)

### Session 16 (2026-03-22) — Image Gen Fix, Full E2E Posting Verified

**Image generation chain fixed:**
- Gemini Imagen removed (paid-only, all image models have 0 free quota)
- Pollinations broken (API changed, now requires key, servers returning 500s)
- **Cloudflare Workers AI FLUX.1 schnell** added as primary (free, 10k neurons/day) — works perfectly
- Together AI FLUX added as fallback (needs credits despite "free tier" claim)
- PIL branded image kept as last resort

**Campaign runner posting fixed:**
- Function names wrong: `_post_to_x` → `post_to_x` (no underscore prefix)
- Function signatures wrong: `(page, draft)` → `(draft, pw)` — each function manages its own browser context
- `_image_path` key was being treated as a platform to post to — filtered out

**Full E2E posting verified (41 minutes total):**
1. Server poll → 1 campaign matched
2. Text gen (Gemini 2.5 Flash Lite) → content for 4 platforms (4s)
3. Image gen (Cloudflare FLUX) → image generated (2s)
4. Facebook → posted with human emulation (browsing, 7 likes)
5. LinkedIn → posted with compose trigger flow
6. Reddit → posted to r/AlgoTrading (title + body, 12 upvotes)
7. X → posted with engagement (15 likes, 3 retweets)
8. Server sync → 4 posts reported, assignment status "posted"

**API keys configured:**
- `GEMINI_API_KEY` — text generation
- `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` — image generation
- `TOGETHER_API_KEY` — image fallback (402 credits issue)

**DeerFlow exploration:**
- Researched ByteDance DeerFlow (open-source super-agent framework)
- Decided to defer integration — test existing pipeline first
- Created `docs/POST_MVP_AI_STRATEGY.md` with multi-agent pipeline vision
- Also noted: explore Xiaomi MiMo v2 Flash (free on Kiko Claw), design for future free models

## Important Decisions Made
- **User-side compute** — AI generation, posting, scraping on user device
- **Pull-based polling** — every 5-15 min, no websockets
- **Credentials never leave device** — server never touches social media passwords
- **Content modes**: Full Auto (1.5x), Semi-Auto (2.0x), Manual (2.0x)
- **Billing**: pay per impression/engagement, 20% platform cut, per-metric dedup
- **Trust**: 0-100 score, affects campaign priority
- **Database**: Supabase PostgreSQL via transaction pooler (port 6543)
- **Dashboards**: Jinja2 (server), inline HTML (Flask user app), emerald green dark theme
- **Deploy autonomously**: user wants Vercel deployment done without intervention

## Key Reference Files

### Server
- `server/app/main.py` — Entry point (52 routes, lifespan)
- `server/app/core/database.py` — Supabase PostgreSQL + NullPool + SSL
- `server/app/routers/company_pages.py` — Company dashboard (6 pages)
- `server/app/routers/admin_pages.py` — Admin dashboard (6 pages)
- `server/app/templates/base.html` — Shared Jinja2 base template (emerald theme, DM Sans)
- `server/app/templates/company/campaign_create.html` — Campaign form (with form data preservation)
- `server/app/services/{matching,billing,trust,payments}.py` — Business logic
- `server/api/index.py` — Vercel serverless entry point

### User App
- `scripts/campaign_dashboard.py` — User dashboard (4 tabs + onboarding, port 5222)
- `scripts/campaign_runner.py` — Campaign loop (poll → generate → post → report)
- `scripts/utils/content_generator.py` — Text: Gemini → Mistral → Groq. Image: Cloudflare FLUX → Together AI → Pollinations → PIL
- `scripts/utils/metric_collector.py` — Hybrid metric collection
- `scripts/utils/server_client.py` — Server API client with retry

### Config & Docs
- `mvp.md` — MVP spec (source of truth)
- `config/platforms.json` — Platform config (TikTok/Instagram disabled)
- `config/.env` — API keys (Gemini, Cloudflare, Together), server URL, timing params (comments on separate lines, not inline!)
- `docs/POST_MVP_AI_STRATEGY.md` — Future AI architecture: multi-agent pipeline, DeerFlow, MiMo v2 Flash, model economics
- `docs/POST_MVP_ROADMAP.md` — User app distribution: web dashboard + Tauri desktop agent

## Deployed URLs
- **Company dashboard**: https://server-five-omega-23.vercel.app/company/login
- **Admin dashboard**: https://server-five-omega-23.vercel.app/admin/login
- **Swagger docs**: https://server-five-omega-23.vercel.app/docs
- **Health check**: https://server-five-omega-23.vercel.app/health

## Vercel Environment Variables
| Variable | Status |
|----------|--------|
| `DATABASE_URL` | Set — Supabase transaction pooler (port 6543) |
| `JWT_SECRET_KEY` | Set — encrypted |
| `ADMIN_PASSWORD` | Set — encrypted (unknown value) |

## Test Data on Deployed Server
- **Test user**: `testuser_e2e@gmail.com` / `TestPass123!` — registered, onboarded, platforms connected
- **Test company**: `testcorp@gmail.com` / `TestPass123!` — "TestCorp Trading", $500 remaining balance
- **Test campaign**: "Trading Tools Launch Campaign" — active, $500 budget, Finance category, X platform required

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
python scripts/review_dashboard.py    # http://localhost:5111

# === Vercel Deploy ===
vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
# Use printf (not echo) for env vars to avoid trailing newline:
printf "value" | vercel env add VAR_NAME production --cwd server
```

## Gotchas & Patterns Discovered
- `python-dotenv` treats inline comments as values — always put comments on separate lines
- `load_dotenv(override=True)` needed or Flask reloader inherits stale env vars
- `.test` TLD rejected by pydantic email validation — use real domains for testing
- Matching algorithm requires `"connected": True` in platform dict — not just presence of key
- Onboarding completion needs explicit flag, not derived from profile state (race condition with step advancement)
- `vercel.json` `rootDirectory` is a project-level setting — CLI rejects it in config file
- Supabase: use transaction pooler (`aws-1-us-east-1.pooler.supabase.com:6543`), not direct connection
- Supabase + pgbouncer: requires `NullPool` + `prepared_statement_cache_size=0`
- Gemini image gen (Imagen, flash-image, 3.x preview) all have 0 free quota — paid only
- Pollinations.ai changed API: now requires API key, endpoint moved to `gen.pollinations.ai`, servers frequently 500
- Together AI "free tier" for images returns 402 — actually needs credits
- Cloudflare Workers AI FLUX.1 schnell works reliably on free tier (account ID + API token from Workers AI template)
- `post_to_x()` functions in `post.py` have no underscore prefix and take `(draft, pw)` not `(page, draft)`
- Old browser profile from locked X account causes blank page — delete `profiles/x-profile/` and re-run `login_setup.py`
- Campaign runner in `semi_auto` mode generates content but skips posting (good for testing generation only)
- Full E2E posting run takes ~41 min due to human emulation (browsing + engagement on each platform)
