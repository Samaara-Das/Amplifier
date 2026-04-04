# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 29)

## Current Task

**Phase A+B+C COMPLETE.** Moving to Phase D (Tier 4 Features). First task: #68 Repost campaigns.

## Task Progress Summary

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All done |
| 3 Delivery | Posting, Metrics | #27-#34 | All done |
| 4 Money | Stripe, Campaign Detail | #35-#38 | All done |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | Pending (Phase F) |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | Pending (Phase F) |
| Security | CSRF, Lockout, Reset, Encryption | #66-#76 | All done (except #76 deferred) |
| Schema | Phase C migrations | — | Done |
| Future | AI scrapers, content gen, tiers | #51-#68 | Pending (Phase D) |

**45 done, 0 in-progress, 35 pending. 80 total tasks.**

## Session 29 — What Was Done (continuation of session 28)

### Phase A Complete (Tasks #28-#38) — 7 commits

**Task #28 — URL Capture (3 commits: `4e8c314`, `e72f11a`, `2bf0264`):**
- Fixed all 4 platforms: X (relative href→full URL), LinkedIn (dispatch_event + activity page fallback), Facebook (permalink selectors), Reddit (legacy poster with `#post-composer_bodytext` click for body)
- Added `optional` field to ScriptStep, fixed `aria-label` exact CSS matching, Chrome/137 UA consistency between login_setup.py and post.py
- Key insight: `dispatch_event("click")` is the standard for overlay-intercepted buttons

**Tasks #29-#32 — Metrics + Billing (`73d74c0`, `2ad3116`):**
- All 4 scrapers verified against real posts (X aria-labels, LinkedIn body text, Reddit shreddit-post attrs)
- Fixed post sync: assignment_id from local_campaign (was 0 → server skipped all). server_post_id mapped back
- Fixed CPM multiplier: `get_cpm_multiplier()` now applied in billing. Verified: seedling $4.80, amplifier $9.60 (2x)
- E2E billing verified on local server: post → metrics → billing → earnings → payout

**Tasks #33-#38 — Earnings + Stripe + Campaign Detail (`e58a6b6`):**
- Dashboard earnings card uses server API (was showing $0 from empty local table)
- Stripe test mode: $0→$50 instant credit. Campaign detail API returns correct budget data

### Phase B Complete (Tasks #66-#76) — 6 commits

- **#72 CSRF** (`2cf7f7d`): Flask-WTF CSRFProtect + auto-inject via base.html JS
- **#66 X lockout** (`2cf7f7d`): PLATFORM_LOCKOUT_INDICATORS + check before auth/login
- **#67 Session health** (`2cf7f7d`): Retry, posting success shortcut, Chrome/137 UA
- **#70 Draft count** (`b11f4c8`): Filter by last 24h (was showing all-time stale drafts)
- **#71 Password reset** (`f11520b`): POST /api/auth/reset-password for users + companies
- **#73 Encrypt auth** (`83612e6`): Already implemented — verified and re-encrypted token
- **#74 Campaign search** (`fe01dcd`, `fe3bb13`): Search bar, defaults to Active tab when searching
- **#75 Draft UX**: Already implemented — char counts with platform limits
- **FTC disclosure** (`12b7dd5`): `_append_ftc_disclosure()` with X 280-char handling

### Phase C Complete — Schema Extensions (`83f796e`)

One migration pass for all Tier 4 fields:
- **Server Campaign**: `campaign_goal`, `campaign_type`, `tone`, `preferred_formats`, `disclaimer_text`
- **Server User**: `zip_code`, `state`, `political_campaigns_enabled`, `subscription_tier`
- **Local agent_draft**: `format_type`, `variant_id`
- **Local local_campaign**: `campaign_type`, `campaign_goal`, `tone`
- **New table**: `campaign_posts` (repost campaigns)
- **API schemas**: CampaignCreate, CampaignResponse, CampaignBrief all updated

