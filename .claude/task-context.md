# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 27)

## Current Task

**Task #28 — Verify: Scheduled Posting** (in-progress) — paused during Sessions 24-27 for co-founder docs, codebase audit, v2/v3 upgrade sprint, and political campaigns strategy.

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

## Session 27 — What Was Done (Current Session)

### 1. Deep Codebase Understanding

Three parallel exploration agents did a comprehensive deep dive of the entire Amplifier product:

**Agent 1 — Amplifier Engine**: Generation pipeline (content_generator.py + AI providers), review dashboard, posting pipeline (post.py → script engine → legacy fallback), JSON posting engine (13 action types, fallback selector chains, error recovery), all 4 platform scripts, human timing, draft lifecycle, login setup, scheduling, config files.

**Agent 2 — Amplifier Server**: FastAPI main app + DB switching, all 11 models (Company, Campaign, User, CampaignAssignment, Post, Metric, Payout, Penalty, CampaignInvitationLog, AuditLog, ContentScreeningLog), auth flow, campaign API (CRUD + wizard + reach estimates + clone + export), invitation workflow, matching service (hard filters + Gemini AI scoring), billing service (cents math, 7-day hold, tier promotion), trust service (fraud detection), payments (Stripe Connect), campaign wizard (URL crawling + Gemini generation), admin dashboard (11 routers, 14 pages), company dashboard (7 routers, 10 pages), all templates.

**Agent 3 — User App + AI Layer**: Flask user app (32+ routes, 5 tabs), background agent (6 async tasks), server client (15 methods), local database (13 tables + encryption), content generator (research_and_generate + 3 image modes), AI manager (text provider fallback), image pipeline (5 providers + UGC post-processing: desaturation, color cast, grain, vignetting, EXIF injection), metric collection/scraping, post scheduler, session health, profile scraper, onboarding, client-side crypto.

### 2. Political Campaigns Strategy

Full strategic analysis and planning for using Amplifier as political campaign infrastructure during US midterm elections:

**What midterms are**: Elections every 2 years, all 435 House seats + ~33 Senate seats + governors + thousands of state/local races. $16.7B spent in 2022. Lower turnout (40%) makes grassroots mobilization critical.

**How Amplifier fits**: Politicians pay Amplifier, Amplifier pays real people to post campaign messages from personal accounts. Bypasses algorithm suppression and platform ad restrictions. Peer-to-peer political messaging is 3-10x more effective than official campaign posts.

**6 use cases**: Voter mobilization (GOTV), issue framing, candidate name recognition (down-ballot), rapid response, policy education, opposition research distribution.

**4 client tiers**: Campaign committees, PACs/Super PACs ($1.2B from top 20 in 2022), issue advocacy groups, state/local parties.

**TAM**: $100M-$500M per midterm cycle. At 25% cut = $25M-$125M platform revenue.

**3-phase plan documented**:
- Phase 0: Legal foundation (US entity + FEC compliance, $5K-$15K)
- Phase 1: 8-week MVP (geo-targeting, political content mode, FEC disclaimers, war room mode, political reporting, political wizard)
- Phase 2: Go-to-market (down-ballot swing states, sell through political consultants at 10% referral, issue advocacy groups)
- Phase 3: Scale for 2026 (self-serve, multi-race packages, war room dashboard, opponent monitoring, A/B message testing)

**Revenue projection**: ~$550K from ~58 campaigns in 2026 cycle (conservative).

### 3. Architecture Decision: One App (DECIDED)

Debated whether political campaigns should be a separate app or built into Amplifier.

**Decision: One app.** Political campaigns are a campaign type within the existing platform.

**Arguments that won**:
- User base is everything — splitting means starting from zero users on the political side, which kills the value prop (politicians need users in specific districts)
- User acquisition cost doubles with two apps — can't afford to split attention
- Politicians get access to a bigger user base in one app
- "Consultants don't want to share a platform" concern is overblown — Google Ads, Meta, Stripe all serve political and commercial clients on the same platform
- Brand contamination is solvable with a simple opt-in toggle (political_campaigns_enabled, default OFF)
- Public perception risk is premature — not at scale where journalists cover Amplifier yet

**Implementation decided**:
- `campaign_type` field: "brand" (default) or "political"
- `political_campaigns_enabled` user setting (default OFF)
- Optional `political_party_preference` (any, democratic, republican, independent, nonpartisan)
- `disclaimer_text` on Campaign model for FEC compliance
- Geographic micro-targeting (zip_code, state, congressional district)

