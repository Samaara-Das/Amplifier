# Amplifier — Task Context

**Last Updated**: 2026-04-03 (Session 26)

## Current Task

**Task #28 — Verify: Scheduled Posting** (in-progress) — paused during Sessions 24-25 for co-founder docs and codebase audit.

Next: Resume posting verification (URL capture fixes for LinkedIn/Facebook/Reddit), then #29-#30 (Metric Scraping).

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting (#27-#28), Metrics (#29-#30) | **#27 done, #28 in-progress** |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |
| Future | AI scrapers, content gen, video gen, tiers | #51-#80 | All pending |

**27 done, 1 in-progress, 52 pending. 80 total tasks.**

## Session 23 Summary (Previous Session)

Tasks #23-#26 completed (Content Gen + Review). Task #27 done, #28 in-progress. Key work:
- Content gen: documented current system, deferred rebuild to Task #63
- Content review: unapprove button, Reddit JSON fix, company name display, auto-reload, notifications
- Posting: CRITICAL human_delay sync bug fixed (broke ALL posting), 4 platforms verified working
- Posting test results: all posts delivered, URL capture broken for LinkedIn/Facebook/Reddit
- 10 future tasks created (#57-#66), selector research via Chrome DevTools MCP
- Key bugs: human_delay sync, X strict mode, Reddit spam filter, LinkedIn/Facebook timeouts

## Session 26 — What Was Done (Current Session)

### Documentation Update for 4-Commit Feature Sprint
Updated all docs after 4 major commits (Declarative JSON Engine, Financial Safety, Automation/AI Abstraction/Tiers, Image Gen Upgrade):
- CLAUDE.md — engine/ and ai/ modules, updated service descriptions, updated model fields, JSON engine note in selector patterns section
- docs/PRD.md — Company/User/Payout/Penalty model fields (cents columns, tier, status lifecycle), post_schedule schema, billing section (hold period, tier table), Implementation Status table
- docs/AMPLIFIER-SPEC.md — Section 5.3 (image generation: 5-provider chain, UGC post-processing, img2img), Section 6.1 (JSON script engine table), Section 3.7 (tiers now in v1), Section 8 comparison table
- Memory MEMORY.md — key file listings updated with engine/ and ai/ modules

### Key Reference Files Added This Session
- `scripts/engine/` — 6-module JSON script engine
- `scripts/ai/` — text AiManager + image ImageManager + UGC post-processor
- `server/app/utils/crypto.py` — server-side AES-256-GCM encryption
- `scripts/utils/crypto.py` — client-side machine-derived key encryption
- `config/scripts/` — x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json

## Session 25 — What Was Done

### Full Codebase Audit & Documentation Update
Comprehensive audit of the entire Amplifier project — server, user app, engine, and all documentation. Found significant discrepancies between docs and code:

**Key findings:**
- Route count was "52" in all docs → actually ~88 routes (27 API + 34 admin + ~22 company + 2 system)
- Model count was "8 tables" → actually 11 models (added AuditLog, ContentScreeningLog, CampaignInvitationLog)
- Admin dashboard was "6 pages" → actually 14 pages (refactored into 10 modular routers)
- Company dashboard was "6 pages" → actually 10 pages (refactored into 7 modular routers)
- User app has 32+ Flask routes, 13 local SQLite tables, background agent with 6 async tasks
- Server services: 7 (added campaign_wizard.py, storage.py)

**Docs updated:**
- CLAUDE.md — route counts, model counts, page counts, services, user app description
- docs/PRD.md — route counts, model counts, added AuditLog + ContentScreeningLog model definitions, expanded admin/company dashboard page lists, updated admin API section, expanded local DB table list
- docs/pitch-deck.md — route count
- .claude/task-context.md — session 25 notes, task counts
- Memory MEMORY.md — all counts, server file listings, user app file listings, implementation status

## Session 24 — What Was Done

### Documentation for Co-Founder Review
Created 3 comprehensive documents for potential co-founder **Devtest-Dan**:

1. **PRD** (`docs/PRD.md`, ~56KB) — Complete product requirements document:
   - Product concept, problem statement, solution overview
   - Full system architecture with diagrams
   - All 6 feature areas detailed (server, company dashboard, admin dashboard, user app, posting engine, content gen, personal brand engine)
   - Complete data models (9 server tables + 8 local tables)
   - Full API reference (52+ endpoints)
   - Monetization formula and billing mechanics
   - Trust & safety system
   - Technical constraints, implementation status
   - Future roadmap (6 phases)
   - Configuration appendices

2. **Concept Doc** (`docs/concept.md`) — Non-technical business document:
   - Vision: marketplace turning everyday social media users into a distribution channel
   - Problem (both sides), solution (how it works in plain language)
   - How it's different (vs influencer agencies, affiliate networks, UGC platforms, social mgmt tools)
   - Business model (20% take rate, unit economics, money flow)
   - Market opportunity (TAM $21B, SAM $5B, SOM $50M)
   - What's built (V1 shipped, live URLs)
   - Risks and honest challenges (platform detection, cold start, legal, revenue scale)
   - Co-founder opportunity (what they'd own, why join now)

3. **Pitch Deck** (`docs/pitch-deck.md`) — 13-slide markdown pitch:
   - Problem (company + user sides)
   - Solution, How It Works (5-step flow)
   - Market Size (TAM/SAM/SOM)
   - Business Model (20% take, ~90% gross margin)
   - Competitive Landscape (comparison matrix)
   - Traction (V1 built, live URLs, 52+ endpoints)
   - Product Highlights, Roadmap
   - Team & What We Need, The Ask

### GitHub Access for Devtest-Dan
- Repo `Samaara-Das/Amplifier` is **private**
- **Devtest-Dan** invited as collaborator with **push access** (pending acceptance)
- All changes merged from `flask-user-app` → `main` and pushed
- Devtest-Dan will see everything on default `main` branch

### Key Decisions This Session
- Devtest-Dan is a **potential co-founder/partner** — docs framed for that audience
- All 80+ commits from flask-user-app merged to main for visibility
- Honest framing in docs: pre-revenue, V1 built, real risks acknowledged
- Market sizing: TAM $21B (influencer marketing), SOM $50M (3-year target)

## Session 23 Key Reference (Posting Verification)

### Task #28 Remaining To-Dos (Resume Next Session)
1. Fix URL capture for LinkedIn, Facebook, Reddit
2. Verify LinkedIn image actually uploads
3. Re-test all platforms with URL capture fixes

### Posting Test Results (Session 23)
| Platform | Text-only | Image+Text | Image-only | URL Capture |
|----------|-----------|------------|------------|-------------|
| X | SUCCESS | SUCCESS | SUCCESS | 3/3 |
| LinkedIn | PARTIAL | SUCCESS | PARTIAL | 1/3 (timeout) |
| Facebook | FAILED | FAILED | FAILED | 0/3 (timeout) |
| Reddit | PARTIAL | PARTIAL | PARTIAL | 0/3 (no redirect) |

All posts delivered (0 failures) but URL capture broken for LinkedIn/Facebook/Reddit.

### Platform Selectors (Verified Session 23)
- **LinkedIn**: `button "Start a post"` → `textbox "Text editor..."` → `button "Add media"` → `button "Post"`
- **Facebook**: `button "What's on your mind?"` → `textbox` → `button "Photo/video"` → `button "Post"`
- **Reddit**: `/user/{username}/submit` → `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button "Post"`
- **X**: `data-testid` attributes. `[data-testid="tweetButton"]`, `[data-testid="fileInput"]`

## Key Reference Files
- `scripts/post.py` — Platform posting orchestrator (script-first via post_via_script(), legacy fallback)
- `scripts/engine/` — Declarative JSON posting engine (script_parser, selector_chain, human_timing, error_recovery, script_executor)
- `config/scripts/` — Platform JSON scripts (x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json)
- `scripts/ai/` — AI provider abstraction (AiManager for text, ImageManager for images, UGC post-processing)
- `scripts/utils/post_scheduler.py` — Post scheduling and execution
- `scripts/background_agent.py` — Polling, content gen, posting loop
- `scripts/utils/content_generator.py` — AI content generation via AiManager + ImageManager
- `scripts/utils/local_db.py` — Local SQLite (API key encryption, post_schedule error_code/retry)
- `server/app/services/billing.py` — Billing engine (cents math, hold period, tier promotion)
- `server/app/services/payments.py` — Stripe Connect + auto payout processing
- `scripts/tests/test_all_post_types.py` — Full posting test suite (12 tests)
- `docs/PRD.md` — Comprehensive product requirements
- `docs/AMPLIFIER-SPEC.md` — Multi-implementation system spec
- `docs/concept.md` — Non-technical concept doc for co-founder
- `docs/pitch-deck.md` — 13-slide markdown pitch deck
- `FUTURE.md` — 12 future feature specs with tool comparisons

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222
- **GitHub**: https://github.com/Samaara-Das/Amplifier (private, Devtest-Dan has access)

## Test Commands
```bash
# Run user app (with hot reload)
python scripts/user_app.py

# Run server locally
cd server && GEMINI_API_KEY=<key> python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Test posting (all platforms, all types)
python scripts/tests/test_all_post_types.py

# E2E matching test
python scripts/tests/test_matching_e2e.py setup && python scripts/tests/test_matching_e2e.py test && python scripts/tests/test_matching_e2e.py cleanup

# Deploy
vercel deploy --yes --prod --cwd server
```
