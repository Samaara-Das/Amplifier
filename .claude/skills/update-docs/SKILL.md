---
name: update-docs
description: "Use this skill after adding, removing, or changing features in Amplifier to update all project documentation. Triggers: 'update docs', 'sync docs', 'refresh docs', 'clean up docs', 'docs are outdated', 'update documentation', or when prompted to update docs after a feature change. Audits all doc files for accuracy, removes outdated content, adds missing info."
---

# Amplifier — Documentation Updater

Keep all Amplifier documentation accurate, consistent, and free of outdated information after feature changes.

## Execution Mode

**IMPORTANT: Enter plan mode immediately when this skill is invoked.** Use `EnterPlanMode` before doing any work. The planning phase should complete Phase 1 (Gather Current State) and Phase 2 (Audit Each Doc) — presenting the user with a clear summary of what will be added, updated, removed, and flagged. Only after the user approves the plan should Phase 3 (Apply Updates) and beyond proceed.

## When to Run

Run this skill:
- After completing a feature, refactor, or significant bug fix
- When the user says docs need updating
- When reminded by post-task prompts to update documentation

## Document Categories

All documentation files are organized into tiers. Every tier must be audited.

### Tier 1: Primary Docs (always audit)
| File | Purpose | Content Guidelines |
|------|---------|-------------------|
| `CLAUDE.md` | AI assistant codebase guide | Architecture overview, commands, file descriptions, platform gotchas. Keep concise — loaded every session. |
| `README.md` | Project overview for GitHub | Tech stack, setup instructions, architecture summary. Public-facing. |

### Tier 2: Architecture & Planning Docs (audit when features change)
| File | Purpose | Content Guidelines |
|------|---------|-------------------|
| `docs/campaign-platform-architecture.md` | Server architecture, API routes, models, services | Technical audience. Include API endpoint tables, model schemas, service descriptions. |
| `docs/auto-poster-workflow.md` | Engine workflow: generate → review → post pipeline | Document the three-phase pipeline, platform-specific flows, scheduling. |
| `auto-poster-prd.md` | Product requirements for the engine | Milestones, roadmap, feature specs for the posting engine. |
| `.taskmaster/docs/campaign-platform-prd.md` | Product requirements for the server/marketplace | Milestones, roadmap, feature specs for the two-sided marketplace. |

### Tier 3: Brand & Content Docs (audit when brand strategy changes)
| File | Purpose | Content Guidelines |
|------|---------|-------------------|
| `docs/brand-strategy.md` | Brand positioning, voice, audience, content pillars | Brand identity, emotional hooks, platform strategy, posting schedule. |
| `config/content-templates.md` | Content generation templates and rules | Brand voice rules, platform format specs, legal disclaimers, CTA templates. |

### Tier 4: Config & Context Docs (audit when relevant)
| File | Purpose |
|------|---------|
| `.claude/task-context.md` | Session context and progress tracking |
| `.claude/commands/get-context.md` | Context retrieval command |
| `.claude/commands/update-context.md` | Context update command |

## Workflow

### Phase 1: Gather Current State (PLAN MODE)

1. Read `references/doc-inventory.md` to get the full list of documentation files
2. Read the git log for recent commits to understand what changed:
   ```
   git log --oneline -20
   ```
3. Read the current codebase state for areas that changed — check:
   - `scripts/` for new/changed scripts (post.py, generate.ps1, review_dashboard.py, campaign_runner.py, etc.)
   - `scripts/utils/` for utility changes (server_client.py, local_db.py, metric_scraper.py, image_generator.py, human_behavior.py)
   - `server/app/routers/` for API route changes
   - `server/app/models/` for database model changes
   - `server/app/services/` for service layer changes (matching.py, billing.py, trust.py, payments.py)
   - `server/app/templates/` for dashboard template changes
   - `config/` for configuration changes (platforms.json, .env, content-templates.md)

### Phase 2: Audit Each Doc (PLAN MODE)

Audit **all tiers** of documentation. For each doc file, compare the documented state against the actual codebase.

#### Things to ADD
- New scripts, API routes, services, models not yet documented
- New platform support or platform-specific posting changes
- New server features or dashboard pages
- New configuration options or environment variables
- Changed commands or workflow steps

#### Things to REMOVE or UPDATE
- References to deleted files, scripts, or routes
- Descriptions of old behavior that no longer matches the code
- Outdated architecture descriptions
- Stale command examples that no longer work
- Old platform gotchas that have been resolved
- References to deprecated or removed dependencies

#### Things to FLAG
- Sections where the doc is ambiguous about current behavior
- PRD items that may be outdated given implementation changes
- Brand strategy content that may need updating

#### Sync Checks
Perform these cross-document consistency checks:

1. **CLAUDE.md ↔ codebase**: Verify all commands in CLAUDE.md still work. Check that file descriptions match actual files.
2. **Doc inventory completeness**: Verify that `references/doc-inventory.md` lists ALL `.md` files that actually exist in the repo. Run:
   ```
   find . -name "*.md" -not -path "./node_modules/*" -not -path "./.venv/*"
   ```
   Flag any files missing from the inventory.
3. **Undocumented code**: Check for scripts, API routes, or services not mentioned in any documentation:
   - Scripts in `scripts/` not listed in CLAUDE.md
   - API routes in `server/app/routers/` not documented
   - Services in `server/app/services/` not described
   - Models in `server/app/models/` not listed

### Present Plan and Exit Plan Mode

After completing Phase 1 and Phase 2, write a plan summarizing:
- **Files to update** with specific changes per file
- **Content to add** (new features, scripts, routes, etc.)
- **Content to remove** (outdated references, deleted files, stale descriptions)
- **Content to flag** (ambiguous sections, outdated PRD items)
- **Sync issues** (cross-document discrepancies)

Use `ExitPlanMode` to present this plan for user approval. Only proceed to Phase 3 after approval.

### Phase 3: Apply Updates (AFTER PLAN APPROVAL)

Update docs in this priority order:

1. **`CLAUDE.md`** — Most critical. This is what Claude reads every session.
   - Update the Architecture section if structure changed
   - Update Commands section with new/changed commands
   - Update Platform-Specific Selector Patterns if posting logic changed
   - Update Configuration section if config files changed
   - Update Key Constraints if constraints changed
   - Keep the file well-organized — don't let sections bloat

2. **`README.md`** — Public-facing.
   - Update setup instructions for changed workflows
   - Update architecture summary
   - Update feature list

3. **Architecture docs:**
   - `docs/campaign-platform-architecture.md`: Update API routes, models, services, dashboard pages
   - `docs/auto-poster-workflow.md`: Update engine pipeline, platform flows, scheduling

4. **PRD docs:**
   - `auto-poster-prd.md`: Mark completed milestones, update feature descriptions
   - `.taskmaster/docs/campaign-platform-prd.md`: Mark completed milestones, update roadmap

5. **Brand & content docs** — Only if brand strategy, content pillars, or platform rules changed.

6. **Config & context docs** — Only if the change is relevant.

### Phase 4: Clean Up Stale Docs

Check for docs that should be deleted entirely:
- Documentation for features that have been completely removed
- Migration docs for migrations that are long complete
- Any `.md` file that describes code that no longer exists

Before deleting, confirm with the user.

### Phase 5: Update Inventory

After all updates, ensure `references/doc-inventory.md` reflects the current state:
- Add any new doc files created
- Remove deleted doc files
- Update status and notes for modified docs

### Phase 6: Report and Remind

After all updates, provide a summary:

```
## Docs Updated
- CLAUDE.md: [what changed]
- README.md: [what changed]
- ...

## Flagged for Manual Action
- [ ] [Any items needing manual intervention]

## Sync Issues Found
- [ ] [Any cross-document discrepancies]

## Docs Reviewed (No Changes Needed)
- [list unchanged docs]
```

Always remind the user to:
1. **Review the diff** before committing doc changes
2. **Check PRD docs** if implementation diverged from original plan

## Content Guidelines by Doc Type

### CLAUDE.md
- Keep it concise and scannable — this is loaded into every Claude session
- Use tables for API routes, commands, and file listings
- Describe WHAT each file does, not HOW (implementation details go in architecture docs)
- Keep Platform-Specific Selector Patterns accurate — these are critical for posting reliability

### README.md
- Public-facing, written for developers who might contribute or deploy
- Include setup instructions, architecture overview, tech stack
- Keep it welcoming but concise

### Architecture Docs
- Use tables for API endpoints and model fields
- Document the data flow: server ↔ user app ↔ engine
- Keep service descriptions focused on what they do and key business rules
- Use Mermaid diagrams where they help visualize flows

### PRD Docs
- Track milestone completion status
- Update feature specs when implementation diverges from original plan
- Stakeholder audience — keep technical detail appropriate

### Brand & Content Docs
- These define the brand voice and content generation rules
- Only update when the user explicitly changes brand strategy
- Keep content-templates.md in sync with the actual generation prompts

## Important Rules

- Never fabricate documentation — only document what actually exists in the codebase
- When unsure whether something changed, read the actual source file before documenting it
- Keep `CLAUDE.md` concise — it's loaded into every session, so bloat wastes context
- Preserve the existing structure and formatting conventions of each doc
- Don't add version history or changelogs to individual doc files
- If a doc section is accurate, leave it alone — don't rewrite for style
- Verify against actual code before documenting features or limitations