### 4. Political Content Generation Requirements

Noted that political content generation is fundamentally different from brand content:
- Needs proper trend analysis (what's trending politically today)
- Must read news on political parties and campaigns
- Must know what opposing party is saying (for contrast/rapid response)
- Must know what supporting party is saying (for coordinated messaging)
- Requires continuous daily news monitoring, not one-time URL crawl
- Research pipeline refreshes daily, not weekly

### 5. Timing Decision: Ship With Core Product (DECIDED)

Decided to include political campaign features in the initial Amplifier launch, not add them later.

**Reasoning**:
- Zero users is not a blocker — users will be acquired
- Core foundation will be tested and verified before launch
- Shipping with political features from day one means users are already there when campaign season starts
- Political vertical is potentially the highest-revenue feature
- Having it ready before demand hits is a competitive advantage

### 6. Files Created/Updated

- **Created**: `docs/political-campaigns.md` — Complete political campaigns strategy document (midterms explainer, problem/solution, 6 use cases, 4 client tiers, 3-phase plan, go-to-market, pricing, revenue projections, risks, architecture decision)
- **Updated**: `FUTURE.md` — Added "Fake Followers/Engagement Problem & Amplifier as Growth Engine" section (verbatim user note) and "Amplifier for Political Campaigns" section (summary with architecture decision)

### Key Decisions This Session
- Political campaigns = campaign type within existing Amplifier app (not separate product)
- Users opt into political campaigns via toggle (default OFF)
- FEC disclaimers appended to every political post
- Geo-targeting (zip, state, district) needed for both political and brand campaigns
- Political content generation needs continuous daily news/trend monitoring
- Political features ship with the core product launch, not added later
- Sell through political consultants (10% referral), start with down-ballot swing state races
- 25-30% platform cut for political (vs 20% for brands)

## Remaining Blockers (Priority Order)
1. Posting URL capture broken on LinkedIn/Facebook/Reddit (Task #28)
2. Metric scraping unverified E2E (Tasks #29-30)
3. Billing unverified E2E (Tasks #31-32)
4. X account detection risk (locked during testing)
5. Real Stripe payments (both sides) — company deposit + creator withdrawal
6. FTC disclosure (#ad/#sponsored) not in content generator
7. Distribution — no installable app yet (Tauri or web planned)
8. Political features: legal structure (US entity + FEC compliance) needed before taking political clients

## Key Reference Files
- `scripts/post.py` — Posting orchestrator (script-first via post_via_script(), legacy fallback)
- `scripts/engine/` — JSON posting engine (script_parser, selector_chain, human_timing, error_recovery, script_executor)
- `config/scripts/` — Platform JSON scripts (x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json)
- `scripts/ai/` — AiManager (text), ImageManager (images, 5 providers), image_postprocess, image_prompts
- `scripts/background_agent.py` — Orchestrator: polling, content gen + image gen, posting, metrics, session health
- `scripts/utils/content_generator.py` — AI content gen via AiManager + ImageManager (txt2img + img2img)
- `scripts/utils/local_db.py` — 13 tables, API key encryption, post_schedule retry lifecycle
- `server/app/services/billing.py` — Cents math, hold period, tier promotion, void earnings
- `server/app/services/payments.py` — Stripe Connect + auto payout processing
- `server/app/services/matching.py` — AI scoring + tier-based campaign limits
- `server/app/utils/crypto.py` — AES-256-GCM encryption
- `docs/political-campaigns.md` — Complete political campaigns strategy and implementation plan
- `docs/AMPLIFIER-SPEC.md` — Complete multi-implementation system spec
- `docs/V2-V3-UPGRADE-PLAN.md` — 15 upgrades across 5 phases
- `docs/IMAGE-GENERATION-UPGRADE.md` — Image gen spec (txt2img, img2img, post-processing)
- `FUTURE.md` — Deferred features including political campaigns and fake engagement problem

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222
- **GitHub**: https://github.com/Samaara-Das/Amplifier (private, Devtest-Dan has access)

## Test Commands
```bash
# Run user app
python scripts/user_app.py

# Run server locally
cd server && GEMINI_API_KEY=<key> python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Test posting
python scripts/tests/test_all_post_types.py

# Deploy
vercel deploy --yes --prod --cwd server
```
