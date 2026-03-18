# Auto-Posting System — Task Context

**Last Updated**: 2026-03-18

## Current Task
- **COMPLETED: Task #17 — Implement Updated Auto-Poster Workflow** (all 13 subtasks done via Ralph)
- Next up: **Task #18 — Test Run** (depends on 17, now unblocked)
- Task Master still shows #17 as pending — needs `task-master set-status --id=17 --status=done`

## Task Progress Summary

### Completed (16/16 MVP tasks + Task 17 — 100%)
- [x] Tasks 1-14, 15-16: Full MVP built and E2E tested
- [x] All 6 platforms E2E verified: X, LinkedIn, Facebook, Reddit, TikTok, Instagram
- [x] BlueSky integration removed (task 10)
- [x] **Task 17: Updated Auto-Poster Workflow** — all 13 subtasks (see below)

### Task 17 Subtasks (all complete, 2026-03-17 to 2026-03-18)
1. [x] Enable all 6 platforms in platforms.json
2. [x] Update posting schedule — 6 individual scheduler tasks (AutoPoster-Post-Slot-1 through -6)
3. [x] Add `--slot` argument to post.py with auto-detection from IST time + SLOT_SCHEDULE mapping
4. [x] Rewrite generate.ps1 for per-slot drafts (one draft per posting slot, slot-aware platforms)
5. [x] Content pillar rotation — $PillarDescriptions, day alternation, content series (Setup Mon, Backtest Wed, One Thing Fri)
6. [x] CTA rotation — FIRST_POST_DATE in .env, month 1 = 100% value, month 2+ = 80/15/5 weighted random
7. [x] Draft JSON schema — slot, pillar, format, platforms fields; get_next_draft(slot=N) filtering
8. [x] post.py uses slot-filtered drafts, intersects draft.platforms with slot schedule
9. [x] Review dashboard — pillar/slot/format/platform badges with color coding
10. [x] Content buffer — get_buffer_status() in draft_manager, generate.ps1 skips slots with pending drafts
11. [x] Failure retry — 5-min delay + retry once per platform, failed drafts visible in dashboard with retry button
12. [x] Legal disclaimers in generator prompt — per-platform rules, conditional for setup/backtest posts
13. [x] Auto-engagement — likes/retweets/upvotes/reposts on all 6 platforms during browse_feed()

### Brand Strategy (Completed — Session 5, 2026-03-13)
- [x] Custom output style, emotion-first principle, brand strategy doc, content templates, US timezone alignment

### E2E Workflow Planning (Completed — Session 6, 2026-03-14)
- [x] Platform strategy, posting frequency, full E2E workflow doc, warmup plan, weekly review loop, 13 new tasks

### Pending — Now (sequential, with dependencies)
- [ ] **18**: Test Run — Confirm Updated Workflow Works (high, depends on 17 ✓)
- [ ] **19**: Account Warmup — Gradual Ramp-Up Per Platform (high, depends on 18)
- [ ] **21**: Discuss "I'm Back" LinkedIn Post Strategy (high, depends on 19)
- [ ] **20**: Revamp Profiles — X, Reddit, LinkedIn, Facebook (high, depends on 21)

### Pending — Later (independent, no blocking dependencies)
- [ ] **22**: AI Video Generation for TikTok + Instagram (medium)
- [ ] **23**: Financial Newsletters/Articles as Content Source (medium)
- [ ] **25**: Facebook Groups Posting (medium)
- [ ] **26**: TradingView Content Auto-Posting (medium)
- [ ] **27**: Analytics Dashboard — Automate Weekly Review Data Pull (medium)
- [ ] **28**: Content A/B Testing Framework (low)
- [ ] **29**: Email List + Lead Magnet for Monetization Funnel (low)
- [ ] **30**: Competitor Analysis Tooling (low)

## Session History

### Sessions 1-4 (2026-03-07 to 2026-03-13) — MVP Build & E2E Testing
- Built entire auto-posting system from scratch
- All 6 platforms E2E tested and working
- Key discoveries: shadow DOM piercing, overlay click workarounds, TikTok video-only uploads, Draft.js editor handling

### Session 5 (2026-03-13) — Brand Strategy Development
- Created brand strategist output style
- Full brand strategy document with 5 audience personas, 5 pillars, 6 platform playbooks, 30+ hook templates
- Updated content-templates.md and scheduler for US timezone

### Session 6 (2026-03-14) — E2E Workflow Planning & Platform Strategy
- Platform strategy: X + Reddit (active engagement), LinkedIn + Facebook (passive auto-post), TikTok + Instagram (paused → later enabled)
- Posting frequency: X 3/day, Reddit 2-3/week, LinkedIn Tue-Fri, Facebook daily
- Full E2E workflow: `docs/auto-poster-workflow.md` (6 phases: research → generate → review → post → engage → weekly review)
- Account warmup plan, weekly performance review, 13 new tasks (17-30)

