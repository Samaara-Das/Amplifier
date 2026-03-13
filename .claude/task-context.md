# Auto-Posting System — Task Context

**Last Updated**: 2026-03-13

## Current Task
- **Brand Strategy Development** — system posts to 6 platforms but lacks a personal brand building strategy. Currently in strategy design phase.

## Task Progress Summary

### Completed (16/16 implementation tasks — 100%)
- [x] Project scaffolding (dirs, config, requirements.txt)
- [x] Content generator (`scripts/generate.ps1`) — Claude CLI writes 6-platform JSON drafts
- [x] Draft manager (`scripts/utils/draft_manager.py`) — pending → posted/failed lifecycle
- [x] Human behavior emulation (`scripts/utils/human_behavior.py`) — typing, scrolling, mouse, browse_feed
- [x] Login setup helper (`scripts/login_setup.py`) — supports 6 platforms
- [x] Platform config (`config/platforms.json`) — 6 platforms with enable flags
- [x] Brand voice & content templates (`config/content-templates.md`)
- [x] Windows Task Scheduler setup (`scripts/setup_scheduler.ps1`)
- [x] Main orchestrator (`scripts/post.py`)
- [x] X (Twitter) posting — E2E tested, working
- [x] LinkedIn posting — E2E tested, working (shadow DOM piercing with locators)
- [x] Facebook posting — E2E tested, working
- [x] Reddit posting — E2E tested, working (shadow DOM, faceplate components)
- [x] TikTok posting — E2E tested, working (video upload via moviepy)
- [x] Instagram posting — E2E tested, working (dialog overlay, force clicks)
- [x] Remove BlueSky Integration (task 10) — fully removed from all files

### Brand Strategy (In Progress)
- [x] Created custom output style: `.claude/output-styles/brand-strategist.md`
- [x] Embedded Emotion-First Principle into output style (non-negotiable)
- [x] Scraped LinkedIn profile (~90+ posts reviewed) and TradingView profile (2 ideas, 5 scripts)
- [x] Built comprehensive user context file: `memory/user_brand_context.md`
- [x] Drafted full brand strategy (identity, 5 content pillars, platform strategy, posting schedule, monetization funnel, channel partner strategy)
- [x] User CONFIRMED: posting schedule (US-aligned), content pillars, platform priorities, monetization funnel, branding, brand identity
- [x] Brand identity reframed: NOT "tool builder" → "the person who helps people achieve financial freedom, side hustle, financial security"
- [x] Full comprehensive strategy document written: `docs/brand-strategy.md` (brand foundation, 5 audience personas, 5 pillar deep-dives with platform-specific formats, 6 platform playbooks, 30+ hook templates, daily/weekly content calendar, monetization funnel, channel partner strategy, growth milestones)
- [x] Output style updated with all confirmed decisions
- [x] Update `config/content-templates.md` to encode the finalized strategy (complete rewrite with emotion-first + value-first principles, 5 pillars, platform formats)
- [x] Update `scripts/setup_scheduler.ps1` to align posting times with US timezone (6 IST slots: 18:30, 20:30, 23:30, 01:30, 04:30, 06:30 = EST 8AM-8PM)
- [ ] Content experimentation & review framework (next discussion — weekly/bi-weekly review of what posts work, do more of winners)
- [ ] Discuss how to make the entire system autonomous with user giving max 10 minutes/day
- [ ] Find/integrate AI video generation tool for TikTok and Instagram (using slideshows for now)

## Session History

### Sessions 1-4 (2026-03-07 to 2026-03-13) — MVP Build & E2E Testing
- Built entire auto-posting system from scratch
- All 6 platforms E2E tested and working (X, LinkedIn, Facebook, Reddit, TikTok, Instagram)
- Key technical discoveries: shadow DOM piercing, overlay click workarounds, TikTok video-only uploads, Draft.js editor handling
- Full details in previous session logs (system is feature-complete)

### Session 5 (2026-03-13) — Brand Strategy Development
1. **Output Style created** — `.claude/output-styles/brand-strategist.md` with `keep-coding-instructions: true`
   - User taught me what Claude Code output styles are (modifies system prompt)
   - Created at project level for brand strategy work
   - Added builder-educator positioning, platform strategies, anti-patterns

