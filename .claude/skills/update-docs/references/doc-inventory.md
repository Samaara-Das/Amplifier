# Amplifier Documentation Inventory

This is the canonical list of all documentation files in Amplifier. The `/update-docs` skill uses this to know what exists and what each file covers.

Last updated: 2026-04-15

---

## Tier 1: Primary Docs (always audit)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `CLAUDE.md` | Architecture, commands, platform gotchas, config | Claude / developers | Every feature change |
| `README.md` | Project overview, setup, tech stack, doc index | Public / contributors | New features, setup changes |

## Tier 2: Architecture & Planning Docs (audit when features change)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `docs/PRD.md` | Full product requirements: all features, data models, API spec, billing, trust, implementation status | Developers, stakeholders | Every feature sprint |
| `docs/AMPLIFIER-SPEC.md` | Complete system spec covering all 3 implementations (v1/v2/v3), content gen, posting, metrics, comparison table | Developers, co-founders | Architecture changes |
| `docs/pitch-deck.md` | Investor/co-founder pitch deck (Slide 9: What's Built is traction-sensitive) | Co-founders, investors | After major milestones |

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
| `docs/deployment-guide.md` | Vercel + Supabase deployment | DevOps | Deployment changes |
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
| `server/.env.example` | Server config template (DB URL, JWT, Stripe, platform cut) |
| `vercel.json` | Vercel deployment config (rootDirectory is a project-level setting, not here) |
| `amplifier.spec` | PyInstaller build spec |
| `installer.iss` | Inno Setup Windows installer |

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
| Server API | `server/app/routers/` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| Server models | `server/app/models/` | CLAUDE.md, docs/PRD.md |
| Server services | `server/app/services/` | CLAUDE.md, docs/PRD.md, docs/AMPLIFIER-SPEC.md |
| Config | `config/` | CLAUDE.md |
| Deployment | `vercel.json`, `server/.env.example` | CLAUDE.md, docs/deployment-guide.md |