### Sessions 7-8 (2026-03-17 to 2026-03-18) — Task 17 Implementation via Ralph
- Ralph autonomous loop implemented all 13 subtasks of Task 17
- Key changes per subtask:
  - **Scheduler**: Split single task into 6 slot-specific tasks in setup_scheduler.ps1
  - **post.py**: Added --slot arg, SLOT_SCHEDULE dict, get_slot_platforms(), slot-filtered draft selection, per-platform retry with 5-min delay
  - **generate.ps1**: Complete rewrite for per-slot generation, pillar rotation (day alternation + content series), CTA rotation (month-based), legal disclaimers per platform
  - **draft_manager.py**: get_next_draft(slot=N), get_buffer_status(), get_failed_drafts(), retry_failed_draft()
  - **review_dashboard.py**: Pillar/slot/format/platform badges, failed drafts section with retry button
  - **human_behavior.py**: auto_engage() with per-platform likes/retweets/upvotes/reposts, daily caps in .env, engagement tracker JSON, blocklist for sensitive content, integrated into browse_feed() midway through each session

## Important Decisions Made
- **ALL 6 platforms enabled** (updated 2026-03-17, was 4)
- **Auto-engagement added** — likes/retweets/upvotes during browse_feed, but NO commenting (stays manual)
- **New X account needed** — fresh start with new email
- **Content voice: "I learnt this, maybe you can try this too"** — never claiming trading experience
- **1-day content buffer** — system keeps approved posts queued
- **CTA rotation** — month 1 = 100% value, month 2+ = 80/15/5 split
- **LinkedIn "I'm back" post** — do this BEFORE profile revamps

## Key Reference Files
- `docs/auto-poster-workflow.md` — Complete E2E workflow specification (Phase 1-6)
- `docs/brand-strategy.md` — Full brand & content strategy document
- `scripts/post.py` — Main orchestrator + platform posting + slot scheduling
- `scripts/generate.ps1` — Content generator (per-slot, pillar rotation, CTA rotation, legal disclaimers)
- `scripts/review_dashboard.py` — Review dashboard with badges and failed draft retry
- `scripts/utils/draft_manager.py` — Draft lifecycle + slot filtering + buffer status
- `scripts/utils/human_behavior.py` — Anti-detection + auto-engagement on all platforms
- `scripts/utils/image_generator.py` — Image/video generation
- `scripts/setup_scheduler.ps1` — Windows Task Scheduler (6 slot-specific tasks)
- `config/platforms.json` — Platform URLs, enable flags, proxy config, subreddits
- `config/content-templates.md` — Brand voice, content pillars, platform format rules
- `config/.env` — Timing, behavior, engagement caps, CTA config
- `.claude/ralph-tasks.md` — Task 17 subtask tracker (all 13 complete)

## Memory Files
- `memory/project_platform_strategy.md` — Which platforms, why, active vs passive
- `memory/project_e2e_flow.md` — Full E2E workflow details
- `memory/user_brand_context.md` — User profile, audience, goals
- `memory/project_content_iteration.md` — Content experimentation framework (future)
- `memory/feedback_auto_commit_push.md` — Always commit and push without being asked
- `memory/feedback_value_first_content.md` — All content must deliver actionable value
- `memory/feedback_no_trading_experience.md` — Never claim trading experience

## Verified Patterns (selectors & techniques)
- **X**: `[data-testid="tweetButton"]` + `dispatch_event("click")` | Engagement: `[data-testid="like"]`, `[data-testid="retweet"]` + `[data-testid="retweetConfirm"]`
- **LinkedIn**: `[role="button"]:has-text("Start a post")` → `[role="textbox"]` → `get_by_role("button", name="Post", exact=True)` | Engagement: `button[aria-label*="Like"]`, `button[aria-label*="Repost"]`
- **Facebook**: `[aria-label="What's on your mind?"]` → `[role="textbox"]` → `[aria-label="Post"]` | Engagement: `[aria-label="Like"]`, `[aria-label="Share"]`
- **Reddit**: `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button:has-text("Post")` | Engagement: `button[aria-label="Upvote"]`
- **TikTok**: Hidden `input[type="file"]` (video/*) → dismiss dialogs → `div.public-DraftEditor-content` (Ctrl+A, Backspace, type) → `button[data-e2e="post_video_button"]` | Engagement: `[data-e2e="like-icon"]`
- **Instagram**: `[aria-label="New post"]` → `svg[aria-label="Post"]` → file input → Next x2 → caption → Share (all force=True) | Engagement: `svg[aria-label="Like"]`

## Test Commands
```bash
# Login setup for a platform
python scripts/login_setup.py tiktok
python scripts/login_setup.py instagram

# Run the poster (picks up next pending draft for auto-detected slot)
python scripts/post.py
python scripts/post.py --slot 3

# Generate drafts
powershell -File scripts/generate.ps1
powershell -File scripts/generate.ps1 -count 3
powershell -File scripts/generate.ps1 -slot 2

# Check content buffer status
python -c "from scripts.utils.draft_manager import get_buffer_status; print(get_buffer_status())"

# Check engagement tracker
python -c "from scripts.utils.human_behavior import _load_engagement_tracker; print(_load_engagement_tracker())"

# Review dashboard
python scripts/review_dashboard.py  # opens http://localhost:5111

# Task Master
task-master next
task-master list --with-subtasks
task-master set-status --id=17 --status=done
```
