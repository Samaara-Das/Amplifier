# Amplifier — Task Context

**Last Updated**: 2026-03-22 (Session 14)

## Current Task
- **Branch: `main`** — MVP built, integration tested, Supabase connected, UI polished
- All MVP phases (1-8) complete
- Server deployed to Vercel with Supabase PostgreSQL
- Brand strategy discussion — user app distribution model for post-MVP

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

### Next Session Priority
- [ ] **Test user desktop app locally** — run `campaign_dashboard.py`, verify it starts without errors, connects to Vercel server, onboarding flow works, campaigns render with new emerald theme, content generation fires (needs Gemini API key), post editing flow works. Test via Chrome DevTools on localhost:5222.

### Post-MVP Tasks (Pending)
- [ ] **User app distribution rethink** — Move user dashboard to web, ship lightweight Tauri desktop agent for posting only (see `docs/POST_MVP_ROADMAP.md`)
- [ ] 31: Browser Use migration for posting
- [ ] 32: Website-to-API fallback tool
- [ ] 33: Expand free API fallback chain
- [ ] 34: LinkedIn/Facebook official API migration
- [ ] 35: Write tests (~50 pytest tests)
- [ ] 36: Campaign marketplace/browse view
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

**Phase 8 Integration Testing (Chrome DevTools MCP):**
- Full E2E cycle verified: company register → create campaign → activate → user register → match → post → metrics → billing → earnings
- All API flows working: `/api/campaigns/mine`, `/api/posts`, `/api/metrics`, `/api/users/me/earnings`
- Company dashboard shows platform breakdown, creator list with handles + post URLs + engagement
- Admin dashboard shows overview stats, user management, billing cycle trigger

**Supabase PostgreSQL Connection (5 commits to fix):**
- Root cause: `DATABASE_URL` env var not set on Vercel → SQLite in `/tmp/` → data lost between serverless instances
- `echo` command adds trailing `\n` that corrupts env vars → use `printf` instead
- Direct connection (`db.*.supabase.co:5432`) unreachable from Vercel (`[Errno 99]`)
- Pooler port 6543 on `db.*` hostname also unreachable
- **Working solution**: Supabase transaction pooler at `aws-1-us-east-1.pooler.supabase.com:6543`
- Required: `NullPool` (serverless), `prepared_statement_cache_size=0` (pgbouncer), SSL context
- Both company login and data persistence issues resolved (same root cause)

**UI Polish:**
- Accent: blue (`#3b82f6`) → emerald green (`#10b981` / `#34d399`)
- Font: system fonts → DM Sans (Google Fonts)
- Cards: gradient bg + hover lift + shadow
- Stats: emerald glow on hover
- Buttons: lift + colored glow hover
- Tables: emerald left-border accent on row hover
- Sidebar: gradient active state + SVG nav icons (Heroicons)
- Login pages: radial emerald gradient bg + card glow
- Page headers: gradient text effect
- User app palette aligned with server dashboards
- 16 files changed across all 3 dashboard systems

**Bugs Fixed This Session:**
1. `vercel.json` rootDirectory removal reverted (commit d4150e0)
2. PIL import fix: `generate_branded_image` → `generate_landscape_image` (commit d4150e0)
3. Supabase connection: NullPool + transaction pooler + prepared_statement_cache_size (commits 54838d0 → 1d2c7c0)
4. `rootDirectory` removed from vercel.json (Vercel CLI now rejects it) (commit 627aa7d)

### Session 14 (2026-03-22) — Brand Strategy: User App Distribution
- Discussed how influencers/users access the Amplifier app (desktop vs web vs hybrid)
- Current desktop-only (PyInstaller) approach flagged as high-friction for user acquisition
- Decision: **Post-MVP task** — split into web dashboard (zero install) + Tauri desktop agent (posting only)
- Created `docs/POST_MVP_ROADMAP.md` with 3-phase plan (web dashboard → Tauri agent → optional cloud posting)

**Remaining Minor Issues:**
1. Admin password on Vercel is encrypted — value unknown (user set it)
2. Niche Tags field redundant — form has both old text input and new Categories checkboxes

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
- `server/app/services/{matching,billing,trust,payments}.py` — Business logic
- `server/api/index.py` — Vercel serverless entry point
- `vercel.json` — Vercel deployment config

### User App
- `scripts/campaign_dashboard.py` — User dashboard (5 tabs, port 5222)
- `scripts/campaign_runner.py` — Campaign loop (poll → generate → post → report)
- `scripts/utils/content_generator.py` — Free AI API content gen (Gemini → Mistral → Groq)
- `scripts/utils/metric_collector.py` — Hybrid metric collection

### Config & Docs
- `mvp.md` — MVP spec (source of truth)
- `config/platforms.json` — Platform config (TikTok/Instagram disabled)
- `config/.env` — API keys, server URL, timing params

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
