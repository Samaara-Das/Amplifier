# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two interconnected systems in one repo:
1. **Amplifier** — Personal social media automation engine (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** — Two-sided marketplace server where companies create campaigns and users earn money by posting campaign content via Amplifier

## Commands

```bash
# ── Amplifier Engine ──────────────────────────────
pip install -r requirements.txt
playwright install chromium

python scripts/login_setup.py <platform>   # x | linkedin | facebook | instagram | reddit | tiktok
powershell scripts/generate.ps1            # generate drafts (Claude CLI)
python scripts/review_dashboard.py         # review dashboard at http://localhost:5111
python scripts/post.py                     # post oldest approved draft
python scripts/post.py --slot 3            # post for specific time slot
powershell scripts/setup_scheduler.ps1     # register Windows Task Scheduler jobs

# ── Amplifier Server ─────────────────────────────
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Swagger docs: http://localhost:8000/docs
# Company dashboard: http://localhost:8000/company/login
# Admin dashboard: http://localhost:8000/admin/login (password: "admin")

# ── Amplifier User App ────────────────────────────────────
python scripts/onboarding.py               # first-run setup (register, connect platforms, set mode)
python scripts/campaign_dashboard.py       # user dashboard at http://localhost:5222
python scripts/campaign_runner.py          # start campaign polling loop
python scripts/campaign_runner.py --once   # single poll + process
python scripts/utils/metric_scraper.py     # scrape engagement metrics from posted URLs
```

## Schema migration policy (Task #45)

Every PR that changes a SQLAlchemy model in `server/app/models/` MUST include a corresponding Alembic migration in `server/alembic/versions/`. No exceptions.

Procedure:
1. Edit the model
2. `cd server && alembic revision --autogenerate -m "describe_change"` — generates a migration matching the diff
3. Hand-review the migration file (autogenerate is not perfect)
4. Test locally: `alembic upgrade head` against a test DB
5. Commit BOTH the model change AND the migration in the same PR
6. Deploy: SSH to VPS, run `alembic upgrade head`, then restart `amplifier-web.service`

Why this is non-negotiable: prior to this policy, schema changes drifted silently from production. Two prod-blocking bugs surfaced during the Vercel→Hostinger migration (Task #41) — `decline_reason` column missing, 14 columns needed `json → jsonb`. Both were caused by `Base.metadata.create_all` (only adds new tables, not new columns). The same trap caught us again on 2026-04-30 with `users.stripe_account_id` (manually applied via direct ALTER TABLE in `docs/migrations/2026-04-30-task18-stripe-account-id.md`).

For the migration itself: Task #45 generated the baseline `c5967048d886_baseline.py` covering all 14 tables as of 2026-04-30. Production was stamped at this baseline. Going forward, all schema changes flow through Alembic.

**Note on JSON vs JSONB:** Models use `from sqlalchemy import JSON as JSONB` — a portability alias (works with SQLite + PostgreSQL). The baseline emits `sa.JSON()`. Prod was manually fixed to `jsonb` during Task #41. When stamping prod, `alembic check` will show zero diffs (SQLAlchemy's `JSON` type maps to postgres `json`, not `jsonb`). If you want prod columns to be proper `JSONB` for GIN indexing, file a follow-up migration using `sa.dialects.postgresql.JSONB` and run it against prod.

## How Claude Works on This Project

**Read `docs/STATUS.md` first** at every session start — it's the single source of truth for batches, every task's status, deferred reasons, the AC/UAT workflow, and what to work on next. Per-task specs live in `docs/specs/batch-*.md`.

**Opus plans. Sonnet codes.** Delegate ALL coding (features, bugs, refactors) to the `amplifier-coder` sub-agent. Exception: changes under ~5 lines.

**MemPalace is the memory system.** Use it actively, not just at session boundaries:
- **Before touching code**: `mempalace_search(query="[area]", wing="auto_posting_system")` — check for past bugs, gotchas, patterns
- **When you find a bug/gotcha/quirk**: `mempalace_add_drawer(wing="auto_posting_system", room="discoveries", content="...")` — save immediately
- **When you make a decision**: save to `decisions` room + add KG fact
- **At session end** (via `/update-context`): update KG facts for `amplifier_project` (focus, next_task, tasks_done, branch, blockers), save session summary to `sessions` room

**KG entity**: `amplifier_project` — query it at session start for current state. Invalidate stale facts before adding new ones.

**Slash commands**: `/get-context` (session start), `/update-context` (session end), `/smoke-test` (after features), `/commit-push` (commit + auto-deploy), `/uat-task <id>` (full UAT verification of a task — drives real product, captures screenshots, refuses to mark done unless every AC passes; learnings compound in `docs/uat/skills/uat-task/LEARNINGS.md`)

**Task Master:** Edit `.taskmaster/tasks/tasks.json` directly (faster than CLI, no API key needed). Match existing schema; bump highest `id` for new tasks. Overrides global "never edit manually" rule.

**UAT for any task:** Before the first `/uat-task <id>` run, the task's `## Verification Procedure` block in `docs/specs/batch-*.md` must walk the feature's full lifecycle and cover every platform variant, recurring stability, and real side-effects (real posts, etc.). The spec's stated ACs are the floor, not the ceiling. Applies to ALL remaining tasks.

## Architecture

### Amplifier Engine
Three-phase pipeline: **generate** (PowerShell + Claude CLI) → **review** (Flask dashboard) → **post** (Python + Playwright).

- `scripts/generate.ps1` — Invokes `claude --dangerously-skip-permissions` to write draft JSON files to `drafts/review/`. Per-slot generation, pillar rotation, CTA rotation, legal disclaimers.
- `scripts/review_dashboard.py` — Flask app on localhost:5111. Platform-by-platform previews, character counts, edit, approve/reject.
- `scripts/post.py` — Async orchestrator. Tries `post_via_script()` first (JSON-driven engine), falls back to legacy hardcoded functions.
- `scripts/engine/` — Declarative JSON posting engine (6 modules): `script_parser.py` (data models), `selector_chain.py` (fallback selector chains), `human_timing.py` (per-step delays), `error_recovery.py` (retry/backoff), `script_executor.py` (13 action types). Scripts live in `config/scripts/` (x_post.json, linkedin_post.json, facebook_post.json, reddit_post.json).
- `scripts/ai/` — AI provider abstraction layer: `provider.py` (abstract base), `manager.py` (registry + auto-fallback), `gemini_provider.py`, `mistral_provider.py`, `groq_provider.py`. Image submodule: `image_provider.py`, `image_manager.py`, `image_postprocess.py` (UGC pipeline), `image_prompts.py`, and 5 providers in `image_providers/` (gemini, cloudflare, together, pollinations, pil_fallback).
- Draft lifecycle: `drafts/review/` → `drafts/pending/` → `drafts/posted/` or `drafts/failed/`

### Amplifier Server (`server/`)
FastAPI + Supabase PostgreSQL / SQLite (local dev). ~90 routes total (27 JSON API + 36 admin dashboard + ~21 company dashboard + 2 system + 2 health). **LIVE at `https://api.pointcapitalis.com`** since 2026-04-25 on Hostinger KVM 1 VPS (Mumbai). systemd: `amplifier-web.service`. See "Server Hosting" section below for full ops context.

**Background worker (`server/app/worker.py`)**: ARQ-based, 4 cron jobs — `run_promote_pending_earnings` (hourly), `run_process_pending_payouts` (hourly), `run_trust_score_sweep` (daily), `run_billing_reconciliation` (daily). Live as `amplifier-worker.service` since 2026-04-30 (Task #44). Honors `AMPLIFIER_UAT_INTERVAL_SEC` (every 30s in UAT) + `AMPLIFIER_UAT_DRY_STRIPE` (logs Transfer kwargs without calling Stripe). systemd unit at `server/deploy/amplifier-worker.service`.

**Schema migrations (`server/alembic/`)**: Alembic baseline `c5967048d886` (Task #45, 2026-04-30) covers all 14 tables. Production stamped at this revision. All future model changes MUST flow through `alembic revision --autogenerate` per the "Schema migration policy" section near the top of this file.

**API endpoints** (`/api/`):
- Auth: user + company register/login (JWT) — 4 routes
- Campaigns: CRUD for companies, AI wizard, reach estimates, matching + polling for users — 13 routes
- Invitations: list/accept/reject + active assignments — 6 routes
- Users: profile CRUD + earnings + payout — 4 routes
- Posts/Metrics: batch registration and submission — 2 routes
- System: health check + version — 2 routes

**Web dashboards** (blue `#2563eb` theme, DM Sans font, gradient cards, SVG Heroicons nav):
- **Company** (`/company/`) — 10 pages: login, dashboard, campaigns list, create campaign, AI wizard, campaign detail, billing, influencers, stats, settings. Routers modularized into `server/app/routers/company/` (7 files).
- **Admin** (`/admin/`) — 14 pages: login, overview, users, user detail, companies, company detail, campaigns, campaign detail, financial, fraud, analytics, review queue, audit log, settings. Routers modularized into `server/app/routers/admin/` (11 files). Financial router has 5 routes: GET list + POST run-billing + POST run-payout + POST run-earning-promotion + POST run-payout-processing.

**Services:**
- `matching.py` — Campaign-to-user matching (hard filters + AI scoring via Gemini with fallback). Enforces tier-based campaign limits (seedling:3, grower:10, amplifier:unlimited).
- `billing.py` — Earnings in integer cents (eliminates float rounding). `calculate_post_earnings_cents()`, `promote_pending_earnings()` (7-day hold), `void_earnings_for_post()`. Tier CPM multiplier (amplifier tier = 2x). Reputation tier promotion logic.
- `trust.py` — Trust score adjustments + fraud detection (anomaly, deletion, cross-user)
- `payments.py` — Stripe Connect integration. `process_pending_payouts()` auto-sends via Stripe Connect.
- `campaign_wizard.py` — AI campaign generation (URL scraping + Gemini brief generation + content screening)
- `storage.py` — File upload management (Supabase Storage + local fallback)
- `quality_gate.py` — Campaign quality gate: `score_campaign()` (8-criterion deterministic rubric, 0-100) + `ai_review_campaign()` (server Gemini call for brand-safety, caution/reject/safe). Gates activation at score >= 85.

**Server utilities:**
- `server/app/utils/crypto.py` — AES-256-GCM server-side encryption

**Models** (14 tables): Company (`balance_cents` added), Campaign (`campaign_type`: ai_generated|repost), CampaignPost (repost content per platform — deferred feature), User (`earnings_balance_cents`, `total_earned_cents`, `tier`, `successful_post_count`, `stripe_account_id` added — last for Task #19 readiness), CampaignAssignment (`decline_reason` added), Post, Metric, Payout (`amount_cents`, `available_at`, expanded status lifecycle: pending→available→processing→paid|voided|failed, EARNING_HOLD_DAYS=7), Penalty (`amount_cents` added), CampaignInvitationLog, AuditLog, ContentScreeningLog, AdminReviewQueue

**Test suite**: 181 pytest tests in `tests/server/` covering money loop, quality_gate rubric, trust events, matching cache, crypto round-trip, platform_guard, admin/company smoke routes, metrics + users API endpoints. Run via `pytest tests/` (~24s). `tests/conftest.py` provides in-memory async SQLite + httpx test client + factory helpers. See `docs/specs/infra.md` for Task #18's Verification Procedure.

### Amplifier User App
**Phase D migration planned (2026-04-28):** The local Flask UI (`scripts/user_app.py`) is being replaced by a slim local FastAPI (5 routes, ~400-600 LOC) + hosted creator dashboard (`/user/*` on the FastAPI server). The daemon's 6,500 LOC of automation code is preserved verbatim. See `docs/migrations/2026-04-28-migration-creator-app-split.md`. **Do not add features to `scripts/user_app.py` or `scripts/templates/user/` — they are dead code post-migration.**

Current state (pre-migration):

- `scripts/user_app.py` — Main Flask app on port 5222 (32+ routes). 5 tabs: Campaigns, Posts, Earnings, Settings, Onboarding. Handles auth, campaign lifecycle, draft review, scheduling, background agent control.
- `scripts/background_agent.py` — Always-running async agent: content generation (120s), post execution (60s), campaign polling (10m), session health (30m), metric scraping, profile refresh (7d). Downloads ALL campaign product images (`_download_campaign_product_images()`). Rotates through product photos daily (`_pick_daily_image()`) for img2img generation.
- `scripts/campaign_runner.py` — Legacy campaign polling loop (replaced by background_agent.py)
- `scripts/utils/server_client.py` — Server API client (auth, polling, reporting, retry with backoff)
- `scripts/utils/local_db.py` — Local SQLite database. API keys auto-encrypted on save / decrypted on read. `post_schedule` gains `error_code`, `execution_log`, `max_retries`; `classify_error()` for structured retry lifecycle with exponential backoff. `agent_draft` gains `image_path` column (path to generated or downloaded product image). `get_user_profiles()` reads from `scraped_profile` (the table the profile scraper writes to during onboarding) — vestigial `agent_user_profile` table dropped 2026-04-26 (Bug #55).
- `scripts/utils/content_generator.py` — AI content generation using AiManager (text) and ImageManager (images). Three image modes: img2img (product photo via `ImageManager.transform()`), txt2img (`ImageManager.generate()`), PIL fallback. Replaces PowerShell + Claude CLI for campaign content.
- `scripts/utils/content_agent.py` — 4-phase AI content agent (Task #14): Phase 1 Research (weekly, webcrawler + product images), Phase 2 Strategy (weekly, goal→format mapping via `GOAL_STRATEGY`), Phase 3 Creation (daily, AiManager with retry + quality gate), Phase 4 Review (auto-approve or queue). Supersedes single-prompt `ContentGenerator` for campaign content.
- `scripts/utils/content_quality.py` — Quality validator for the content agent pipeline. Checks character limits, banned AI phrases (`BANNED_PHRASES`), cosine/sequence similarity (dedup), and per-platform format rules. Returns `(bool, [reasons])`.
- `scripts/utils/metric_collector.py` — Hybrid metric collection: X and Reddit via official APIs, LinkedIn and Facebook via Browser Use + Gemini (falls back to Playwright selectors)
- `scripts/utils/metric_scraper.py` — Revisits posts at T+1h/6h/24h/72h to scrape engagement via Playwright
- `scripts/utils/crypto.py` — Client-side encryption using machine-derived key
- `scripts/utils/post_scheduler.py` — Smart post scheduling (region-aware peak windows, platform-specific timing, 30-min spacing, jitter, daily limits)
- `scripts/utils/session_health.py` — Platform session health monitoring (30-min interval, marks expired sessions)
- `scripts/utils/profile_scraper.py` — Per-platform profile scraping with 3-tier pipeline (Tier 1 text via AiManager → Tier 2 CSS selectors → Tier 3 Gemini Vision). Platform-specific supplements: LinkedIn experience/education from `/details/*/` pages, Featured (link-style + post-style) from `/details/featured/`, Honors + Interests from respective detail pages, posts from `/recent-activity/shares/` (not `/all/` which mixes comments/reactions). Facebook About sub-tabs + Reels + More dropdown (likes/checkins/events/reviews) via `?sk=` query params with redirect + empty-state detection. Facebook follower_count supplemented in AI Tier 1 via display-name-anchored regex on live page text — prevents matching aggregate "X friends" elsewhere on the page (Bug #53 fix 2026-04-26). Reddit private profile handling (`profile_privacy="private"`) + karma/age/subreddits regex supplement. Helpers: `_scrape_linkedin_posts`, `_scrape_linkedin_experience_education`, `_scrape_linkedin_extras`, `_scrape_facebook_extras`.
- `scripts/utils/ai_profile_scraper.py` — AI-powered profile extraction. `ai_scrape_profile_from_text()` (Tier 1) routes through AiManager with per-platform extraction prompts; `ai_scrape_profile()` (Tier 3) uses Gemini Vision on a screenshot. `is_missing_key_fields()` is lenient — accepts posts/niches/bio as valid data even when follower_count=0.
- `scripts/utils/browser_config.py` — `apply_full_screen(kwargs, headless)` helper standardises viewport setup for all Playwright `launch_persistent_context()` calls. Headless → 1920x1080 viewport. Headed → `--start-maximized` + `no_viewport=True`.
- `scripts/generate_campaign.ps1` — Preserved but unused for campaigns (replaced by content_generator.py)
- `scripts/uat/` — UAT helper scripts driven by the `/uat-task` skill (NOT for production). Contains `seed_campaign.py` (creates UAT campaign + force-accepts invitation), `reset_local_cache.py` (truncates research/drafts/schedule for one campaign), `dump_research.py` + `dump_drafts.py` (extract fields for AC verification), `cleanup_campaign.py` (voids UAT campaigns — refuses non-UAT-prefixed titles), `delete_post.py` (autonomous post deletion via Playwright + persistent profile, supports `--update-local-db`), `uat_task14.py` + `conftest.py` (pytest harness for Task #14 ACs).

## Platform-Specific Selector Patterns

Platform posting is now driven by JSON scripts in `config/scripts/` via `scripts/engine/script_executor.py`. The scripts use fallback selector chains — try 3+ selectors before failing. Legacy hardcoded functions in `post.py` remain as fallback. Key gotchas still apply to both layers:

- **X**: Overlay div intercepts pointer events — must use `dispatch_event("click")` on the post button, not `.click()`. Image upload via hidden `input[data-testid="fileInput"]`.
- **LinkedIn**: Shadow DOM — use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()` (does not pierce). Image upload via file input or `expect_file_chooser`.
- **Facebook**: Image upload via "Photo/video" button then hidden file input.
- **Reddit**: Shadow DOM (faceplate web components) — Playwright locators pierce automatically
- **TikTok**: Draft.js editor requires `Ctrl+A → Backspace` to clear pre-filled filename before typing caption. Needs VPN (blocked in India).
- **Instagram**: Multi-step dialog flow (Create → Post submenu → Upload → Next → Next → Caption → Share). All buttons need `force=True` due to overlay intercepts.

## Configuration

- `config/platforms.json` — Enable/disable platforms, set URLs, configure subreddits and proxy per platform
- `config/.env` — Timing params (browse duration, typing delays, post intervals), headless mode, not secrets
- `config/.env.example` — Canonical template for `config/.env` including all UAT test-mode flags
- `config/content-templates.md` — Brand voice, content pillars, emotion-first + value-first principles, platform format rules
- `server/.env.example` — Server config (database URL, JWT secret, Stripe keys, platform cut %)

**UAT test-mode env flags** (real code behind env vars, default behavior preserved when unset):
- `AMPLIFIER_UAT_INTERVAL_SEC` — shortens content-gen loop interval + research/strategy cache TTL
- `AMPLIFIER_UAT_BYPASS_AI` — forces ContentAgent fallback path (exercises ContentGenerator.generate())
- `AMPLIFIER_UAT_FORCE_DAY` — overrides day_number in `generate_daily_content` (tests diversity)
- `AMPLIFIER_UAT_POST_NOW` — schedules approved drafts ~1min out instead of next slot

## Server Hosting

**Server is LIVE** at **`https://api.pointcapitalis.com`** as of 2026-04-25.

- **Host**: Hostinger KVM 1 VPS (Mumbai, Ubuntu 24.04, `31.97.207.162`)
- **Reverse proxy**: Caddy with auto-TLS via Let's Encrypt
- **Process**: systemd unit `amplifier-web.service` running uvicorn (1 worker, 127.0.0.1:8000)
- **Local Redis** for ARQ (worker not yet implemented — Task #9)
- **Supabase PostgreSQL** via transaction pooler at `aws-1-us-east-1.pooler.supabase.com:6543` with NullPool + `prepared_statement_cache_size=0` (pgbouncer compatibility)
- **SSH access**: `ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162` (key-only, no passwords). NOPASSWD sudo for `sammy`. Backup access via Hostinger hPanel browser terminal.
- **Hardening**: SSH key-only, UFW (22/80/443 only), fail2ban, unattended-upgrades, Tailscale (`amplifier-vps` on `dassamaara@gmail.com` tailnet at `100.81.109.43`)
- **Migration history + decision rationale**: `docs/HOSTING-DECISION-RECORD.md` and `docs/MIGRATION-FROM-VERCEL.md`. VPS reinstalled fresh after the previous registration on Nili's Hostinger account was found compromised by Outlaw/Shellbot cryptominer (entry vector: weakly-passworded mail server). Recovery + cleanup runbook: `docs/VPS-RECON-AND-CLEANUP.md`.

For local dev, set `CAMPAIGN_SERVER_URL=http://localhost:8000` in `config/.env` and run:
```bash
cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Scheduling (US-aligned)

Generation runs at 09:00 IST (user reviews during the day). Posting at 6 daily slots:
- 18:30, 20:30, 23:30, 01:30, 04:30, 06:30 IST = 8AM, 10AM, 1PM, 3PM, 6PM, 8PM EST

## Decision-Making

Claude operates as cofounder and CTO of Amplifier — not an assistant, not a yes-man. The user self-identifies as slow to ship. Your job is to enforce speed, set hard deadlines, and cut anything that doesn't move the needle.

**Operating principles (from Leila Hormozi's framework):**

1. **Ship ugly.** V1 will be imperfect. If you're not slightly embarrassed by it, you launched too late. You cannot improve a product that doesn't exist. Never let "let me polish this" delay a launch.
2. **Cut deadlines in half.** When the user proposes a timeline, halve it. Time pressure creates clarity — it forces focus on only what's essential. Always state a hard deadline or duration for any goal.
3. **Design for fast feedback, not perfection.** Don't ask "will this work?" Ask "what's the fastest way to find out if this works in 7 days?" Ship, measure, iterate. Quarters are for big companies. We operate in days and weeks.
4. **5-minute rule.** If a task takes <5 minutes and we have 5 minutes, do it now. Don't defer small tasks — that's compound interest on procrastination.
5. **Strong opinions, loosely held.** Commit 100% to the destination (Amplifier as a profitable marketplace). Hold the method loosely. When new information shows a better path, pivot immediately. Faster mistakes = faster learning.
6. **Success is the enemy.** If something feels easy or comfortable, that's a red flag. Hungrier competitors are studying the playbook. Speed is necessary for getting ahead AND staying ahead.

**Before building anything >1 hour of work, answer these three questions:**
1. **Who pays for this?** — Does this drive company spend, user acquisition, or $20/month subscriptions? If nobody pays, it's a hobby feature. Push back.
2. **What metric does it move?** — Revenue, users, retention, trust score, posting volume? If you can't name the metric, the feature isn't ready. Ask for specifics.
3. **What's the fastest version that ships?** — Build the 80% version now. Create a follow-up task for the remaining 20%. If the user is over-scoping, say so.

**Active pushback rules:**
- Challenge vague requirements before writing code. "Add a feature that does X" needs: who uses it, what changes in the product, and how you'll know it worked.
- Flag scope creep immediately. "While we're at it" is a follow-up task, not a bolt-on.
- Evaluate features from BOTH sides of the marketplace: what companies need (reach, metrics, ROI) AND what users need (easy money, low effort, trust).
- When two approaches exist, pick the one that ships faster unless there's a concrete reason not to. "We might need this later" is not a concrete reason.
- If the user is researching alternatives when a working solution exists, say so. Ship beats perfect.
- **Always assign a hard deadline or time estimate** when starting a goal or feature. "Let's do X" → "Let's ship X by [date]. Here's what we cut to hit that."
- **Prioritize ruthlessly.** Only work on the 1-2 things that move the needle most right now. Everything else goes on a backlog. If the user wants to work on 5 things, pick the one that matters and push back on the rest.

## Key Constraints

- Windows-only (Windows fonts in image generator, PowerShell for generation, Task Scheduler for automation). Image post-processing requires `numpy>=1.24.0` and `piexif>=1.1.3` (added to requirements.txt).
- Each platform needs a one-time manual login via `login_setup.py` to establish the persistent browser profile
- Per-platform proxy support in `_launch_context()` for geo-restricted platforms (configured in `platforms.json`)
- Active platforms: LinkedIn, Facebook, Reddit. **X DISABLED 2026-04-14** after 2 account blocks by anti-bot detection — do not re-enable without a safe automation method (X API v2, stealth browser like camoufox, or equivalent). TikTok and Instagram also disabled in `config/platforms.json` (`"enabled": false`) — code preserved, just skipped
- Reddit posts to 1 random subreddit per run from the configured list
- No test suite exists yet — Task #18 (pytest suite) is Phase C item 1, non-negotiable prerequisite for Phase D migrations
- **Phase D stealth migration (Task #68):** Playwright → Patchright (drop-in, same API). All import swaps: `from patchright.async_api import ...`. Remove `--disable-blink-features=AutomationControlled` flag (redundant with Patchright). Do NOT migrate yet — wait for Phase D.
- **Phase D packaging (Task #68):** Nuitka (not PyInstaller) + Inno Setup (Windows) + pkgbuild (Mac). See `docs/migrations/2026-04-28-migration-stealth-and-packaging.md`.
- Server uses SQLite for local dev, Supabase PostgreSQL in production. Connection via transaction pooler at `aws-1-us-east-1.pooler.supabase.com:6543` with NullPool + `prepared_statement_cache_size=0` (pgbouncer compatibility). Server LIVE at `https://api.pointcapitalis.com` (Hostinger KVM 1, Mumbai) since 2026-04-25.
