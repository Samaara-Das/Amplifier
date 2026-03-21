# Amplifier Documentation Inventory

This is the canonical list of all documentation files in Amplifier. The `/update-docs` skill uses this to know what exists and what each file covers.

Last updated: March 2026

---

## Tier 1: Primary Docs (always audit)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `CLAUDE.md` | Architecture, commands, platform gotchas, config | Claude / developers | Every feature change |
| `README.md` | Project overview, setup, tech stack, doc index | Public / contributors | New features, setup changes |

## Tier 2: Technical Reference Docs (audit when features change)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `docs/API_REFERENCE.md` | All 52+ API endpoints with request/response examples | Developers | API route changes |
| `docs/DATABASE_SCHEMA.md` | All 13 tables with field-level detail + Mermaid ERD | Developers | Model changes |
| `docs/USER_FLOWS.md` | Step-by-step user journeys with Mermaid diagrams | Developers, stakeholders | Flow changes |
| `docs/SYSTEM_DESIGN.md` | Architectural decisions with rationale | Developers | Architecture changes |
| `docs/DEPLOYMENT.md` | Server deployment, user app distribution, env vars | DevOps, developers | Deployment changes |

## Tier 3: Architecture & Planning Docs (audit when features change)

| File | Purpose | Audience | Update Frequency |
|------|---------|----------|-----------------|
| `docs/campaign-platform-architecture.md` | Server architecture deep dive, matching, billing, trust | Developers | Server feature changes |
| `docs/auto-poster-workflow.md` | Engine pipeline: generate → review → post | Developers | Engine workflow changes |
| `auto-poster-prd.md` | Product requirements for the posting engine | Stakeholders, devs | Scope changes, milestones |
| `.taskmaster/docs/campaign-platform-prd.md` | Product requirements for the marketplace server | Stakeholders, devs | Scope changes, milestones |

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

## Configuration Files (not audited for content, but tracked)

| File | Purpose |
|------|---------|
| `.claude/agents/docs-updater.md` | Docs-updater agent definition |
| `.claude/skills/update-docs/SKILL.md` | Update-docs skill definition |
| `.claude/skills/update-docs/references/doc-inventory.md` | This file |
| `config/platforms.json` | Platform URLs, timeouts, enable flags, proxy, subreddits |
| `config/.env` | Timing params, headless mode, behavior config |
| `server/.env.example` | Server config template (DB URL, JWT, Stripe, platform cut) |
| `amplifier.spec` | PyInstaller build spec |
| `installer.iss` | Inno Setup Windows installer |

## Key Codebase Areas to Monitor

These are the main code areas. When files here change, docs likely need updating:

| Area | Key Files | Docs Affected |
|------|-----------|---------------|
| Posting engine | `scripts/post.py` | CLAUDE.md, auto-poster-workflow.md, USER_FLOWS.md |
| Content generation | `scripts/generate.ps1` | CLAUDE.md, auto-poster-workflow.md |
| Review dashboard | `scripts/review_dashboard.py` | CLAUDE.md, USER_FLOWS.md |
| Campaign runner | `scripts/campaign_runner.py` | CLAUDE.md, USER_FLOWS.md, SYSTEM_DESIGN.md |
| User dashboard | `scripts/campaign_dashboard.py` | CLAUDE.md, USER_FLOWS.md |
| Server API | `server/app/routers/` | CLAUDE.md, API_REFERENCE.md, campaign-platform-architecture.md |
| Server models | `server/app/models/` | CLAUDE.md, DATABASE_SCHEMA.md, campaign-platform-architecture.md |
| Server services | `server/app/services/` | campaign-platform-architecture.md, SYSTEM_DESIGN.md |
| Server dashboards | `server/app/templates/` | campaign-platform-architecture.md, USER_FLOWS.md |
| Utilities | `scripts/utils/` | CLAUDE.md, SYSTEM_DESIGN.md |
| Config | `config/` | CLAUDE.md, DEPLOYMENT.md |
| Deployment | `vercel.json`, `amplifier.spec`, `installer.iss` | DEPLOYMENT.md, README.md |
