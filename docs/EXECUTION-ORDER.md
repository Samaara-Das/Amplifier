> ## ⚠️ DEPRECATED — do not use this doc for execution planning
>
> **Deprecated 2026-04-24.** This file was written for an earlier 80-task `task-master` state that no longer exists. The task-master tasks.json was reset to a 41-task list (commit `c20a639 chore: reset task-master with finalized 36-task list`) and the Phase A-G grouping below references task IDs (#28-#38, #52/#63, etc.) that have been renumbered or removed.
>
> **For current execution order, use:**
> 1. `task-master list` — authoritative pending/done/deferred status
> 2. `docs/specs/batch-1-money-loop.md`, `batch-2-ai-brain.md`, `batch-3-product-features.md`, `batch-4-business-launch.md` — feature buckets with acceptance criteria
> 3. Rule: pick the lowest-numbered pending task in the current batch whose dependencies are met. Ignore task-master's "recommended next" algorithm.
>
> The content below is preserved for historical reference only.
>
> ---

# Amplifier — Task Execution Order

**Purpose**: Which tasks to do in what sequence. Tasks are ordered by dependency — later tasks consume data or features that earlier tasks create.

## How To Use This Document

**For the user**: Start a new session and say: "Read these 4 docs and start implementing: `docs/REMAINING-WORK.md`, `docs/EXECUTION-ORDER.md`, `docs/SCHEMA-CHANGES.md`, `docs/FILE-CHANGE-INDEX.md`." That's it — nothing else needed.

**For Claude**: You determine which phase to work on by reading this execution order. You implement each phase autonomously. After completing a phase, you MUST proactively:
1. Tell the user the phase is done
2. Provide a specific step-by-step verification checklist (not vague — "do X, expect Y")
3. Wait for the user to run through the checklist and report results
4. Fix any failures before moving to the next phase
5. Move to the next phase automatically — do not wait for the user to tell you what's next

---

## Phase A: Foundation (Do First — Everything Else Depends On This)

These fix the core posting → metrics → billing loop. No other work matters until this chain works end-to-end.

```
#28 Fix posting URL capture (LinkedIn/Facebook/Reddit)
 ↓ posts now have real URLs
#29 Explain metric scraping → #30 Verify metric scraping
 ↓ metrics flow correctly from platform → local_metric → server Metric
#31 Explain billing → #32 Verify billing
 ↓ billing calculates correct cents, hold periods work, tiers apply
#33 Explain earnings → #34 Verify earnings
 ↓ user dashboard shows correct numbers
#35 Explain Stripe top-up → #36 Verify Stripe top-up
 ↓ companies can add funds
#37 Explain campaign detail → #38 Verify campaign detail
 ↓ companies can see performance
```

**Estimated time**: 5-7 days
**Gate**: After this phase, run a full end-to-end test: company creates campaign → user accepts → content generated → posted → metrics scraped → billing runs → earnings appear → company sees stats. If this works, Phase A is done.

---

## Phase B: Security & Product Gaps (Do Second)

These fix issues that real users would hit on day one. Can be done in any order within the phase.

```
#72 CSRF protection (security — do early)
#71 Password reset flow
#73 Encrypt server auth token (server_auth.json still plaintext)
#74 Rate limiting + API key validation + campaign search
#66 X lockout detection
#67 Session health reliability
#70 Fix draft notification count
#75 Content draft UX improvements
#76 Invitation UX gaps
FTC disclosure (add disclaimer_text to Campaign model, append to content)
```

**Estimated time**: 5-7 days
**Gate**: All Flask forms have CSRF tokens. Password can be reset. X lockout is detected. Drafts show correct counts. Invitations have countdown timers.

---

## Phase C: Schema Extensions (Do Before Tier 4 Features)

Multiple Tier 4 tasks need the same schema changes. Do them ALL in one migration pass to avoid repeated ALTER TABLEs.

### Server Models (one migration):
```python
# Campaign model additions:
campaign_goal    String(30)   # brand_awareness | leads | virality | engagement
campaign_type    String(20)   # ai_generated | repost | political
tone             String(50)   # professional | casual | edgy | educational | urgent
preferred_formats JSONB       # {"x": ["thread", "poll"], "linkedin": ["carousel"]}
disclaimer_text  Text         # "Paid for by [committee]" or "#ad"

# User model additions:
zip_code         String(10)
state            String(2)    # US state abbreviation
political_campaigns_enabled  Boolean  default=False
subscription_tier String(20)  # free | paid
```

### Local DB (one migration in _init_db):
```sql
-- agent_draft additions:
ALTER TABLE agent_draft ADD COLUMN format_type TEXT;  -- text | thread | poll | carousel | video
ALTER TABLE agent_draft ADD COLUMN variant_id INTEGER DEFAULT 0;

-- campaign_posts table (NEW — for repost campaigns):
CREATE TABLE IF NOT EXISTS campaign_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_server_id INTEGER,
    platform TEXT,
    content TEXT,
    image_url TEXT,
    post_order INTEGER DEFAULT 0,
    scheduled_offset_hours INTEGER DEFAULT 0,
    FOREIGN KEY (campaign_server_id) REFERENCES local_campaign(server_id)
);
```

**Estimated time**: 1 day
**Why do this now**: Tasks #52/#63, #64, #68, and Political Campaigns ALL need these fields. Adding them once prevents migration conflicts.

---

## Phase D: Tier 4 Features (Largest Block — Do in This Order)

Tasks are ordered by dependency: earlier tasks create capabilities that later tasks consume.

```
#68 Repost campaign type
 ↓ simplest campaign type, proves campaign_type field works
 ↓ no AI gen needed, just posting
 
#51/#59 AI profile scraping
 ↓ better profile data flows into matching AND content gen
 ↓ must be done before 4-phase agent (research phase needs AI-quality profiles)

#58 AI campaign quality gate
 ↓ validates campaign data before it reaches content gen
 ↓ do before content agent so bad campaigns don't waste AI calls

#52/#63 4-phase AI content agent (LARGEST TASK)
 ↓ replaces ContentGenerator with research → strategy → creation → review
 ↓ strategy phase uses campaign_goal, tone, preferred_formats
 ↓ creation phase produces format-specific content (threads, polls, etc.)
 ↓ this MUST be done before #64 (content formats)

#64 All content formats (threads, polls, carousels) across 6 platforms
 ↓ depends on #52/#63 (content agent must produce format-specific output)
 ↓ new JSON scripts in config/scripts/ per format
 ↓ re-enables Instagram and TikTok

#65 Platform content preview in review UI
 ↓ depends on #64 (needs to know what formats exist)
 ↓ pure UI task, no backend changes

#61 Self-learning content generation
 ↓ depends on #52/#63 (feeds performance data back into strategy phase)
 ↓ needs real posting + metric data to learn from (Phase A must be done)

#62 Free/paid user tiers
 ↓ independent of content features but needs reputation tiers working
 ↓ Stripe subscription billing

Political campaigns
 ↓ depends on: schema changes (Phase C), content agent (#52/#63), geo fields
 ↓ BLOCKED by: US legal entity setup ($5-15K, non-code)
 ↓ can build product features while legal setup is in progress
```

**Estimated time**: 25-35 days
**Gate per task**: Each task has specific verification criteria in REMAINING-WORK.md.

---

## Phase E: Data Integrity & Testing (Do After Features Stabilize)

```
#60 Metrics accuracy for billing
 ↓ cross-validation, sanity checks, audit trail
 ↓ do after metrics are verified working (Phase A)

#53 Update SLC spec
 ↓ do after all features are built — SLC is the living spec

#54 Write automated tests
 ↓ do LAST — tests lock down verified behavior
 ↓ writing tests before features stabilize = constant rewrites
```

**Estimated time**: 3-5 days

---

## Phase F: Polish & Admin Verification (Do Last)

```
#39-50 Admin/company dashboard verification (12 tasks)
#77 Data integrity improvements
#78 Settings, metrics, performance improvements
#79 UX polish and integration fixes
#80 Compliance, accessibility, testing
```

**Estimated time**: 5-7 days

---

## Phase G: Launch Prep

```
Stripe integration (live keys, webhook, Connect onboarding)
 ↓ must be after billing is verified (Phase A)
Mac support (test + fix Windows-specific bits)
 ↓ independent, can be done anytime
Package as installer (PyInstaller)
 ↓ must be after Mac support (package for both platforms)
Landing page
 ↓ must be after packaging (need download links)
```

**Estimated time**: 5-7 days

---

## Visual Dependency Map

```
Phase A ──────────────────────────────────────────────┐
(#28 → #29-30 → #31-32 → #33-34 → #35-36 → #37-38) │
                                                       ↓
Phase B ──────────────────────── Phase C ──────────────┤
(#72, #71, #73, #74, #66,       (Schema migration)    │
 #67, #70, #75, #76, FTC)                             │
                                                       ↓
                              Phase D ─────────────────┤
                              (#68 → #51/59 → #58 →   │
                               #52/63 → #64 → #65 →   │
                               #61 → #62 → Political)  │
                                                       ↓
                              Phase E ─────────────────┤
                              (#60 → #53 → #54)        │
                                                       ↓
                              Phase F ─── Phase G ─────┘
                              (#39-50,    (Stripe, Mac,
                               #77-80)    Installer,
                                          Landing page)
```

---

## Time Summary

| Phase | Tasks | Days | Cumulative |
|---|---|---|---|
| A: Foundation | #28-38 | 5-7 | 5-7 |
| B: Security/Gaps | #66-76, FTC | 5-7 | 10-14 |
| C: Schema | Migration | 1 | 11-15 |
| D: Features | #51-68, Political | 25-35 | 36-50 |
| E: Integrity/Tests | #53, #54, #60 | 3-5 | 39-55 |
| F: Polish | #39-50, #77-80 | 5-7 | 44-62 |
| G: Launch | Stripe, Mac, Installer, Page | 5-7 | 49-69 |

**Total: 49-69 days of focused work.**

Phases B and C can overlap with Phase A. Phases F and G can overlap. With parallelism, realistic calendar time is **8-12 weeks**.
