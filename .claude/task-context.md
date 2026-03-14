# Auto-Posting System — Task Context

**Last Updated**: 2026-03-14

## Current Task
- **Next up: Task #17 — Implement Updated Auto-Poster Workflow** — rebuild the pipeline to match the finalized E2E flow in `docs/auto-poster-workflow.md`. This is a large task that needs subtask breakdown before starting.

## Task Progress Summary

### Completed (16/16 MVP tasks — 100%)
- [x] Tasks 1-14, 15-16: Full MVP built and E2E tested — project scaffolding, content generator, draft manager, human behavior emulation, all 6 platform posting functions, login helper, scheduler, main orchestrator
- [x] All 6 platforms E2E verified: X, LinkedIn, Facebook, Reddit, TikTok, Instagram
- [x] BlueSky integration removed (task 10)

### Brand Strategy (Completed — Session 5, 2026-03-13)
- [x] Custom output style created: `.claude/output-styles/brand-strategist.md`
- [x] Emotion-first principle embedded (non-negotiable)
- [x] LinkedIn + TradingView profiles scraped and analyzed
- [x] Full brand strategy document: `docs/brand-strategy.md`
- [x] Content templates updated: `config/content-templates.md`
- [x] Scheduler aligned to US timezone

### E2E Workflow Planning (Completed — Session 6, 2026-03-14)
- [x] Platform strategy decided: 4 platforms (X + Reddit active, LinkedIn + Facebook passive)
- [x] Posting frequency researched: X 3/day, Reddit 2-3/week, LinkedIn 4/week Tue-Fri, Facebook 1/day
- [x] Full E2E workflow documented: `docs/auto-poster-workflow.md`
- [x] Weekly performance review loop designed
- [x] Account warmup plan defined (weeks 1-2 gradual ramp-up)
- [x] All 13 new tasks created in Task Master (tasks 17-30)

### Pending — Now (sequential, with dependencies)
- [ ] **17**: Implement Updated Auto-Poster Workflow (high)
- [ ] **18**: Test Run — Confirm Updated Workflow Works (high, depends on 17)
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
- Created brand strategist output style (`.claude/output-styles/brand-strategist.md`)
- Embedded emotion-first principle as non-negotiable
- Scraped LinkedIn (~90+ posts, 9.5K connections) and TradingView (357 followers, 5 scripts)
- Built comprehensive user context: `memory/user_brand_context.md`
- Full brand strategy document: `docs/brand-strategy.md` (brand foundation, 5 audience personas, 5 pillar deep-dives, 6 platform playbooks, 30+ hook templates, content calendar, monetization funnel, growth milestones)
- Updated content-templates.md and scheduler for US timezone

### Session 6 (2026-03-14) — E2E Workflow Planning & Platform Strategy
1. **Platform strategy decided** — narrowed from 6 to 4 active platforms:
   - **Active (post + engage):** X (new account needed, new email), Reddit (existing, revamp profile)
   - **Passive (auto-post only):** LinkedIn (existing 9.5K connections, revamp for US), Facebook (existing but empty, set up profile)
   - **Paused:** TikTok (until AI video ready), Instagram (until TikTok content exists to repurpose)
   - **Rationale:** 10 min/day engagement budget means depth beats breadth. X and Reddit are the only platforms where fresh accounts can grow through engagement.

2. **Posting frequency researched** (web search, multiple sources):
   - X: 3 tweets/day + 2 threads/week (replies drive growth more than posts)
   - Reddit: 2-3 posts/week ONLY (9:1 comment-to-post ratio required, spam filters)
   - LinkedIn: 4 posts/week Tue-Fri (daily posting HURTS — 40% reach drop from cannibalization)
   - Facebook: 1/day, 7 days/week (algorithm rewards daily consistency)
   - Total: ~36 posts/week

