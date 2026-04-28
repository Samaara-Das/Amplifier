# Amplifier — Status, Batches, Phases, Tasks

> **Snapshot date: 2026-04-28.** This is a derived view. The canonical source is `.taskmaster/tasks/tasks.json`. If this doc is more than a few days old, re-derive from `tasks.json`.

> **Important — two orthogonal concepts.** A **batch** is a *feature bucket* (what a set of tasks delivers — e.g. "the AI brain"). A **phase** is an *execution stage* (when a task runs in time). They are not the same thing. The 4 batches and 5 phases overlap but are not identical.

---

## How to read this repo

A fresh agent should read in this order:

1. **`docs/STATUS.md`** (this file) — what's done, what's next, what's deferred, the canonical batches and phases
2. **`docs/specs/batch-*.md`** + **`docs/specs/user-app-tech-stack.md`** — per-task specs
3. **`docs/uat/AC-FORMAT.md`** — Acceptance Criteria + UAT format every spec must follow before `/uat-task <id>` can run it
4. **`CLAUDE.md`** — developer reference: commands, architecture, gotchas, slash commands, decision-making framework
5. **`.taskmaster/tasks/tasks.json`** — canonical task list (65 tasks)

**Execution rule (from feedback 2026-04-18):** Run **phases in order**: A → C → D → E (B is deferred). Within a phase, run tasks in **numeric order**. **Ignore** task-master's "recommended next" — it reorders by dependency/priority, the user wants predictable forward progress.

---

## Status counts