### Bug Fixes This Session
1. X URL missing domain — relative href resolution against page origin
2. Facebook `get_by_label("Post")` matched "Create a post" — exact CSS fix
3. LinkedIn session killed by user agent mismatch — Chrome/137 in both files
4. Reddit HeadlessChrome blocked — explicit UA in scraper + session_health
5. Reddit body in title — click `#post-composer_bodytext` instead of JS focus
6. Reddit 335 fake impressions — generic `/comments/` URLs filtered from scraping
7. Campaign search tab — defaults to Active when `?q=` present
8. CPM multiplier never applied — now called in billing cycle
9. Post sync assignment_id=0 — resolved from local_campaign
10. Dashboard earnings $0 — switched to server API

### Key Decisions
- Chrome DevTools MCP for self-verification of UI changes
- Rate limiting deferred to Phase G (Vercel has DDoS protection)
- #76 Invitation UX deferred to Phase F
- Reddit JSON script Post button still broken — legacy poster handles Reddit
- Father's company has Stripe account for Amplifier

## Phase D: What's Next

Per `docs/EXECUTION-ORDER.md`, Phase D is the largest block (25-35 days):

```
#68 Repost campaign type
 → simplest type, proves campaign_type field works
#51/#59 AI profile scraping
 → better profile data for matching + content gen
#58 AI campaign quality gate
 → validates campaign data before content gen
#52/#63 4-phase AI content agent (LARGEST)
 → research → strategy → creation → review
#64 All content formats (threads, polls, carousels)
#65 Platform content preview
#61 Self-learning content gen
#62 Free/paid user tiers
Political campaigns
```

## Key Reference Files

### Implementation Docs
- `docs/REMAINING-WORK.md` — Full task specs with verification criteria
- `docs/EXECUTION-ORDER.md` — Phase ordering and dependency chains
- `docs/SCHEMA-CHANGES.md` — All DB field additions (Phase C done)
- `docs/FILE-CHANGE-INDEX.md` — File-to-task mapping + conflict map

### Core Code
- `scripts/post.py` — Posting orchestrator (script-first, legacy fallback)
- `scripts/engine/` — JSON posting engine (script_parser, script_executor, selector_chain)
- `scripts/utils/metric_scraper.py` — Per-platform scrapers + Chrome/137 UA
- `scripts/utils/content_generator.py` — AI content gen + FTC disclosure
- `scripts/utils/local_db.py` — Local SQLite (14 tables incl. campaign_posts)
- `scripts/utils/server_client.py` — Server API client (encrypted auth)
- `scripts/utils/session_health.py` — Lockout detection + retry + posting shortcut
- `scripts/background_agent.py` — 6 async tasks + disclaimer_text pass-through
- `server/app/services/billing.py` — Billing with CPM multiplier
- `server/app/models/campaign.py` — Campaign with Phase C fields
- `server/app/models/user.py` — User with Phase C fields
- `server/app/schemas/campaign.py` — API schemas with Phase C fields
- `server/app/routers/auth.py` — Auth + password reset

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login
- **User App**: http://localhost:5222

## Server Auth
- Primary: `dassamaara@gmail.com` / `1304sammy#` (ID 15)
- Test: `amplifier.test@gmail.com` / `Amplifier2026!` (ID 16)
- Auth file: `config/server_auth.json` (encrypted)

## Earnings Estimates (for brand strategy)
| User Type | Daily (4 platforms) | Monthly |
|-----------|--------------------:|--------:|
| New (< 500 followers) | $2-6 | $60-180 |
| Growing (1K-5K) | $8-30 | $240-900 |
| Established (10K+) | $30-120 | $900-3,600 |
| Amplifier tier | 2x above | 2x above |

## Test Commands
```bash
python scripts/user_app.py
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
python scripts/login_setup.py <platform>
vercel deploy --yes --prod --cwd server
```
