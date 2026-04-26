# Amplifier — Project Status

> **Snapshot date: 2026-04-26.** This is a derived view. The canonical source is `.taskmaster/tasks/tasks.json`. If this doc is more than a few days old, re-derive from `tasks.json` and update.

## How to read this repo

A fresh agent should read in this order:

1. **`docs/STATUS.md`** (this file) — what's done, what's next, what's deferred
2. **`docs/specs/batch-*.md`** — per-task specs and `## Verification Procedure` blocks
3. **`CLAUDE.md`** — developer reference: commands, architecture, gotchas, slash commands
4. **`docs/uat/AC-FORMAT.md`** — canonical Acceptance Criteria + UAT format

The work is organized into **5 orthogonal batches** plus a **UAT-infra batch**. Within each batch, execute tasks in numeric order. Ignore the task-master recommender — it doesn't respect batch ordering.

---

## Batches at a glance

| Batch | Spec file | Tasks | Status |
|-------|-----------|-------|--------|
| **1 — Money Loop** | `docs/specs/batch-1-money-loop.md` | #1, #6, #9, #10, #11, #38 | ✅ **DONE** (2026-04-08) — full post → metrics → billing → earnings pipeline live |
| **2 — AI Brain** | `docs/specs/batch-2-ai-brain.md` | #12, #13, #14, #15 | 🔄 **IN PROGRESS** — #12, #13, #14 done; **#15 next** (pending AC block) |
| **3 — Product Features** | `docs/specs/batch-3-product-features.md` | #5, #7, #8, #16 | ⚠️ **MIXED** — #5, #8 done; #7, #16 deferred (post-launch) |
| **4 — Business Launch** | `docs/specs/batch-4-business-launch.md` | #17, #19, #22 | 📋 **PENDING** — all need AC blocks (Task #51 owns this) + Stripe setup blocks #17, #19 |
| **5 — Polish / Infra** | (no dedicated spec — see `tasks.json`) | #18, #20, #21, #23–28, #44, #45 | 📋 **PENDING** — automated tests, packaging, polish items |
| **UAT Infra** | `docs/uat/AC-FORMAT.md` + `docs/uat/skills/uat-task/LEARNINGS.md` | #46–52 | 🔄 **IN PROGRESS** — #46–49 done; **#50, #51, #52** pending (AC backfill) |
| **User App Tech Stack** | `docs/specs/user-app-tech-stack.md` | #54 | ⏸ **DEFERRED** — Tauri vs Electron vs status-quo Flask reconsideration |

**Server**: ✅ LIVE at `https://api.pointcapitalis.com` (Hostinger KVM 1, Mumbai). Task #41 done 2026-04-25. Deploy via `/commit-push`.

---

## Currently in flight