2. **Emotion-First Principle embedded** — User emphasized ALL content must lead with emotion
   - People don't care about indicators or technical concepts
   - They respond to: greed, security, financial stability, side hustle, earning money, fear of AI
   - Added as non-negotiable section in output style with 8 specific emotional triggers and good/bad examples
   - Platform-specific emotional hooks added

3. **User context gathered from arscontexta** — identity, goals, relationships, projects

4. **LinkedIn profile scraped** (Chrome DevTools MCP, ~90+ posts):
   - 9,497 connections, 737 impressions/week despite 1-2 years dormant
   - Headline: "Financial Market Algorithm Developer | Happy to share my free algos"
   - 3 roles: Market DaVinci (algos, ICT learning modules), PoolsiFi (50+ strategies, TTE, ML algos), FCMB Bank UK (frontend)
   - Content: mostly trading education (Elliott Wave, Ichimoku, liquidity, moving averages, supply/demand, divergences, risk management, trading psychology, automation advocacy)
   - Style: "in simple English", structured lists, step-by-step, moderate emojis
   - Cross-posted same content 3-5x to LinkedIn groups
   - Best performers: practical how-tos (liquidity 27 reactions, trading plans 35, moving averages 21)

5. **TradingView profile reviewed**:
   - 357 followers, Premium account, joined Oct 2021
   - 5 scripts: structure break indicator (267 boosts), RSI divergence (237 boosts), indicators library, AO divergence library, stoch+supertrend strategy
   - 2 ideas: Supply & Demand Part 1, Elliott Wave labeling (both educational)

6. **Full brand strategy drafted** with these components:
   - **Brand identity**: builder-educator, not guru. Hide age (17) and location (India). US-only positioning.
   - **5 content pillars**: "Stop Losing Money" (fear), "Make Money While You Sleep" (greed/automation), "The Market Cheat Code" (competence/edge), "Proof Not Promises" (trust/data), "Future-Proof Your Income" (AI fear/stability)
   - **Platform priorities**: Tier 1 = TikTok + X, Tier 2 = Instagram + Reddit, Tier 3 = LinkedIn + Facebook
   - **Posting schedule fix**: Current IST schedule misses US audience. Proposed US-aligned times (6:30PM-6:30AM IST = 8AM-8PM EST)
   - **Monetization funnel**: Free content → free TradingView indicators → $20/month paid indicators/strategies
   - **Channel partner strategy**: shareable content, engagement pods, tag-a-friend CTAs, eventual referral program
   - **Content mix**: 50% education, 20% aspiration, 15% proof, 15% topical/engagement

7. **Key user details captured**:
   - 17 years old, doesn't want people to know his age
   - Father is trading expert with 30+ years experience, builds strategies/indicators
   - Targets US audience ONLY — teens (8th grade+), housewives, professional traders, working professionals, people afraid of AI
   - Plans to sell indicators/strategies at $20/month
   - All 6 social accounts are fresh (zero posts) except LinkedIn and TradingView
   - AI video tool for TikTok/Instagram TBD — using slideshows for now
   - Built Stock Buddy (AI app: teaches markets, proprietary indicators/strategies, signals, performance tracking, groups, 1000+ instruments)
   - TradingView chosen as primary platform for publishing indicators/strategies (free, accessible, looks good)

8. **Content experimentation framework** — noted for future discussion. Will build a testing and iteration loop: experiment with content types, track metrics per platform weekly/bi-weekly, double down on winners, kill losers.

9. **Full brand strategy document written** — `docs/brand-strategy.md` containing:
   - Brand foundation (voice table, positioning, what you never do)
   - 5 detailed audience personas (teens, housewives, professionals, traders, AI-fearful) with emotional triggers, platforms, and path to $20/month
   - 5 content pillars deep-dived with specific content angles, platform-specific formats, and example posts
   - 6 platform playbooks (TikTok, X, Instagram, Reddit, LinkedIn, Facebook) with tactics, formats, growth strategies
   - 30+ hook templates organized by emotional trigger (fear, greed, competence, trust, AI fear, engagement)
   - Daily content calendar (6 slots mapped to IST/EST with pillar assignments)
   - Weekly rhythm (themed days: Backtest Wednesdays, Aspiration Thursdays, etc.)
   - Monetization funnel (3 stages over weeks 1-13+: Attention → Trust → Conversion)
   - Channel partner strategy (find, activate, types)
   - Growth milestones (Phase 1-4 over 12 months, targets from 500 to 50K+ followers)
   - Brand rules quick reference (always do / never do)