- **26 done** · **24 pending** · **15 deferred** · 0 in-progress · **65 total**
- **Server**: ✅ LIVE at `https://api.pointcapitalis.com` (Hostinger KVM 1, Mumbai). Task #41 done 2026-04-25. Deploy via `/commit-push`.
- **Active branch**: `flask-user-app`
- **Active platforms**: LinkedIn, Facebook, Reddit. **X is unconditionally disabled** (Task #40 hardcoded guard) after 3 account suspensions.
- **Most recent UAT win** (2026-04-26): `/uat-task 14` first all-green run — 18/18 ACs PASS, real posts on LinkedIn/FB/Reddit then auto-deleted, 7 production bugs surfaced and fixed.

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
| **#15** | **AI campaign quality gate (rubric for whether a campaign is worth generating content for)** | 📋 **pending — NEXT TASK** (needs AC block via Task #50) |

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
**What it delivers**: Free/Pro tiers, live Stripe (companies pay in, users get paid out), public landing page.

| Task | Title | Status |
|------|-------|--------|
| #17 | Free/Pro user subscription tiers ($19.99/mo) — Stripe subscription | 📋 pending (blocked: Stripe setup; needs AC block via Task #51) |
| #19 | Stripe live integration — company Checkout + user Connect Express | 📋 pending (blocked: Stripe setup; deps `#2`, `#10`; needs AC block via Task #51) |
| #22 | Landing page — public-facing acquisition site | 📋 pending (dep `#20`; needs AC block via Task #51) |

### Architecture spec (not a batch but referenced by tasks)
**Spec**: `docs/specs/user-app-tech-stack.md` — Tauri vs Electron vs status-quo Flask analysis. Approved direction is web dashboard + headless Python agent. Drives Tasks #20 (PyInstaller), #21 (Mac), #54 (revisit decision). Currently implementation defers #54 — Flask-based status quo continues.

---

## The 5 execution phases (when tasks run, in order)

Per feedback 2026-04-18. Run A → C → D → E. **B is deferred entirely.**

### Phase A — AI Brain finish 🔄
- ✅ #14 (4-phase content agent — done 2026-04-18, re-verified 2026-04-26)
- 📋 **#15 (AI campaign quality gate)** ← *next task to start*

### Phase B — Content formats ⏸ DEFERRED
- ⏸ #16 deferred 2026-04-18 — text + image already work on all 3 active platforms; format expansion is post-launch quality-of-life.

### Phase C — Product tail 📋
Run in numeric order:
- #18 Automated test suite (pytest) — deps `#10`, `#11`
- #20 PyInstaller packaging — Windows installer
- #21 Mac support — cross-platform audit + packaging — dep `#20`
- #22 Landing page — dep `#20` *(also listed in Batch 4)*
- #27 Server-side post URL dedup
- #28 ToS + privacy policy acceptance in registration
- Low-prio polish: #23 (DB backup), #24 (status label rename), #25 (clipboard copy), #26 (client-side validation)

### Phase D — Money 📋
- #17 Free/Pro tiers — blocked on user setting up Stripe
- #19 Stripe live integration — blocked on user setting up Stripe Connect

### Phase E — Launch 📋
Already covered by #22 in Phase C. No new tasks.

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
| **#50** | Backfill Verification Procedure for #15, #44, #45 | 📋 **pending — DO BEFORE `/uat-task 15`** |
| #51 | Backfill Verification Procedure for Batch 4 (#17, #19, #22) | 📋 pending |
| #52 | Backfill Verification Procedure for polish tasks (#23–28) | 📋 pending |

### Server / infra one-offs
| Task | Title | Status |
|------|-------|--------|
| #2 | Stripe top-up verification + idempotency fix | ✅ done |
| #3 | Verify CSRF tokens in all Flask forms | ✅ done |
| #4 | Install slowapi + apply rate limiting to auth endpoints | ✅ done |
| #40 | Fully disable X — hardcoded safety guard (3 X account suspensions) | ✅ done |
| #41 | Vercel → Hostinger KVM migration | ✅ done (server LIVE since 2026-04-25) |
| #44 | ARQ worker entrypoint | 📋 pending (blocking #17) |
| #45 | Baseline Alembic migration + enforce going forward | 📋 pending (blocking #15) |

### Bugs discovered 2026-04-26 (during `/uat-task 14`)
| Task | Title | Status |
|------|-------|--------|
| #53 | Re-verify #13 — Facebook/Reddit follower counts wrong | ✅ done |
| #55 | `get_user_profiles()` reads empty `agent_user_profile` table | ✅ done (vestigial table dropped) |
| #56 | `'list' object has no attribute 'get'` in content agent (3 sites) | ✅ done |
| #57 | Quality gate: accept `niche_tags + required_platforms + empty target_regions` as valid | 📋 pending (low) |
| #58 | Matching algorithm doesn't invite eligible users to active campaigns | ✅ done |
| #59 | Duplicate invitation rendered on `/campaigns` page | 📋 pending (medium) |
| #60 | Dashboard shows X (Twitter) as Connected despite global disable | 📋 pending (low) |
| #61 | Server `matching.py` `NameError 'user_tier'` for seedling at max | ✅ done (deployed live via SSH) |
| #62 | Dashboard "Posts This Month" counts deleted/voided posts | ✅ done |
| #63 | `seed_campaign.py` wrong invitation accept endpoint (404) | 📋 pending (low — UAT infra) |
| #64 | `seed_campaign.py` wrong image-upload endpoint (404) | 📋 pending (low — UAT infra) |
| #65 | `AMPLIFIER_UAT_FORCE_DAY` doesn't propagate to `agent_draft.iteration` | 📋 pending (low — UAT infra) |

---

## Deferred tasks — why (15 total)

| Task | Title | Why deferred |
|------|-------|--------------|
| #7 | Repost campaigns | Post-launch. Foundational code exists (CampaignPost model, creation form, agent branch) but feature not complete. UI hidden, backend preserved. |
| #16 | Content formats (LinkedIn polls, Facebook photo albums, Reddit link posts) | Deferred 2026-04-18. Text + image already work on all 3 active platforms. Quality-of-life upgrade, not a launch blocker. Revisit if engagement data shows formats outperform text-only by >2x. |
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
| #54 | Reconsider user app tech stack (Tauri / Electron vs Flask) | Awaiting decision. Current Flask works. Will re-evaluate if packaging issues block #20. |

---

## Currently in flight (immediate next steps)

1. **Task #50** — backfill `## Verification Procedure` block for #15, #44, #45 in `docs/specs/batch-2-ai-brain.md` and equivalent. Format per `docs/uat/AC-FORMAT.md`. Walk the full lifecycle, cover every platform variant, recurring stability, real side-effects.
2. **Then `/uat-task 15`** — drives the real product to verify Task #15's ACs.
3. **Marks Phase A complete** → move to Phase C (#18 first, automated tests).

**Active blockers (need user)**: Tasks #17 and #19 require user to set up Stripe Connect + bank onboarding before they can be implemented.

---

## AC + UAT workflow (one-paragraph summary)

Every task spec ends with a `## Verification Procedure — Task #<id>` block following the table format in `docs/uat/AC-FORMAT.md` (Preconditions → Test data setup → Test-mode flags → AC table per criterion → Aggregated PASS rule). Each AC has 7 fields: Setup, Action, Expected, Automated, Automation, Evidence, Cleanup. Run **`/uat-task <id>`** to drive the **real** product (real server `api.pointcapitalis.com`, real Supabase DB, real Playwright browsers, real Gemini calls) and verify each AC. The skill **refuses** to mark a task done unless every AC PASSes + zero errors in logs + cleanup completed. Tool boundaries: **Playwright** drives the product (posting, scraping); **Chrome DevTools MCP** drives the verifier (testing the product as a user). X is unconditionally refused (Task #40). UAT learnings compound in `docs/uat/skills/uat-task/LEARNINGS.md`.

**Tasks lacking AC blocks (cannot run `/uat-task` until backfilled):**
- #15 (Quality gate) — owner: Task **#50**
- #44 (ARQ worker) — owner: Task **#50**
- #45 (Alembic baseline) — owner: Task **#50**
- #17, #19, #22 (Batch 4) — owner: Task **#51**
- #23–#28 (polish) — owner: Task **#52**

---

## Server / infra state

LIVE at **`https://api.pointcapitalis.com`** since 2026-04-25 — Hostinger KVM 1 (Mumbai, Ubuntu 24.04, Caddy + uvicorn + Supabase PostgreSQL via transaction pooler). systemd unit `amplifier-web.service`. Deploy = `/commit-push` (auto-pulls + restarts via SSH). Full context: `docs/HOSTING-DECISION-RECORD.md`, `docs/MIGRATION-FROM-VERCEL.md`.

---

*Re-derive this file from `.taskmaster/tasks/tasks.json` whenever statuses change. Quick check command:*
```bash
python -c "import json,io,collections; d=json.load(io.open('.taskmaster/tasks/tasks.json',encoding='utf-8')); print(collections.Counter(t['status'] for t in d['master']['tasks']))"
```
