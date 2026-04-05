# Amplifier — Task Context

**Last Updated**: 2026-04-05 (Session 29-30)

## Current Task

**Phases A-F COMPLETE. Deployed to production.** 67/80 tasks done. 13 remaining are Phase D/E AI features.

## Task Progress Summary

| Phase | Focus | Tasks | Status |
|-------|-------|-------|--------|
| A Foundation | URL capture, metrics, billing, earnings, Stripe | #28-#38 | All done |
| B Security | CSRF, lockout, reset, encryption, FTC | #66-#76 | All done |
| C Schema | DB migrations for Tier 4 | — | Done |
| D Features | Repost, quality gate, subscriptions | #58, #62, #68 | Done |
| D Features | AI scrapers, content agent, formats | #51-#65 | 13 pending |
| E Integrity | Metrics accuracy | #60 | Done |
| F Admin/Polish | Admin dashboard, system tray, UX | #39-#50, #76-#80 | All done |

**67 done, 0 in-progress, 13 pending. 80 total tasks.**

## Session 30 — What Was Done

### Phase D Progress — 3 features implemented

**#68 Repost Campaigns (3 commits):**
- Server: CampaignPost model, 3 API endpoints (add/list/delete posts), matching includes campaign_posts in CampaignBrief
- Company dashboard: Campaign type toggle (AI Generated/Repost) in wizard, per-platform text editors with char limits
- User app: background_agent skips AI gen for repost campaigns, loads pre-written content from campaign_posts table
- Local DB: upsert_campaign stores campaign_type/goal/tone/disclaimer_text + repost_content

**#58 Quality Gate:**
- `server/app/services/campaign_quality.py` — 8-rubric scoring (brief length, guidance, payout rates, targeting, assets, title, dates, budget)
- Blocks activation below 85/100, returns actionable feedback
- Integrated into campaign status update in campaigns.py

**#62 Free/Pro Subscription Tiers:**
- SUBSCRIPTION_TIERS config in billing.py (free: 4 posts/day, pro: $19.99/mo, 20 campaigns, image gen)
- `get_effective_max_campaigns()` combines reputation + subscription limits
- User model/schema updated with subscription_tier field

### Phase E — Metrics Accuracy (#60)
- Anomaly detection: `_check_metric_anomaly()` flags 10x+ jumps, `anomaly_flag` column
- Deleted post detection: all 6 scrapers detect platform-specific deletion phrases
- Rate limit detection: CAPTCHA detection, consecutive limit counter, platform skip after 3 hits
- `update_post_status()` marks posts as "deleted", excluded from future scraping

### Phase F — Admin + Support Verified
- All 12 admin pages verified via Chrome DevTools on deployed server (overview, users, companies, campaigns, financial, fraud, analytics, review, settings, audit)
- System tray notifications already integrated in background_agent
- Tasks #39-50, #76-80 marked done

### Deployment Fixes (Critical)

**Root cause: Supabase PostgreSQL missing columns.** SQLAlchemy `create_all()` auto-creates on local SQLite but doesn't ALTER existing tables on PostgreSQL. Multiple columns added to models over sessions but never migrated on Supabase.

**Columns added to Supabase via psycopg2 ALTER TABLE:**
- users: `tier`, `successful_post_count`, `earnings_balance_cents`, `total_earned_cents`, `scraped_profiles`, `ai_detected_niches`, `last_scraped_at`, `zip_code`, `state`, `political_campaigns_enabled`, `subscription_tier`
- companies: `balance_cents`, `status`
- campaigns: `campaign_goal`, `campaign_type`, `tone`, `preferred_formats`, `disclaimer_text`
- payouts: `amount_cents`, `available_at`
- penalties: `amount_cents`
- campaign_assignments: `content_mode`, `payout_multiplier`, `assigned_at`
- posts: `status`
- New table: `campaign_posts`

**Python 3.12 forward reference crash:** `CampaignPostResponse` defined after `CampaignBrief` which references it. Python 3.14 handles this via lazy evaluation but 3.12 (Vercel) crashes. Fixed by moving class definition before usage.

**Other deploy fixes:**
- Skip `init_tables()` on Vercel (VERCEL env var check)
- JSON global exception handler for debugging
- Billing page dev-mode top-up form when Stripe not configured
- Removed accidentally committed `.env.prod` with secrets

### Vercel Deploy Notes
- Must be logged in to correct Vercel account (`araamas` not `kingsdxb2025`)
- Project: `araamas-projects/server` linked via `.vercel/project.json`
- Deploy command: `cd server && vercel deploy --yes --prod`
- Python 3.12 specified in `.python-version`
- Supabase migrations must be run manually via psycopg2 (not auto-created)

## Remaining Tasks (13)

```
#51  AI profile scraping (Browser Use / AI vision)
#52  Sophisticated AI content generation
#53  Update SLC spec (docs)
#54  Write automated tests
#55  Flux.1 image generation
#56  Video generation integration
#57  Official social media APIs
#59  AI browser agent for profile scraping
#61  Self-learning content gen
#63  4-phase AI content agent
#64  Content formats (threads, polls, carousels)
#65  Platform content preview UI
```

## Key Lessons Learned

1. **Always test on deployed server, not just local** — SQLite masks PostgreSQL schema issues
2. **Run Supabase migrations manually** — `create_all()` doesn't ALTER existing tables
3. **Python 3.12 vs 3.14** — forward references in type hints behave differently
4. **Vercel account matters** — wrong account = wrong project = deploy to wrong URL
5. **Chrome DevTools MCP for self-verification** — don't claim "works" without visual proof on deployed

## Key Reference Files

- `server/app/main.py` — FastAPI entry + JSON exception handler
- `server/app/core/database.py` — Supabase connection (SSL, NullPool, pgbouncer)
- `server/app/schemas/campaign.py` — CampaignPostResponse BEFORE CampaignBrief
- `server/app/services/campaign_quality.py` — Quality gate (85/100 threshold)
- `server/app/services/billing.py` — SUBSCRIPTION_TIERS + CPM multiplier
- `server/app/models/campaign_post.py` — Repost campaign posts
- `scripts/utils/metric_scraper.py` — Anomaly detection, deleted post handling
- `scripts/background_agent.py` — Repost campaign support

## Deployed URLs
- **Production**: https://server-five-omega-23.vercel.app
- **Company dashboard**: /company/login
- **Admin dashboard**: /admin/login (password: admin, cookie: admin_token=valid)
- **User App**: localhost:5222

## Server Auth
- Primary: `dassamaara@gmail.com` / `1304sammy#` (ID 15)
- Company test: `amplifier.testco@gmail.com` / `TestCo2026!`
- Auth file: `config/server_auth.json` (encrypted)

## Test Commands
```bash
python scripts/user_app.py
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd server && vercel deploy --yes --prod
python scripts/login_setup.py <platform>
```