10. **User confirmed brand identity reframe** — NOT "tool builder" but "the person who helps people achieve financial freedom, have a side hustle, get the life they want, secure them financially." Content must be fun to watch/see and grab attention.

11. **Output style fully updated** with all confirmed decisions — brand identity, content pillars, audience segments, platform tiers, posting schedule, monetization, anti-patterns including age/location hiding

## Important Decisions Made
- **Output style over skill/subagent** for brand strategy work — modifies entire thinking mode
- **Emotion-first is non-negotiable** — every post must lead with emotional hook, deliver substance after
- **US-only targeting** — all content uses US markets (SPY, AAPL), USD, American English, US timezone posting
- **Age hidden** — never reference school, college, generation. Content should be ageless.
- **Location hidden** — no Indian references, no IST, no rupee
- **TradingView as primary tool platform** — free, accessible, where indicators/strategies will be published
- **Slideshows first, AI video later** — for TikTok and Instagram until AI video tool is figured out
- **Personal brand (Samaara Das)** — not a company name
- **$20/month subscription model** — affordable, needs volume
- **Posting schedule confirmed**: IST 6:30PM-6:30AM = EST 8AM-8PM (6 slots)
- **Brand identity**: NOT "tool builder" → "the person who helps people achieve financial freedom"
- **Content must be fun, attention-grabbing, scroll-stopping** — never dry or boring

## Key Reference Files
- `scripts/post.py` — Main orchestrator + 6 platform posting functions
- `scripts/generate.ps1` — Content generator (Claude CLI, 6 platforms)
- `scripts/utils/draft_manager.py` — Draft lifecycle
- `scripts/utils/human_behavior.py` — Anti-detection behaviors
- `scripts/utils/image_generator.py` — TikTok video + Instagram image generation
- `scripts/login_setup.py` — Browser login helper (6 platforms)
- `config/platforms.json` — Platform URLs, enable flags
- `config/content-templates.md` — Brand voice, platform rules (NEEDS UPDATE with new strategy)
- `config/.env` — Timing/behavior config
- `.claude/output-styles/brand-strategist.md` — Custom output style for brand strategy work (fully updated with all confirmed decisions)
- `docs/brand-strategy.md` — **THE** comprehensive brand & content strategy document
- `memory/user_brand_context.md` — Comprehensive user profile, audience, goals, LinkedIn/TradingView analysis
- `memory/project_content_iteration.md` — Planned content experimentation framework

## Next Discussions (Upcoming)
1. **Content experimentation & review framework** — weekly/bi-weekly review of what posts work, track metrics per platform, do more of winners, kill losers
2. **Autonomous operation** — how to make the entire system run with user giving max 10 minutes/day

## Verified Patterns (selectors & techniques)
- **X**: `[data-testid="tweetButton"]` + `dispatch_event("click")`
- **LinkedIn**: `[role="button"]:has-text("Start a post")` → `[role="textbox"]` → `get_by_role("button", name="Post", exact=True)`
- **Facebook**: `[aria-label="What's on your mind?"]` → `[role="textbox"]` → `[aria-label="Post"]`
- **Reddit**: `textarea[name="title"]` → `[role="textbox"][name="body"]` → `button:has-text("Post")`
- **TikTok**: Hidden `input[type="file"]` (video/*) → dismiss "Cancel"/"Got it" dialogs → `div.public-DraftEditor-content` for caption (Ctrl+A, Backspace, then type) → `button[data-e2e="post_video_button"]`
- **Instagram**: `[aria-label="New post"]` → `svg[aria-label="Post"]` submenu → file input in dialog → `get_by_text("Next", force=True)` x2 → `div[aria-label="Write a caption..."]` → `get_by_role("button", name="Share", exact=True, force=True)` → wait for "Sharing" spinner → dialog close

## Test Commands
```bash
# Login setup for a platform
python scripts/login_setup.py tiktok
python scripts/login_setup.py instagram

# Run the poster (picks up next pending draft)
python scripts/post.py

# Generate drafts
powershell -File scripts/generate.ps1

# Generate a specific number of drafts
powershell -File scripts/generate.ps1 -count 3
```