- **Next implementation task**: **#15 — AI campaign quality gate** (Batch 2 finisher). Spec exists at `docs/specs/batch-2-ai-brain.md`; **AC block needs to be backfilled first** under Task #50.
- **Active branch**: `flask-user-app`
- **Active blockers (need user)**: Tasks #17 and #19 require user to set up Stripe Connect + bank onboarding.
- **Recent UAT win** (2026-04-26): `/uat-task 14` first all-green run. 18/18 ACs PASS. Real posts on LinkedIn/FB/Reddit then auto-deleted. 7 production bugs surfaced and fixed (#55, #56, #58, #61, #62, plus Bug #53 follower count, plus a server `NameError` patched live via SSH).

---

## Task status (full table — 65 tasks)

Status counts: **26 done · 24 pending · 15 deferred · 0 in-progress**

### Batch 1 — Money Loop ✅
| ID | Title | Status |
|----|-------|--------|
| #1 | Fix URL capture for LinkedIn, Facebook, Reddit | ✅ done |
| #6 | Metrics accuracy — anomaly_flag, cross-validation | ✅ done |
| #9 | Metric scraping — per-platform spec, E2E verify | ✅ done |
| #10 | Billing — earnings calc spec, E2E verify | ✅ done |
| #11 | Earnings display — server↔local sync, withdrawal | ✅ done |
| #38 | E2E deleted post detection — full pipeline | ✅ done |

### Batch 2 — AI Brain 🔄
| ID | Title | Status | Notes |
|----|-------|--------|-------|
| #12 | AI matching — scoring logic, accuracy verify | ✅ done | |
| #13 | AI profile scraping — Gemini Vision, per-platform | ✅ done | Re-verified via #53 (FB follower count fix) |
| #14 | 4-phase content agent (research, strategy, creation, review) | ✅ done | First all-green `/uat-task` run 2026-04-26 |
| **#15** | **AI campaign quality gate — detailed rubric spec** | 📋 **pending** | **NEXT TASK.** Needs AC block (Task #50). |

### Batch 3 — Product Features ⚠️
| ID | Title | Status |
|----|-------|--------|
| #5 | Invitation UX — countdown, expired badge, decline reason | ✅ done |
| #7 | Repost campaign — company create + frequency + display | ⏸ deferred (post-launch — see `Deferred — why` below) |
| #8 | Admin payout void/approve actions | ✅ done |
| #16 | Content formats — threads, polls, carousels | ⏸ deferred (post-launch) |

### Batch 4 — Business Launch 📋
| ID | Title | Status | Blockers |
|----|-------|--------|----------|
| #17 | Free/Pro tiers — Stripe subscription billing | 📋 pending | User needs Stripe setup; needs AC block (#51) |
| #19 | Stripe live integration — Checkout + Connect onboarding | 📋 pending | User needs Stripe setup; needs AC block (#51); deps `#2`, `#10` |
| #22 | Landing page — public acquisition site | 📋 pending | dep `#20` (packaging); needs AC block (#51) |

### Batch 5 — Polish / Infra 📋
| ID | Title | Status | Notes |
|----|-------|--------|-------|
| #18 | Automated test suite (pytest) | 📋 pending | deps `#10`, `#11` |
| #20 | PyInstaller packaging — Windows installer | 📋 pending | |
| #21 | Mac support — cross-platform audit + packaging | 📋 pending | dep `#20` |
| #23 | Periodic DB backup in background agent | 📋 pending (low) | |
| #24 | Status label renaming in user app templates | 📋 pending (low) | |
| #25 | Clipboard copy button for post URLs | 📋 pending (low) | |
| #26 | Client-side form validation in user app | 📋 pending (low) | |
| #27 | Server-side post URL dedup | 📋 pending | |
| #28 | ToS + privacy policy acceptance in registration | 📋 pending | |
| #44 | ARQ worker entrypoint | 📋 pending | Blocking #17 — needs scheduling |
| #45 | Baseline Alembic migration + enforce going forward | 📋 pending | Blocking #15 |

### UAT Infra 🔄
| ID | Title | Status |
|----|-------|--------|
| #46 | Build `/uat-task` skill — closed-loop UAT verifier | ✅ done |
| #47 | Author `docs/uat/AC-FORMAT.md` + Task #14 AC block | ✅ done |
| #48 | Build `scripts/uat/` helpers (seed_campaign, accept_invitation, etc.) | ✅ done |
| #49 | First real `/uat-task 14` run + capture learnings | ✅ done (2026-04-26) |
| **#50** | Backfill Verification Procedure for #15, #44, #45 | 📋 pending — **DO BEFORE running `/uat-task 15`** |
| #51 | Backfill Verification Procedure for Batch 4 (#17, #19, #22) | 📋 pending |
| #52 | Backfill Verification Procedure for Batch 5 polish (#23–28) | 📋 pending |

### Infrastructure / one-offs ✅
| ID | Title | Status |
|----|-------|--------|
| #2 | Stripe top-up verification + idempotency fix | ✅ done |
| #3 | Verify CSRF tokens in all Flask forms | ✅ done |
| #4 | Install slowapi + apply rate limiting to auth | ✅ done |
| #40 | Fully disable X — hardcoded safety guard | ✅ done (3 X account suspensions; X stays off until API v2 or stealth browser) |
| #41 | Vercel migration → Hostinger KVM | ✅ done (server LIVE at api.pointcapitalis.com 2026-04-25) |

### Bug tasks discovered 2026-04-26 (during /uat-task 14)
| ID | Title | Status |
|----|-------|--------|
| #53 | Re-verify #13 — Facebook/Reddit follower counts | ✅ done |
| #55 | `get_user_profiles()` reads empty `agent_user_profile` table | ✅ done (vestigial table dropped) |
| #56 | `'list' object has no attribute 'get'` in content agent | ✅ done |
| #57 | Quality gate: accept `niche_tags + required_platforms + empty target_regions` | 📋 pending (low) |
| #58 | Matching algorithm doesn't invite eligible users | ✅ done |
| #59 | Duplicate invitation rendered on `/campaigns` page | 📋 pending |
| #60 | Dashboard shows X as Connected despite global disable | 📋 pending (low) |
| #61 | Server `matching.py` `NameError 'user_tier'` for seedling at max | ✅ done (deployed live via SSH) |
| #62 | Dashboard "Posts This Month" counts deleted/voided posts | ✅ done |
| #63 | `seed_campaign.py` wrong invitation accept endpoint (404) | 📋 pending (low — UAT infra) |
| #64 | `seed_campaign.py` wrong image-upload endpoint (404) | 📋 pending (low — UAT infra) |
| #65 | `AMPLIFIER_UAT_FORCE_DAY` doesn't propagate to `agent_draft.iteration` | 📋 pending (low — UAT infra) |

---

## Deferred — why

| ID | Title | Why deferred |
|----|-------|--------------|
| #7 | Repost campaigns | Post-launch — text+image campaigns cover MVP. UI hidden, backend preserved. |
| #16 | Content formats (threads, polls, carousels) | Post-launch — text+image already work on all 3 active platforms. Quality-of-life upgrade, not blocking launch. Revisit if engagement data shows formats outperform >2x. |
| #29 | Political campaigns (geo-targeting, FEC) | Post-launch — heavy compliance scope, not in MVP. |
| #30 | Self-learning content generation | Post-launch — needs production data to train on. |
| #31 | Video generation | Post-launch — out of scope until image pipeline proves itself. |
| #32 | Flux.1 image generation upgrade | Post-launch — current 5-provider chain (Gemini→Cloudflare→Together→Pollinations→PIL) works. |
| #33 | GDPR export + account deletion | Post-launch — not blocking US-only launch. |
| #34 | ARIA accessibility audit | Post-launch. |
| #35 | CSV export for earnings | Post-launch — nice-to-have. |
| #36 | Mobile responsive dashboard | Post-launch — companies use desktop. |
| #37 | Local lightweight LLM for user-side AI | Post-launch — Gemini free tier is enough. |
| #39 | UGC-style content (authenticity for viral) | Post-launch — image post-processing pipeline already exists; deeper UGC tuning later. |
| #42 | Re-enable TikTok / Instagram / X via cheap API | Blocked — X API v2 is expensive; stealth browser unproven. Re-enable only when a verified-safe automation method exists. |
| #43 | Shared research pool across users | Post-launch — research cache per-user is fine for current scale. |
| #54 | Reconsider user app tech stack (Tauri/Electron vs Flask) | Awaiting decision — current Flask works. Will re-evaluate if packaging issues block #20. |

---

## What's missing (gaps a fresh agent should know)

These tasks **cannot** run `/uat-task <id>` until their `## Verification Procedure` block is written, per CLAUDE.md UAT rule:

- **#15** (AI quality gate) — owner: Task **#50**
- **#44** (ARQ worker) — owner: Task **#50**
- **#45** (Alembic baseline) — owner: Task **#50**
- **#17, #19, #22** (Batch 4) — owner: Task **#51**
- **#23–#28** (polish) — owner: Task **#52**

The AC block format is locked in `docs/uat/AC-FORMAT.md`. Task #14 in `docs/specs/batch-2-ai-brain.md` is the worked example to copy from.

UAT learnings (apply automatically when writing new AC blocks): `docs/uat/skills/uat-task/LEARNINGS.md`.

---

## AC + UAT workflow (one-paragraph version)

Every task spec ends with a `## Verification Procedure — Task #<id>` block following the table format in `docs/uat/AC-FORMAT.md` (Preconditions → Test data setup → Test-mode flags → AC table per criterion → Aggregated PASS rule). Each AC has 7 fields: Setup, Action, Expected, Automated, Automation, Evidence, Cleanup. Run `/uat-task <id>` to drive the **real** product (real server `api.pointcapitalis.com`, real Supabase DB, real Playwright browsers, real Gemini calls) and verify each AC. The skill refuses to mark a task done unless every AC PASSes + zero errors in logs + cleanup completed. Tool boundaries: **Playwright** drives the product (posting, scraping); **Chrome DevTools MCP** drives the verifier (testing the product as a user). X is unconditionally refused (Task #40). UAT learnings compound in `docs/uat/skills/uat-task/LEARNINGS.md`.

---

## Server / infra state (one-liner)

LIVE at **`https://api.pointcapitalis.com`** since 2026-04-25 — Hostinger KVM 1 (Mumbai, Ubuntu 24.04, Caddy + uvicorn + Supabase PostgreSQL). systemd unit `amplifier-web.service`. Deploy = `/commit-push` (auto-pulls + restarts). Full context: `docs/HOSTING-DECISION-RECORD.md`, `docs/MIGRATION-FROM-VERCEL.md`.

---

*Re-derive this file from `.taskmaster/tasks/tasks.json` whenever statuses change. Cmd: `python -c "import json,io,collections; d=json.load(io.open('.taskmaster/tasks/tasks.json',encoding='utf-8')); print(collections.Counter(t['status'] for t in d['master']['tasks']))"`*
