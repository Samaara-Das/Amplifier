# Amplifier — Task Context

**Last Updated**: 2026-04-04 (Session 26)

## Current Task

**Task #28 — Verify: Scheduled Posting** (in-progress) — paused during Sessions 24-26 for co-founder docs, codebase audit, and v2/v3 upgrade sprint.

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

## Session 26 — What Was Done (Current Session)

### 1. Full Codebase Audit (Session 25 portion)
Comprehensive audit found major doc discrepancies: route count was "52" in docs (actually ~88), model count was "8" (actually 11), admin dashboard was "6 pages" (actually 14). All docs updated.

### 2. Dan's v2/v3 Analysis
Read both Devtest-Dan repos (amplifire-v2: NestJS+Kotlin+Go 75% done, AmpliFire-v3: Android Phase 1 MVP). Created `docs/AMPLIFIER-SPEC.md` (complete system spec covering all 3 versions) and `docs/V2-V3-UPGRADE-PLAN.md` (15 upgrades across 5 phases).

### 3. v2/v3 Upgrade Implementation (8 commits)

**Phase 1 — Declarative JSON Posting Engine** (`994adcf`)
- `scripts/engine/` — 6 modules: script_parser.py (data models), selector_chain.py (fallback selectors), human_timing.py (per-step delays), error_recovery.py (retry strategies), script_executor.py (13 action handlers)
- `config/scripts/` — 4 JSON posting scripts (x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json)
- `post.py` refactored: `post_to_platform()` tries script-first, falls back to legacy hardcoded functions
- `post_scheduler.py` updated to use unified posting function

**Phase 2 — Financial Safety** (`019a667`)
- `server/app/utils/crypto.py` — AES-256-GCM server-side encryption (PBKDF2 key derivation from ENCRYPTION_KEY env var)
- `scripts/utils/crypto.py` — Client-side encryption (machine-derived key: username+hostname)
- `local_db.py` — API keys (gemini, mistral, groq) auto-encrypted on save, auto-decrypted on read
- Payout model: `amount_cents`, `available_at`, expanded status lifecycle (pending→available→processing→paid|voided|failed), EARNING_HOLD_DAYS=7
- Company/User/Penalty models: `_cents` integer columns alongside legacy Numeric
- `billing.py`: `calculate_post_earnings_cents()`, `promote_pending_earnings()`, `void_earnings_for_post()`

**Phase 3 — Automation & Intelligence** (`4d085de`)
- `scripts/ai/` — AiProvider abstract base, GeminiProvider (model fallback + rate limit tracking), MistralProvider, GroqProvider
- `scripts/ai/manager.py` — AiManager with registry, priority ordering, auto-fallback
- `content_generator.py` refactored to use AiManager (deleted 3 inline provider classes)
- `local_db.py` — post_schedule gains error_code (SELECTOR_FAILED/TIMEOUT/AUTH_EXPIRED/RATE_LIMITED), execution_log, max_retries. classify_error(). Exponential backoff retry (30min * 2^retry_count)
- `payments.py` — `process_pending_payouts()` auto-sends via Stripe Connect

**Phase 5 — Reputation Tiers** (`4d085de`)
- User model gains `tier` (seedling/grower/amplifier) + `successful_post_count`
- TIER_CONFIG: seedling (max 3 campaigns, 1x CPM), grower (max 10, 1x CPM, auto-post), amplifier (unlimited, 2x CPM)
- Auto-promotion in billing after each successful post
- `matching.py` uses tier-based campaign limits
- Admin endpoints: run-earning-promotion, run-payout-processing

**Image Generation Upgrade** (`f840964`)
- `scripts/ai/image_provider.py` — Abstract ImageProvider (text_to_image + image_to_image)
- `scripts/ai/image_manager.py` — ImageManager with 5-provider fallback + auto post-processing
- 5 providers: GeminiImageProvider (500 free/day, img2img support), CloudflareImageProvider, TogetherImageProvider, PollinationsImageProvider, PilFallbackProvider
- `scripts/ai/image_postprocess.py` — UGC pipeline: desaturation (13%), color cast, film grain (sigma=8), vignetting, JPEG at quality 80, EXIF injection (iPhone/Samsung/Pixel metadata)
- `scripts/ai/image_prompts.py` — 8-category photorealism prompt framework with randomized pools, negative prompt

**Campaign Image Pipeline Fix** (`168137d`)
- Critical gap found: campaign product images were stored in assets dict through the whole chain but NEVER actually used for image generation. All images were generic txt2img.
- Fixed: `_download_campaign_product_images()` downloads ALL product images from assets.image_urls
- `generate_daily_content()` now calls `generate_image(product_image_path=...)` after text generation
- `agent_draft` table gains `image_path` column; `add_draft()` stores it; `_schedule_draft()` passes it through

**Daily Image Rotation** (`bc7b433`)
- `_pick_daily_image(images, day_number)` rotates through multiple campaign product photos: Day 1 → image 0, Day 2 → image 1, wraps around
- Maximizes value of multiple campaign assets without needing multi-image compositing

### Key Decisions This Session
- local-dream (on-device SD1.5 for Android) rejected: CC-BY-NC-4.0 non-commercial license + Android-only
- Our FastAPI server + Playwright engine stays — adopt v2/v3 PATTERNS, not their stacks
- Gemini Flash Image as primary image provider (500 free/day, best quality, supports img2img)
- Integer cents for all money (industry standard, consistent with Stripe)
- 7-day earning hold period before payout (fraud prevention window)
- Three-tier reputation system (Seedling→Grower→Amplifier) with auto-promotion

## Remaining Blockers (Priority Order)
1. Posting URL capture broken on LinkedIn/Facebook/Reddit (Task #28)
2. Metric scraping unverified E2E (Tasks #29-30)
3. Billing unverified E2E (Tasks #31-32)
4. X account detection risk (locked during testing)
5. Real Stripe payments (both sides) — company deposit + creator withdrawal
6. FTC disclosure (#ad/#sponsored) not in content generator
7. Distribution — no installable app yet (Tauri or web planned)

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
- `docs/AMPLIFIER-SPEC.md` — Complete multi-implementation system spec
- `docs/V2-V3-UPGRADE-PLAN.md` — 15 upgrades across 5 phases
- `docs/IMAGE-GENERATION-UPGRADE.md` — Image gen spec (txt2img, img2img, post-processing)

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