3. **Full E2E workflow documented** — `docs/auto-poster-workflow.md`:
   - **Phase 1: Content Research** (5:00 PM IST) — Coda notes, backtest reports (every 2-3 days), Stock Buddy performance page screenshots, market events calendar
   - **Phase 2: Content Generation** (5:30 PM IST) — per-platform cadence, voice rules ("I learnt this, maybe you can try this too"), pillar rotation, cross-platform repurposing
   - **Phase 3: User Review** (6:00 PM IST, 15 min) — dashboard approval, 1-day content buffer
   - **Phase 4: Automated Posting** (6:30 PM – 1:30 AM IST) — platform-specific times aligned to US hours
   - **Phase 5: Manual Engagement** (10 min/day) — X replies + Reddit comments (NOT automated)
   - **Phase 6: Weekly Review** (Sunday 7 PM IST, 15 min) — metrics, top/bottom posts, adjust pillar mix
   - Content sources explicitly REMOVED: trending market events (not v1), financial newsletters (future), Stock Buddy signals page (users won't understand)
   - Images/slideshows must be visually striking, scroll-stopping, branded, mobile-first

4. **Account warmup plan** — gradual ramp-up for new/empty accounts:
   - X: Week 1 = 1 tweet/day, Week 2 = 2/day, Week 3+ = full cadence
   - Reddit: Weeks 1-2 = comments only, Weeks 3-4 = 1 post/few days, Month 2+ = full
   - LinkedIn: No warmup (existing 9.5K connections)
   - Facebook: Week 1 = every other day, Week 2+ = daily

5. **Weekly performance review** — weeks 1-3 collect data only, week 4+ start adjusting. Don't overreact to early data.

6. **13 new tasks created** in Task Master (17-30) covering implementation through long-term enhancements

## Important Decisions Made
- **4 platforms, not 6** — X + Reddit (active), LinkedIn + Facebook (passive). TikTok/Instagram paused.
- **New X account needed** — fresh start with new email, not existing account
- **Auto-poster = posting only** — no automated engagement. User handles X replies and Reddit comments manually.
- **Content voice: "I learnt this, maybe you can try this too"** — never claiming trading experience, never ordering people
- **1-day content buffer** — system keeps approved posts queued so it doesn't break if user misses a review day
- **Market Events Calendar kept** — FOMC, CPI, earnings dates drive topical content
- **CTA rotation** — month 1 = 100% value, month 2+ = 80/15/5 split
- **LinkedIn "I'm back" post** — do this BEFORE profile revamps (informs profile strategy)
- **Switch to Default output style** for implementation work (Brand Strategist is for content/strategy discussions)
- **Start new chat** for task 17 implementation — current conversation is strategy-heavy, implementation needs room

## Key Reference Files
- `docs/auto-poster-workflow.md` — **THE** complete E2E workflow specification (Phase 1-6)
- `docs/brand-strategy.md` — Full brand & content strategy document
- `scripts/post.py` — Main orchestrator + platform posting functions
- `scripts/generate.ps1` — Content generator (Claude CLI)
- `scripts/review_dashboard.py` — Review dashboard (localhost:5111)
- `scripts/utils/draft_manager.py` — Draft lifecycle
- `scripts/utils/human_behavior.py` — Anti-detection behaviors
- `scripts/utils/image_generator.py` — Image/video generation
- `scripts/login_setup.py` — Browser login helper
- `scripts/setup_scheduler.ps1` — Windows Task Scheduler
- `config/platforms.json` — Platform URLs, enable flags, proxy config
- `config/content-templates.md` — Brand voice, content pillars, platform format rules
- `config/.env` — Timing/behavior config
- `.claude/output-styles/brand-strategist.md` — Custom output style for brand/content work

## Memory Files
- `memory/project_platform_strategy.md` — Which platforms, why, active vs passive
- `memory/project_e2e_flow.md` — Full E2E workflow details
- `memory/user_brand_context.md` — User profile, audience, goals
- `memory/project_content_iteration.md` — Content experimentation framework (future)
- `memory/feedback_auto_commit_push.md` — Always commit and push without being asked
- `memory/feedback_value_first_content.md` — All content must deliver actionable value
- `memory/feedback_no_trading_experience.md` — Never claim trading experience

## Verified Patterns (selectors & techniques)
- **X**: `[data-testid="tweetButton"]` + `dispatch_event("click")`
- **LinkedIn**: `[role="button"]:has-text("Start a post")` → `[role="textbox"]` → `get_by_role("button", name="Post", exact=True)`
- **Facebook**: `[aria-label="What's on your mind?"]` → `[role="textbox"]` → `[aria-label="Post"]`
- **Reddit**: `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button:has-text("Post")`
- **TikTok**: Hidden `input[type="file"]` (video/*) → dismiss dialogs → `div.public-DraftEditor-content` (Ctrl+A, Backspace, type) → `button[data-e2e="post_video_button"]`
- **Instagram**: `[aria-label="New post"]` → `svg[aria-label="Post"]` → file input → `get_by_text("Next", force=True)` x2 → caption → `get_by_role("button", name="Share", force=True)`

## Test Commands
```bash
# Login setup for a platform
python scripts/login_setup.py tiktok
python scripts/login_setup.py instagram

# Run the poster (picks up next pending draft)
python scripts/post.py

# Generate drafts
powershell -File scripts/generate.ps1
powershell -File scripts/generate.ps1 -count 3

# Task Master
task-master next
task-master list --with-subtasks
task-master show 17
```
