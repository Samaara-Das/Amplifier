# Amplifier — Status, Batches, Phases, Tasks

> **Snapshot date: 2026-04-29.** This is a derived view. The canonical source is `.taskmaster/tasks/tasks.json`. If this doc is more than a few days old, re-derive from `tasks.json`.

> **Tech stack migration decided (2026-04-28).** After three independent architecture reviews (Claude Desktop, Grok, synthesis), the launch-blocking UI migration is now spec'd in `docs/migrations/`. Three docs: dashboards-htmx-upgrade, creator-app-split, stealth-and-packaging. These supersede Tasks #20, #21, and #54. See "Migration docs" section below.

> **Important — two orthogonal concepts.** A **batch** is a *feature bucket* (what a set of tasks delivers — e.g. "the AI brain"). A **phase** is an *execution stage* (when a task runs in time). They are not the same thing. The 4 batches and 5 phases overlap but are not identical.

---

## How to read this repo

A fresh agent should read in this order:

1. **`docs/STATUS.md`** (this file) — what's done, what's next, what's deferred, the canonical batches and phases
2. **`docs/specs/batch-*.md`** — per-task specs (the 4 product batches). Plus **`docs/specs/infra.md`** — server-side infra task specs (#44 ARQ worker, #45 Alembic baseline) that live outside the batch system.
3. **`docs/migrations/2026-04-28-*.md`** — the three migration docs (Phase D blueprint)
4. **`docs/uat/AC-FORMAT.md`** — Acceptance Criteria + UAT format every spec must follow before `/uat-task <id>` can run it
5. **`CLAUDE.md`** — developer reference: commands, architecture, gotchas, slash commands, decision-making framework
6. **`.taskmaster/tasks/tasks.json`** — canonical task list (68 tasks)

> Note: `docs/specs/user-app-tech-stack.md` is **superseded** by the three migration docs in `docs/migrations/`. Kept for historical context only.

**Execution rule (from feedback 2026-04-18):** Run **phases in order**: A → C → D → E (B is deferred). Within a phase, run tasks in **numeric order** (with one exception in Phase C — see below). **Ignore** task-master's "recommended next" — it reorders by dependency/priority, the user wants predictable forward progress.

---

## Status counts

- **45 done** · **7 pending** · **22 deferred** · 0 in-progress · **74 total**

> **Phase C COMPLETE 2026-04-30** ✅ All 7 items shipped or rationally deferred: #18 pytest, #44 ARQ worker, #45 Alembic baseline, bug-cleanup batch, #27 post URL dedup, #28 ToS gate, #23 DB backup. #24/#25/#26 deferred into Phase D HTMX migration. Pre-launch tests + safety net + legal gate are all in place. Server LIVE at `https://api.pointcapitalis.com`.
- **Server**: ✅ LIVE at `https://api.pointcapitalis.com` (Hostinger KVM 1, Mumbai). Task #41 done 2026-04-25. Deploy via `/commit-push`.
- **Worker**: ✅ LIVE as `amplifier-worker.service` on the same VPS since 2026-04-30 06:17 UTC. 4 cron jobs running.
- **Schema migrations**: ✅ Alembic baseline `c5967048d886` stamped on prod 2026-04-30. All future model changes flow through `server/alembic/versions/`.
- **Active branch**: `flask-user-app`
- **Active platforms**: LinkedIn, Facebook, Reddit. **X is unconditionally disabled** (Task #40 hardcoded guard) after 3 account suspensions.
- **Most recent wins** (2026-04-30 15:15):
  - **Phase C bug cleanup batch DONE** — 7 bugs shipped in one PR: #57 (quality gate empty target_regions), #59 (duplicate /campaigns row), #60 (X hidden from dashboard via filter_disabled), #63 (seed_campaign accept endpoint), #64 (new `POST /api/company/campaigns/assets` Bearer route + seed uses it), #65 (FORCE_DAY → agent_draft.iteration), #73 (gemini-1.5-flash → gemini-1.5-flash-latest). 185 tests pass (+4 new). AC blocks for all 7 in batch-3-product-features.md, infra.md, and new uat-infra.md.
  - **Task #51 DONE** — AC blocks backfilled for #19 (13 ACs covering test-mode + live-mode flow via Stripe MCP) and #22 (8 ACs covering perf, dual-audience hero, CTAs, OG tags, mobile, FAQ). #19 description updated to direct autonomous Stripe MCP setup (no longer blocked on user setup).
- **Most recent wins** (2026-04-30 09:23):
  - **Task #72 REVERTED** — niche-mismatch AI review was wrong-direction. Companies own their targeting decisions; AI doesn't second-guess. Both my new rule AND the original Task #15 targeting check were stripped from `_build_review_prompt()`. AI review now checks only: brief-is-content / harmful-guidance / legitimacy-scam. Verified via post-revert regression check (5/5 fixtures: zero "niche mismatch" / "targeting mismatch" / "audience fit" mentions in any concerns).
  - **Task #18 DONE (extended for migration-readiness)** — 181 tests pass in 24.0s. Round 1 (10:23): 80 tests covering money loop + rubric + trust + cache + cleanup of pre-existing rot. Round 2 (10:50, after user audit): 101 more tests for migration-readiness — `test_crypto.py` (21, AES-GCM round-trip + tampering + key isolation, 96% line coverage), `test_platform_guard.py` (21, X-disable safety guard, 100% coverage), `test_admin_smoke.py` (24, all 14 admin GET routes), `test_company_smoke.py` (19, all 10 company GET routes), `test_metrics_routes.py` (6, daemon→server contract), `test_users_routes.py` (10, profile + earnings + payout). Caught + fixed real bug: `User.stripe_account_id` field was missing (`payments.py` had a TODO since forever). Schema migration applied to prod Supabase before code deploy: `docs/migrations/2026-04-30-task18-stripe-account-id.md`.
- **Active blockers**: #19 needs Stripe Connect setup from user before it can ship.

---

## Migration docs (Phase D blueprint)

Three docs in `docs/migrations/` define the launch-blocking UI/packaging migration. **Do not execute until Phase A and Phase C are complete.** The migrations replace Tasks #20, #21, #54.

| Doc | Scope | Effort |
|---|---|---|
| `2026-04-28-migration-dashboards-htmx-upgrade.md` | Add HTMX + Alpine + Tailwind CDN + Chart.js to existing company/admin Jinja2 templates. New creator dashboard pages (`/user/*`) on the same FastAPI server. **Rejected**: Next.js, React, shadcn/ui. | 5–7 days |
| `2026-04-28-migration-creator-app-split.md` | Split current Flask user app into (a) hosted creator dashboard at `/user/*`, (b) slim local FastAPI on `localhost:5222` for draft review + platform connect + API keys (~400-600 LOC), (c) daemon adds command polling + draft upload. Strips 9 templates and 3,451 LOC of CSS. Daemon's 6,500 LOC of automation code is preserved. **Rejected**: Tauri, Electron, native UI frameworks. | 8–10 days |
| `2026-04-28-migration-stealth-and-packaging.md` | Patchright (drop-in Playwright replacement) for stealth. Nuitka native binary. Inno Setup (Windows) + pkgbuild (Mac) installers. GitHub Releases for distribution + auto-update. **No code signing in v1** — accept SmartScreen/Gatekeeper warnings. **Rejected**: Tauri bundler, PyInstaller, Camoufox (deferred), Electron, Linux installer (deferred). | 5–7 days |

**Total Phase D effort:** 18–24 days.

**Architecture decisions (final, do not re-litigate):**
- Server: FastAPI + SQLAlchemy + Postgres on Hostinger VPS (unchanged)
- Company + Admin UI: Jinja2 + HTMX + Alpine.js + Tailwind CDN
- Creator hosted dashboard: same stack, new `/user/*` routes on same server
- Creator local UI: FastAPI + Jinja2 + HTMX (~400-600 LOC, 5 routes only: auth_callback, connect, keys, drafts, drafts/{campaign_id})
- Creator daemon: Python (existing code preserved verbatim, ~150 LOC additions for command polling + draft upload)
- Stealth: Patchright (Chromium drop-in for Playwright)
- Packaging: Nuitka + Inno Setup (Windows) + pkgbuild (Mac)
- Distribution: GitHub Releases + HTTP version-check auto-update
- Code signing: deferred to post-launch (~$400/yr cost when revenue justifies)

---

## The 4 feature batches (what gets delivered)

Each batch is a `docs/specs/batch-*.md` file. The tasks listed are the ones the spec covers.

### Batch 1 — Money Loop ✅ DONE
**Spec**: `docs/specs/batch-1-money-loop.md`
**What it delivers**: post goes live → URL captured → metrics scraped → billing calculates earnings → user sees money. The full pipeline that lets anyone get paid.

| Task | Title | Status |
|------|-------|--------|
| #1 | Post URL capture (LinkedIn / Facebook / Reddit) | ✅ done |
| #9 | Metric scraping (per-platform, deleted-post detection, rate-limit handling) | ✅ done |
| #10 | Billing (cents-based formula, 7-day hold, tier multiplier, budget cap) | ✅ done |
| #11 | Earnings display + withdrawal | ✅ done |
| #6 | Metrics accuracy (deletion detection, rate-limit handling, dedup) | ✅ done — *also listed in Batch 4 spec* |
| #38 | E2E deleted post detection — full pipeline verification | ✅ done |

### Batch 2 — AI Brain 🔄 IN PROGRESS
**Spec**: `docs/specs/batch-2-ai-brain.md`
**What it delivers**: profile scraping → matching → content agent → quality gate. Amplifier's intelligence layer.

| Task | Title | Status |
|------|-------|--------|
| #13 | AI profile scraping (3-tier: text → CSS → Vision; per-platform extractors) | ✅ done |
| #12 | AI matching (Gemini scoring + niche overlap fallback + caching) | ✅ done |
| #14 | 4-phase content agent (Research → Strategy → Creation → Review) | ✅ done — first all-green `/uat-task` run 2026-04-26 |
| #15 | AI campaign quality gate (rubric + AI review on activation) | ✅ done 2026-04-29 — 14/14 ACs PASS via `/uat-task 15`. Provider fallback chain Gemini → Mistral → Groq, hard-fail criteria, HTTP-header test-mode flags |

### Batch 3 — Product Features ⚠️ MIXED
**Spec**: `docs/specs/batch-3-product-features.md`
**What it delivers**: rich content formats, better invitation UX, repost campaigns, admin payout tools.

| Task | Title | Status |
|------|-------|--------|
| #5 | Invitation UX — countdown timers, expired badge, decline reason | ✅ done |
| #7 | Repost campaign — company creation, frequency, user display | ⏸ deferred (post-launch) |
| #8 | Admin payout void / force-approve actions | ✅ done |
| #16 | Content formats — LinkedIn polls, Facebook photo albums, Reddit link posts (X threads/polls deferred per Task #40) | ⏸ deferred 2026-04-18 (post-launch) |

### Batch 4 — Business Launch 📋 PENDING
**Spec**: `docs/specs/batch-4-business-launch.md`
**What it delivers**: live Stripe (companies pay in, users get paid out), public landing page.

| Task | Title | Status |
|------|-------|--------|
| #17 | Free/Pro user subscription tiers ($19.99/mo) — Stripe subscription | ⏸ deferred 2026-04-29 (post-traction monetization, not MVP) |
| #19 | Stripe live integration — company Checkout + user Connect Express | 📋 pending (blocked: Stripe setup; deps `#2`, `#10`; needs AC block via Task #51) |
| #22 | Landing page — public-facing acquisition site | 📋 pending (links to new installer from migration; needs AC block via Task #51) |

### ~~Architecture spec~~ → Superseded by migration docs
Previous: `docs/specs/user-app-tech-stack.md` (Tauri vs Electron vs status-quo Flask analysis).
**Replaced by** the three migration docs above. Tasks #20 (PyInstaller), #21 (Mac), #54 (revisit decision) are **superseded** — see Phase D below.

---

## The 5 execution phases (when tasks run, in order)

Per feedback 2026-04-18. Run A → C → D → E. **B is deferred entirely.**

### Phase A — AI Brain finish 🔄
- ✅ #14 (4-phase content agent — done 2026-04-18, re-verified 2026-04-26)
- 📋 **#15 (AI campaign quality gate)** ← *next task to start* (needs AC block via #50 first)

### Phase B — Content formats ⏸ DEFERRED
- ⏸ #16 deferred 2026-04-18 — text + image already work on all 3 active platforms; format expansion is post-launch quality-of-life.

### Phase C — Product tail 📋
**Modified order (2026-04-28): pull #18 first.** Without test coverage, the Phase D migration breaks things invisibly. Bug #53 (Facebook follower count regression) and the disappearing Next-button fix are exactly the kind of regressions a pytest suite catches.

Run in this order:
1. ~~**#18 Automated test suite (pytest)**~~ ✅ done 2026-04-30 — 181 tests pass in 24.0s (extended for migration-readiness). Migration safety net in place.
2. ~~**#44 ARQ worker entrypoint**~~ ✅ done 2026-04-30 11:17 — 9/10 ACs PASS. Worker live on VPS systemd. Unblocks Phase D Stripe.
3. ~~**#45 Alembic baseline migration**~~ ✅ done 2026-04-30 11:42 — 7/7 ACs PASS. Baseline `c5967048d886` covers 14 tables. Prod stamped. CLAUDE.md policy enforces forward migrations.
4. ~~Bug cleanup batch (carry-overs from `/uat-task 14`): #57, #59, #60, #63, #64, #65, #73~~ ✅ done 2026-04-30 (one bundled PR, 185 tests pass, AC blocks for all 7).
5. ~~#27 Server-side post URL dedup~~ ✅ done 2026-04-30 18:17 — 4/4 ACs PASS via `/uat-task 27` (3 pytest + 1 prod curl smoke). 188 tests pass. Report: `docs/uat/reports/task-27-2026-04-30-1817.md`.
6. ~~#28 ToS + privacy policy acceptance in registration~~ ✅ done 2026-04-30 18:42 — 5/5 ACs PASS via `/uat-task 28`. Alembic migration `a1b2c3d4e5f6` applied to prod. /terms + /privacy live. Report: `docs/uat/reports/task-28-2026-04-30-1842.md`.
7. ~~#23 DB backup~~ ✅ done 2026-04-30 18:56 — 3/3 ACs PASS via `/uat-task 23`. Online SQLite `.backup()` API + 6h interval in daemon main loop. Report: `docs/uat/reports/task-23-2026-04-30-1856.md`. **#24/#25/#26 DEFERRED 2026-04-30** — they target dead Flask user-app templates that get ripped up in Phase D. Requirements folded into `docs/migrations/2026-04-28-migration-dashboards-htmx-upgrade.md` (Polish requirements section).

**Skipped from Phase C** (replaced by Phase D migration docs):
- ~~#20 PyInstaller packaging~~ → superseded by `2026-04-28-migration-stealth-and-packaging.md` (Nuitka, not PyInstaller)
- ~~#21 Mac support~~ → superseded by same migration doc (cross-platform handled in Nuitka build matrix)
- ~~#22 Landing page~~ → moved to Phase E (links to the new installer, must come after migration)

### Phase D — Tech Stack Migration + Money 📋
**This phase is launch-blocking.** Execute the three migration docs in order, in parallel with Stripe setup.

| Order | Item | Source |
|---|---|---|
| 1 | Dashboards HTMX upgrade | `docs/migrations/2026-04-28-migration-dashboards-htmx-upgrade.md` |
| 2 | Creator app split | `docs/migrations/2026-04-28-migration-creator-app-split.md` |
| 3 | Stealth + packaging | `docs/migrations/2026-04-28-migration-stealth-and-packaging.md` |
| Parallel | #19 Stripe live integration | `docs/specs/batch-4-business-launch.md` (touches FastAPI backend only — independent of UI migrations) |
| Parallel | #70 BYOK — companies bring their own AI API keys | `C:\Users\dassa\.claude\plans\do-the-remaining-ux-atomic-biscuit.md` (W9) — new `company_api_keys` table, AES-encrypted, quality gate + wizard check company keys first |

**Sequencing rationale:** Dashboards must come first because the creator-app-split's hosted creator pages (`/user/*`) depend on the new `base.html`. Creator-app-split must come before stealth-and-packaging because the strip-down to local FastAPI must happen before the Nuitka build (otherwise dead Flask templates and CSS bloat the binary).

### Phase E — Launch 📋
- **#74 Comprehensive UAT — user app + company dashboard + admin dashboard** (pre-launch gate, MUST pass before #22). Drives every page, every form, every button across all 3 surfaces. ~50–70 ACs across 3 sub-tasks (74.1 user app, 74.2 company, 74.3 admin). AC blocks live in `docs/specs/` and follow `docs/uat/AC-FORMAT.md`.
- #22 Landing page — last, links to new installer from Phase D. Only opens for traffic after #74 passes.

---

## Tasks NOT in any batch or phase

These exist outside the 4-batch / 5-phase model. They're either (a) infrastructure that supports execution, (b) one-off security/migration work, or (c) bug tickets discovered during UAT.

### UAT infrastructure (the `/uat-task` workflow)
| Task | Title | Status |
|------|-------|--------|
| #46 | Build `/uat-task` skill — closed-loop UAT verifier | ✅ done |
| #47 | Author `docs/uat/AC-FORMAT.md` + Task #14 Verification Procedure block | ✅ done |
| #48 | Build `scripts/uat/` helper scripts (seed_campaign, accept_invitation, etc.) | ✅ done |
| #49 | First real `/uat-task 14` run + capture learnings | ✅ done (2026-04-26) |
| #50 | Backfill Verification Procedure for #15, #44, #45 | ✅ done 2026-04-29 — #15 ACs in batch-2-ai-brain.md (14 ACs); #44 + #45 ACs in new docs/specs/infra.md (10 + 7 ACs). |
| #51 | Backfill Verification Procedure for Batch 4 (#19, #22) | ✅ done 2026-04-30 — #19 has 13 ACs (Stripe MCP autonomous setup + test-mode → live smoke); #22 has 8 ACs (perf, dual-audience, OG tags, mobile, FAQ). |
| #52 | Backfill Verification Procedure for polish tasks (#23–28) | ✅ done 2026-04-30 — scope absorbed. AC blocks for #23/#27/#28 shipped inline with their PRs. #24/#25/#26 deferred (dead-template polish) — requirements folded into Phase D HTMX migration doc. |
| #74 | **Pre-launch comprehensive UAT** — user app + company dashboard + admin dashboard, all features driven via Chrome DevTools MCP. 3 sub-tasks, ~50–70 ACs. Phase E entry gate. | 📋 pending (high) |

### Server / infra one-offs
| Task | Title | Status |
|------|-------|--------|
| #2 | Stripe top-up verification + idempotency fix | ✅ done |
| #3 | Verify CSRF tokens in all Flask forms | ✅ done |
| #4 | Install slowapi + apply rate limiting to auth endpoints | ✅ done |
| #40 | Fully disable X — hardcoded safety guard (3 X account suspensions) | ✅ done |
| #41 | Vercel → Hostinger KVM migration | ✅ done (server LIVE since 2026-04-25) |
| #44 | ARQ worker entrypoint | ✅ done 2026-04-30 — 9/10 ACs PASS, live on VPS systemd, unblocks Phase D |
| #45 | Baseline Alembic migration + enforce going forward | ✅ done 2026-04-30 — 7/7 ACs PASS, prod stamped at `c5967048d886`, CLAUDE.md policy live |

### Bugs discovered 2026-04-26 (during `/uat-task 14`)
| Task | Title | Status |
|------|-------|--------|
| #53 | Re-verify #13 — Facebook/Reddit follower counts wrong | ✅ done |
| #55 | `get_user_profiles()` reads empty `agent_user_profile` table | ✅ done (vestigial table dropped) |
| #56 | `'list' object has no attribute 'get'` in content agent (3 sites) | ✅ done |
| #57 | Quality gate: accept `niche_tags + required_platforms + empty target_regions` as valid | 📋 pending (low) — Phase C |
| #58 | Matching algorithm doesn't invite eligible users to active campaigns | ✅ done |
| #59 | Duplicate invitation rendered on `/campaigns` page | 📋 pending (medium) — Phase C |
| #60 | Dashboard shows X (Twitter) as Connected despite global disable | 📋 pending (low) — Phase C |
| #61 | Server `matching.py` `NameError 'user_tier'` for seedling at max | ✅ done (deployed live via SSH) |
| #62 | Dashboard "Posts This Month" counts deleted/voided posts | ✅ done |
| #63 | `seed_campaign.py` wrong invitation accept endpoint (404) | 📋 pending (low — UAT infra) — Phase C |
| #64 | `seed_campaign.py` wrong image-upload endpoint (404) | 📋 pending (low — UAT infra) — Phase C |
| #65 | `AMPLIFIER_UAT_FORCE_DAY` doesn't propagate to `agent_draft.iteration` | 📋 pending (low — UAT infra) — Phase C |

### Bugs / polish from Task #15 UAT (2026-04-29)

| Task | Title | Status |
|------|-------|--------|
| #71 | BUG: Wizard create-and-activate skips audit_log + AI review | ✅ done 2026-04-29 23:01 — 5/5 ACs PASS via `scripts/uat/verify_task71_72.py` |
| #72 | ~~POLISH: Tighten AI review prompt for niche-mismatch cases~~ | ⏪ **REVERTED 2026-04-30** — companies own targeting decisions, AI doesn't review. Full reversal record: `docs/uat/reports/task-72-2026-04-30-REVERTED.md` |
| #73 | BUG: gemini-1.5-flash returns 404 in AI review provider chain | 📋 pending (low) — Phase C cleanup |

---

## Deferred / superseded tasks — why (17 total)

| Task | Title | Why deferred / superseded |
|------|-------|--------------|
| #7 | Repost campaigns | Post-launch. Foundational code exists (CampaignPost model, creation form, agent branch) but feature not complete. UI hidden, backend preserved. |
| #17 | Free/Pro user subscription tiers ($19.99/mo) | **Deferred 2026-04-29.** Cold-start economics: amplifiers with no earnings track record can't rationally evaluate a $19.99/mo subscription. 20% platform cut is sufficient MVP monetization. Free 4 posts/day cap dropped alongside Pro (it only made sense as upgrade friction). Reputation tier still governs campaign count + earnings multiplier. Server scaffolding (`subscription_tier` column, `SUBSCRIPTION_TIERS` dict, `get_effective_max_campaigns`) left dormant — inert with default `free`. Revisit triggers: amplifier cohort earning $300+/month, OR campaign-supply scarcity, OR feature demand that genuinely costs money. |
| #16 | Content formats (LinkedIn polls, Facebook photo albums, Reddit link posts) | Deferred 2026-04-18. Text + image already work on all 3 active platforms. Quality-of-life upgrade, not a launch blocker. Revisit if engagement data shows formats outperform text-only by >2x. |
| #20 | PyInstaller packaging | **Superseded 2026-04-28** by `docs/migrations/2026-04-28-migration-stealth-and-packaging.md` (uses Nuitka, not PyInstaller). |
| #21 | Mac support | **Superseded 2026-04-28** by same migration doc (Nuitka cross-platform build matrix handles Mac). |
| #29 | Political campaigns (geo-targeting, FEC compliance) | Post-launch. Heavy compliance scope, not in MVP. |
| #30 | Self-learning content generation | Post-launch. Needs production data to train on. |
| #31 | Video generation | Post-launch. Out of scope until image pipeline proves itself. |
| #32 | Flux.1 image generation upgrade | Post-launch. Current 5-provider chain (Gemini → Cloudflare → Together → Pollinations → PIL) works. |
| #33 | GDPR export + account deletion | Post-launch. Not blocking US-only launch. |
| #34 | ARIA accessibility audit | Post-launch. |
| #35 | CSV export for earnings | Post-launch. Nice-to-have. |
| #36 | Mobile responsive dashboard | Post-launch. Companies use desktop. |
| #37 | Local lightweight LLM for user-side AI | Post-launch. Gemini free tier is enough. |
| #39 | UGC-style content (authenticity for viral) | Post-launch. Image post-processing pipeline already exists; deeper UGC tuning later. |
| #42 | Re-enable TikTok / Instagram / X via cheap API | Blocked. X API v2 too expensive; stealth browser unproven. Re-enable only when verified-safe automation method exists. |
| #43 | Shared research pool across users | Post-launch. Per-user research cache is fine for current scale. |
| #54 | Reconsider user app tech stack (Tauri / Electron vs Flask) | **Decided 2026-04-28.** After three independent reviews, the answer is: stay Python for the daemon, replace the local Flask UI with a slim local FastAPI (5 routes only), host the rest on the FastAPI server. Migrate stealth to Patchright. Package with Nuitka. See `docs/migrations/2026-04-28-*.md`. |
| #69 | Nvidia free-tier as 4th AI provider fallback | **Deferred 2026-04-29.** Current 3-provider chain (Gemini + Mistral + Groq) works in production after Task #15. Nvidia trial terms restrict to prototyping/testing — proxying via Amplifier likely violates spirit. Full analysis: `docs/research/nvidia-free-tier-for-amplifier.md`. Revisit if existing chain becomes unreliable or onboarding friction data shows users lack the 3 existing provider keys. |

---

## Currently in flight (immediate next steps)

1. ~~**Task #50**~~ ✅ done 2026-04-29. ACs backfilled: #15 in `docs/specs/batch-2-ai-brain.md` (14 ACs), #44 + #45 in new `docs/specs/infra.md` (10 + 7 ACs). New helpers expected during build: `scripts/uat/seed_campaign_quality_test.py`, `scripts/uat/cleanup_quality_test.py`, `scripts/uat/seed_worker_fixtures.py`, `scripts/uat/dump_models_ddl.py`, plus `scripts/uat/uat_task15.py`, `uat_task44.py`, `uat_task45.py`, and `scripts/uat/infra/compose.yml`.
2. **Build Task #15 (quality gate)** — implement `services/quality_gate.py` to satisfy the 14 ACs. Then `/uat-task 15`.
3. **Marks Phase A complete** → move to Phase C (#18 first, automated tests).

**Active blockers (need user)**: Task #19 requires user to set up Stripe Connect + bank onboarding before it can be implemented. Phase D Stripe work (#19) can run in parallel with the UI migrations once Stripe is set up.

**Tasks.json status (2026-04-30 09:23):** 31 done / 23 pending / 19 deferred / 73 total. Tasks #66 (dashboards-htmx), #67 (creator-app-split), #68 (stealth-and-packaging), #69 (nvidia, deferred), #70 (BYOK) are in tasks.json. #71 (wizard audit_log + AI review) shipped 2026-04-29 — 5/5 ACs PASS. **#72 REVERTED 2026-04-30** (companies own their targeting; AI doesn't second-guess) — moved to deferred with `[REVERTED]` prefix. **#18 (pytest suite) shipped 2026-04-30** — 80 tests pass in 10.2s, including 20 new + cleanup of pre-existing test rot. #73 (gemini-1.5-flash 404) filed pending. #20 / #21 carry status `deferred` (functionally equivalent to `superseded` — both mean "won't be built as originally scoped, see migration docs"). #54 is `done`.

---

## AC + UAT workflow (one-paragraph summary)

Every task spec ends with a `## Verification Procedure — Task #<id>` block following the table format in `docs/uat/AC-FORMAT.md` (Preconditions → Test data setup → Test-mode flags → AC table per criterion → Aggregated PASS rule). Each AC has 7 fields: Setup, Action, Expected, Automated, Automation, Evidence, Cleanup. Run **`/uat-task <id>`** to drive the **real** product (real server `api.pointcapitalis.com`, real Supabase DB, real Playwright browsers, real Gemini calls) and verify each AC. The skill **refuses** to mark a task done unless every AC PASSes + zero errors in logs + cleanup completed. Tool boundaries: **Playwright** drives the product (posting, scraping); **Chrome DevTools MCP** drives the verifier (testing the product as a user). X is unconditionally refused (Task #40). UAT learnings compound in `docs/uat/skills/uat-task/LEARNINGS.md`.

**Tasks lacking AC blocks (cannot run `/uat-task` until backfilled):**
- #15 (Quality gate) — owner: Task **#50**
- #44 (ARQ worker) — owner: Task **#50**
- #45 (Alembic baseline) — owner: Task **#50**
- #17, #19, #22 (Batch 4) — owner: Task **#51**
- #23–#28 (polish) — owner: Task **#52**
- #74 (pre-launch UAT) — three sub-task AC blocks (74.1/74.2/74.3) authored as part of #74 itself. Block must exist before launch and is itself the launch gate.
- New migration tasks #66, #67, #68 already have inline ACs in their migration docs (each migration doc has an Acceptance Criteria section that follows the same shape).

---

## Server / infra state

LIVE at **`https://api.pointcapitalis.com`** since 2026-04-25 — Hostinger KVM 1 (Mumbai, Ubuntu 24.04, Caddy + uvicorn + Supabase PostgreSQL via transaction pooler). systemd unit `amplifier-web.service`. Deploy = `/commit-push` (auto-pulls + restarts via SSH). Full context: `docs/HOSTING-DECISION-RECORD.md`, `docs/MIGRATION-FROM-VERCEL.md`.

---

*Re-derive this file from `.taskmaster/tasks/tasks.json` whenever statuses change. Quick check command:*
```bash
python -c "import json,io,collections; d=json.load(io.open('.taskmaster/tasks/tasks.json',encoding='utf-8')); print(collections.Counter(t['status'] for t in d['master']['tasks']))"
```
