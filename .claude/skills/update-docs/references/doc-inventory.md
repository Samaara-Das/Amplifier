# Amplifier Documentation Inventory

This is the canonical list of all documentation files in Amplifier. The `/update-docs` skill uses this to know what exists and what each file covers.

Last updated: 2026-05-02 (Phase D fully closed via `a4828de`: Tasks #66 + #67 + #70 SHIPPED, #68 partial; Task #74 launch-UAT ACs authored at `docs/specs/launch-uat.md`; 4 new UAT seed helpers under `scripts/uat/`; Alembic head now `b1c2d3e4f5a6`; pytest count 303)

---

## Tier 1: Primary Docs (always audit)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `CLAUDE.md` | Architecture, commands, platform gotchas, config, schema-migration policy | Claude / developers | Every feature change |
| `README.md` | Project overview, setup, tech stack, doc index | Public / contributors | New features, setup changes |
| `docs/STATUS.md` | Derived view of tasks.json — batches, phases, status counts, immediate next steps | Claude / developers | Re-derive from tasks.json on every task status change |

## Tier 2: Architecture & Planning Docs (audit when features change)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `docs/PRD.md` | Full product requirements: all features, data models, API spec, billing, trust, implementation status | Developers, stakeholders | Every feature sprint |
| `docs/AMPLIFIER-SPEC.md` | Complete system spec covering all 3 implementations (v1/v2/v3), content gen, posting, metrics, comparison table | Developers, co-founders | Architecture changes |
| `docs/pitch-deck.md` | Investor/co-founder pitch deck (Slide 9: What's Built is traction-sensitive) | Co-founders, investors | After major milestones |
| `docs/specs/batch-1-money-loop.md` | Per-task specs (Tasks #1, #9, #10, #11) + Verification Procedure blocks | Developers | When task scope changes |
| `docs/specs/batch-2-ai-brain.md` | Per-task specs (Tasks #12, #13, #14, #15) + Verification Procedure blocks (Task #14 has 18 ACs) | Developers | When task scope changes |
| `docs/specs/batch-3-product-features.md` | Per-task specs (Tasks #5, #7, #8, #16) + Verification Procedure blocks for cleanup bugs #57, #59, #60 (added 2026-04-30) | Developers | When task scope changes |
| `docs/specs/batch-4-business-launch.md` | Per-task specs (Tasks #6, #17, #19, #22). Task #19 has 13 ACs (Stripe MCP autonomous setup + test-mode → live smoke); Task #22 has 8 ACs (perf, dual-audience, OG tags, mobile, FAQ). Backfilled 2026-04-30 via Task #51. | Developers | When task scope changes |
| `docs/specs/infra.md` | Per-task specs for non-batch infra: Task #18 (pytest suite), #44 (ARQ worker), #45 (Alembic baseline), #73 (gemini model id fix), #27 (post URL dedup, added 2026-04-30), #28 (ToS gate, added 2026-04-30), #23 (daemon DB backup, added 2026-04-30) — all with full Verification Procedure blocks | Developers | When infra task scope changes |
| `docs/specs/uat-infra.md` | Per-task specs for UAT-harness bugs (Tasks #63, #64, #65) — added 2026-04-30 alongside Phase C bug cleanup batch | Developers | When UAT helper scripts evolve |
| `docs/specs/launch-uat.md` | Phase E launch UAT spec — 64 ACs across 3 sub-tasks (74.1 user app, 74.2 company dashboard, 74.3 admin dashboard). Authored 2026-05-01. Pre-launch gate. | Developers | When launch UAT scope changes |
| `docs/specs/onboarding.md` | Task #75 web onboarding spec — 12 ACs covering /register page, JWT handoff to localhost:5222, /onboarding/step2/3/4 flow, ToS gate, edge cases. Authored 2026-05-02. | Developers | When onboarding scope changes |
| `docs/specs/agent-control.md` | Task #76 daemon control + dashboard agent visibility — 8 ACs covering pause/resume buttons + AgentCommand creation + SSE-driven badges + last_seen indicator + drafts-ready widget. Authored 2026-05-02. | Developers | When agent control surface changes |
| `docs/specs/installer-assets.md` | Tasks #77 (icon.ico) + #79 (eula.rtf) — 8 ACs total covering Windows installer asset readiness. Authored 2026-05-02. | Developers | When installer assets change |
| `docs/specs/admin-actions.md` | Task #80 admin financial UI buttons — 4 ACs for missing run-earning-promotion + run-payout-processing buttons on /admin/financial. Authored 2026-05-02. | Developers | When admin action UI changes |
| `docs/migrations/2026-05-01-migration-gap-audit.md` | Phase D gap audit (3 audit passes) + final triage table + pre-launch checklist. Identifies 6 launch-blocker gaps mapped to tasks #75/#76/#77/#79/#80 + #19 update. Authored 2026-05-02. | Developers, Claude | One-shot historical record (do not modify after launch) |
| `docs/specs/user-app-tech-stack.md` | ⚠️ SUPERSEDED 2026-04-28 by `docs/migrations/2026-04-28-*.md`. Kept for historical context only. | -- | Do not edit |
| `docs/migrations/2026-04-25-task41-schema-fixes.md` | Vercel→Hostinger schema-fix runbook (Task #41 deployment) | DevOps | One-shot historical record |
| `docs/migrations/2026-04-28-migration-dashboards-htmx-upgrade.md` | Phase D blueprint: dashboards HTMX upgrade (#66) | Developers | When migration plan evolves |
| `docs/migrations/2026-04-28-migration-creator-app-split.md` | Phase D blueprint: creator app split (#67) | Developers | When migration plan evolves |
| `docs/migrations/2026-04-28-migration-stealth-and-packaging.md` | Phase D blueprint: Patchright + Nuitka + installers (#68) | Developers | When migration plan evolves |
| `docs/migrations/2026-04-30-task18-stripe-account-id.md` | Schema migration: ALTER TABLE adding `users.stripe_account_id` (pre-Alembic-baseline pattern) | DevOps | One-shot historical record |
| `docs/sessions/` | Per-session fallback notes when MemPalace MCP is unavailable. `mempalace mine docs/sessions/` ingests them. Files like `2026-04-30-phase-c-bug-batch-and-task51.md`. | Claude / next session | One file per session as needed |
| `docs/uat/AC-FORMAT.md` | Format spec for `## Verification Procedure` blocks; rules for `/uat-task` skill | Developers, Claude | When AC format evolves |

## Tier 3: Reference Docs (audit when relevant subsystems change)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `docs/amplifier-flow.md` | E2E flow diagram | Developers | Flow changes |
| `docs/api-reference.md` | Detailed API endpoint reference | Developers | API route changes |
| `docs/background-agent-reference.md` | Background agent task reference | Developers | Agent task changes |
| `docs/billing-and-earnings.md` | Billing mechanics deep dive | Developers | Billing changes |
| `docs/campaign-matching.md` | Matching algorithm deep dive | Developers | Matching changes |
| `docs/config-reference.md` | Config options reference | Developers | Config changes |
| `docs/content-generation.md` | Content generation pipeline | Developers | AI provider changes |
| `docs/database-models.md` | DB model field reference | Developers | Model changes |
| `docs/deployment-guide.md` | ⚠️ Stale Vercel-era setup. Server moved to Hostinger 2026-04-25. Refresh needed. | DevOps | Out of date — flag for rewrite |
| `docs/development-setup.md` | Local dev setup | Developers | Setup changes |
| `docs/local-database-schema.md` | Local SQLite schema | Developers | Local DB changes |
| `docs/platform-posting-playbook.md` | Platform-specific posting details | Developers | Platform changes |
| `docs/technical-architecture.md` | Architecture overview | Developers | Architecture changes |
| `docs/troubleshooting.md` | Common issues and fixes | Developers | When new bugs found |
| `docs/user-app-guide.md` | User app guide | Users, developers | UX changes |

## Tier 4: Brand & Content Docs (audit when brand strategy changes)

| File | Purpose | Notes |
|------|---------|-------|
| `docs/brand-strategy.md` | Brand positioning, voice, audience, content pillars | Core brand document |
| `config/content-templates.md` | Content generation templates, platform format rules, legal disclaimers | Used by generate.ps1 |

## Tier 5: Config & Context Docs (audit when relevant)

| File | Purpose | Notes |
|------|---------|-------|
| `.claude/task-context.md` | Session context and progress tracking | Updated per session |
| `.claude/commands/get-context.md` | Context retrieval command | Rarely changes |
| `.claude/commands/update-context.md` | Context update command | Rarely changes |
| `.claude/output-styles/brand-strategist.md` | Brand strategist output style for Claude | Update when brand strategy changes |
| `.claude/ralph-tasks.md` | Ralph task queue | Task management |
| `.claude/skills/uat-task/SKILL.md` | `/uat-task` skill — runs end-to-end UAT, refuses to mark done unless every AC passes | Skill grows via LEARNINGS.md |
| `docs/uat/skills/uat-task/LEARNINGS.md` | Persistent corrections for `/uat-task` skill — read first on every invocation, compounds across runs | Append-only |
| `docs/uat/reports/` | Generated UAT reports per run (committed to git) | One file per `/uat-task <id>` run |

## Tier 5: MVP Spec (audit when MVP scope changes)

| File | Purpose | Notes |
|------|---------|-------|
| `mvp.md` | MVP feature spec and verification checklist | Source of truth for MVP scope; all 8 phases complete |

## Configuration Files (not audited for content, but tracked)

| File | Purpose |
|------|---------|
| `.claude/agents/docs-updater.md` | Docs-updater agent definition |
| `.claude/skills/update-docs/SKILL.md` | Update-docs skill definition |
| `.claude/skills/update-docs/references/doc-inventory.md` | This file |
| `config/platforms.json` | Platform URLs, timeouts, enable flags, proxy, subreddits |
| `config/.env` | Timing params, headless mode, behavior config, API keys |
| `config/.env.example` | Canonical template for `config/.env` — documents UAT_TEST_* creds + AMPLIFIER_UAT_* test-mode flags |
| `server/.env.example` | Server config template (DB URL, JWT, Stripe, platform cut) |
| `vercel.json` | Vercel deployment config (LEGACY — server now on Hostinger VPS as of 2026-04-25) |
| `amplifier.spec` | PyInstaller build spec (LEGACY — Phase D migrates to Nuitka per `docs/migrations/2026-04-28-migration-stealth-and-packaging.md`) |
| `installer.iss` | Inno Setup Windows installer |
| `server/deploy/amplifier-worker.service` | systemd unit file for ARQ worker (deployed to `/etc/systemd/system/` on VPS) |
| `server/alembic/` | Alembic migrations directory. Baseline `c5967048d886` (Task #45) → `a1b2c3d4e5f6` (Task #28, ToS) → `63d9159c4ce6` (Task #67, drafts + agent_commands + agent_status) → `b1c2d3e4f5a6` (Task #70, company_api_keys). **Current head: `b1c2d3e4f5a6`** — applied to prod 2026-05-01. |
| `tests/conftest.py` + `tests/server/test_*.py` | 303-test pytest suite (288 baseline + 15 BYOK from Task #70). Run via `python -m pytest tests/ -q` (~70s). See `docs/specs/infra.md` Task #18. |
| `.mcp.json` | Project-scope MCP servers. Includes `tradingview` (stdio) and `stripe` (HTTP/OAuth at `https://mcp.stripe.com/`, added 2026-04-30 for Task #19 — needs one-time `/mcp` auth before tools become callable). |

## Key Codebase Areas to Monitor

These are the main code areas. When files here change, docs likely need updating:

| Area | Key Files | Docs Affected |
|------|-----------|---------------|
| Posting engine | `scripts/post.py`, `scripts/engine/`, `config/scripts/` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| AI abstraction (text) | `scripts/ai/manager.py`, `scripts/ai/*_provider.py` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| AI abstraction (image) | `scripts/ai/image_manager.py`, `scripts/ai/image_providers/`, `scripts/ai/image_postprocess.py`, `scripts/ai/image_prompts.py` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| Background agent | `scripts/background_agent.py` | CLAUDE.md, docs/PRD.md |
| Content generation (personal) | `scripts/generate.ps1` | CLAUDE.md |
| Content generation (campaigns) | `scripts/utils/content_generator.py` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| Local database | `scripts/utils/local_db.py` | CLAUDE.md, docs/PRD.md |
| Metric collection | `scripts/utils/metric_collector.py`, `scripts/utils/metric_scraper.py` | CLAUDE.md |
| User app | `scripts/user_app.py` | CLAUDE.md, docs/PRD.md |
| Profile scraping | `scripts/utils/profile_scraper.py`, `scripts/utils/ai_profile_scraper.py`, `scripts/utils/browser_config.py` | CLAUDE.md |
| Server API | `server/app/routers/` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md, docs/api-reference.md |
| Server models | `server/app/models/` | CLAUDE.md, docs/PRD.md, docs/database-models.md, AND requires Alembic migration in `server/alembic/versions/` per CLAUDE.md schema-migration policy |
| Server services | `server/app/services/` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| Background worker | `server/app/worker.py` | CLAUDE.md, docs/technical-architecture.md, docs/specs/infra.md |
| Schema migrations | `server/alembic/versions/` | CLAUDE.md (schema-migration policy section) |
| Config | `config/` | CLAUDE.md |
| Deployment | `vercel.json`, `server/.env.example`, Hostinger VPS systemd unit | CLAUDE.md, docs/deployment-guide.md, docs/HOSTING-DECISION-RECORD.md, docs/MIGRATION-FROM-VERCEL.md |
| UAT infrastructure | `scripts/uat/`, `.claude/skills/uat-task/`, `docs/uat/`, `docs/specs/batch-*.md` Verification Procedure blocks | CLAUDE.md, doc-inventory.md, docs/uat/AC-FORMAT.md |
