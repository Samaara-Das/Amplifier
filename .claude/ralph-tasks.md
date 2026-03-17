# Ralph Task List — Auto-Poster Workflow (Task 17)

Ralph picks the first `[ ]` task each iteration. Mark `[x]` when done.

---

## Subtask 1: Enable all 6 platforms in platforms.json
- [x] Edit `config/platforms.json` — set `enabled: true` for ALL 6 platforms (x, linkedin, facebook, instagram, reddit, tiktok)
- Removed X lock note, kept TikTok VPN note, kept Reddit subreddits
- Done: all 6 platforms enabled, JSON validated

## Subtask 2: Update posting schedule for per-platform cadence
- [x] Edit `scripts/setup_scheduler.ps1` to match the workflow spec in `docs/auto-poster-workflow.md`:
  - Slot 1 (18:30 IST / 8AM EST): X tweet #1 + LinkedIn (Tue-Fri only)
  - Slot 2 (20:30 IST / 10AM EST): Facebook post
  - Slot 3 (23:30 IST / 1PM EST): X tweet #2 + Reddit (2-3x/week)
  - Slot 4 (01:30 IST / 3PM EST): X tweet #3 or thread
  - Slot 5 (04:30 IST / 6PM EST): TikTok
  - Slot 6 (06:30 IST / 8PM EST): Instagram
- Done: Split single AutoPoster-Post task into 6 individual tasks (AutoPoster-Post-Slot-1 through -6), each passing --slot N to post.py. Removes old single-task format. Summary shows per-slot platform assignments.

## Subtask 3: Update post.py to support per-slot platform selection
- [x] Added `--slot` argument (1-6) with auto-detection from current IST time
- Added SLOT_SCHEDULE dict mapping each slot to platforms with day-of-week rules
- LinkedIn Tue-Fri only (slot 1), Reddit Tue/Thu/Sat only (slot 3), all others daily
- get_slot_platforms() filters by enabled + day of week. All platform functions unchanged.
- Verified: import OK, slot detection works, --help shows argument, platform lists correct.

## Subtask 4: Update generate.ps1 for per-platform volume
- [x] Rewrote generate.ps1 to produce one draft per posting slot (6 slots)
- Each draft targets only the platforms active for that slot on that day
- Slot schedule mirrors post.py SLOT_SCHEDULE: X in slots 1/3/4, LinkedIn Tue-Fri (slot 1), Reddit Tue/Thu/Sat (slot 3), Facebook (slot 2), TikTok (slot 5), Instagram (slot 6)
- X threads auto-detected for slot 4 on Tue/Thu
- New draft JSON fields: slot (int), platforms (array), format (post/thread)
- Added -slot param for single-slot generation
- Backward compat: -count N generates first N slots
- Validation checks that only expected platform keys exist in generated JSON

## Subtask 5: Add content pillar rotation to generate.ps1
- [x] Add pillar rotation logic to the generator:
  - Daily mix: 2x Pillar 1/3, 1x Pillar 2, 1x Pillar 4, 1x Pillar 5, 1x Wildcard
  - The prompt to Claude should specify WHICH pillar to generate for each draft
  - Track which pillars were used today (check existing drafts in review/ and pending/)
  - Content series: Backtest Wednesday (Reddit+X), Setup of the Week Monday (X+LinkedIn), One Thing I Learned Friday (all)
  - Read `docs/auto-poster-workflow.md` Phase 2 "Content Pillar Rotation" section
- Done: Added $PillarDescriptions, $DefaultPillarMap (even/odd day alternation for slots 1/4), $ContentSeries overrides (Setup of the Week Mon/slot1, Backtest Wednesday Wed/slot3, One Thing I Learned Fri/slot1). Get-PillarForSlot and Get-SeriesForSlot functions. Get-TodaysPillars scans existing drafts for dedup. Prompt now includes specific pillar + series instructions + used-today tracking. Pillar value pre-set in JSON template.

## Subtask 6: Add CTA rotation to generate.ps1
- [x] Add CTA rotation logic:
  - Need a way to track which "month" the system is in (count from first post date)
  - Month 1: 100% pure value, zero CTAs
  - Month 2+: 80% pure value, 15% soft CTA ("Free indicator — link in bio"), 5% direct CTA
  - Pass the CTA instruction into the Claude prompt so it generates the right mix
  - Store the "first post date" in config/.env as FIRST_POST_DATE (default to today if not set)
- Done: Added FIRST_POST_DATE= to config/.env. Added Get-CTAType function that parses date, calculates days since first post, returns "none" for month 1 or weighted random (80/15/5) for month 2+. Added $CTADescriptions with prompt text for none/soft/direct. CTA instruction injected into every Claude prompt. CTA type logged in generator start line.

## Subtask 7: Update draft JSON schema for new fields
- [x] Update draft_manager.py to handle new draft fields:
  - `slot` (int 1-6) — which posting slot this draft is for
  - `pillar` (string) — already exists in generate.ps1, ensure draft_manager preserves it
  - `format` (string) — "tweet", "thread", "long-form", "image-post", "video-post"
  - `platforms` (list of strings) — which platforms this draft targets (e.g. ["x", "linkedin"])
  - Update `get_next_draft()` to optionally filter by slot number
  - Update `mark_posted()` / `mark_failed()` to preserve new fields
  - Keep backward compatible with existing drafts that don't have these fields
- Done: Added optional `slot` parameter to `get_next_draft(slot=N)`. When slot is specified, it first looks for drafts with matching slot field, then falls back to unslotted drafts (backward compat), then returns None. mark_posted/mark_failed already preserve all fields (they write back the full dict). New fields (slot, pillar, format, platforms) from generate.ps1 flow through naturally.

## Subtask 8: Update post.py to use slot-filtered drafts
- [x] Now that draft_manager supports slot filtering (Subtask 7) and post.py supports slots (Subtask 3):
  - When post.py runs for a specific slot, call `get_next_draft(slot=N)` to get a draft for THAT slot
  - Only post to the platforms listed in the draft's `platforms` field
  - If no draft exists for this slot, log a warning and skip (don't post nothing)
  - Keep the retry-once-on-failure behavior from the workflow spec
- Done: main() now passes slot to get_next_draft(slot=slot). If draft has a `platforms` field, intersects it with the slot's scheduled platforms — skips if no overlap. Warns and exits cleanly if no draft found for the slot.

## Subtask 9: Update review dashboard with pillar tags and slot info
- [x] Edit `scripts/review_dashboard.py` to show new metadata:
  - Display pillar tag (color-coded badge) for each draft
  - Display target slot number and time
  - Display target platforms list
  - Display format type (tweet/thread/long-form/etc.)
  - Show image preview if draft has image_text field (already partially done)
  - Keep the existing approve/reject/edit functionality unchanged
- Done: Added PILLAR_COLORS (6 pillars with bg/text colors), SLOT_TIMES (1-6 mapped to EST times). Draft cards now show color-coded pillar badge, slot+time badge, format badge, platforms badge, and image_text preview. All existing functionality unchanged.

## Subtask 10: Add content buffer logic
- [x] Implement 1-day content buffer per the workflow spec:
  - In draft_manager.py, add a function `get_buffer_status()` that counts approved (pending) drafts per slot
  - If buffer has 0 drafts for any slot, the system should generate extra drafts
  - In generate.ps1, check buffer status before generating — if buffer is healthy (1+ day ahead), generate only tomorrow's content
  - If buffer is empty, generate 2 days worth (today + tomorrow)
  - Add a simple buffer check: `python -c "from scripts.utils.draft_manager import get_buffer_status; print(get_buffer_status())"`
- Done: Added get_buffer_status() to draft_manager.py — counts pending drafts per slot (1-6) plus unslotted, returns total and empty_slots count. Added Get-BufferStatus function to generate.ps1 that calls Python to check buffer. When buffer is healthy (all slots have pending drafts) and no explicit -slot or -count flag, skips slots that already have pending drafts. When buffer has gaps, generates all slots normally.

## Subtask 11: Add failure retry logic to post.py
- [x] Currently post.py moves failed drafts to failed/ immediately. Update per workflow spec:
  - On failure: wait 5 minutes, retry once
  - If retry fails: move to drafts/failed/, log the error
  - Failed drafts should be visible in the review dashboard for manual retry
  - Add a "retry_count" field to track retries
- Done: Added RETRY_DELAY_SEC (300s default) config. Per-platform retry in main(): on failure, waits 5 min, retries once, logs result. Tracks retry_count and retried_platforms on draft. Added get_failed_drafts() and retry_failed_draft() to draft_manager.py. Review dashboard now shows failed drafts section (red-bordered cards with error, retry count, and "Retry" button to move back to pending).

## Subtask 12: Add legal disclaimers to generate.ps1
- [x] Ensure the generator prompt includes legal disclaimer rules from the workflow spec:
  - X: "NFA. Educational only." at end of tweet
  - Reddit: Full disclaimer paragraph at bottom
  - LinkedIn/Facebook: "Not financial advice. For educational purposes only." at bottom
  - Setup-based posts: "These are just for educational and entertainment purposes."
  - Backtest posts: "Past performance does not guarantee future results."
  - Pure educational / engagement posts: no disclaimer needed
  - Read `docs/auto-poster-workflow.md` "Legal Disclaimers" section for exact wording
- Done: Added LEGAL DISCLAIMERS section to the Claude prompt in generate.ps1. Per-platform disclaimer rules (X/Reddit/LinkedIn/Facebook/TikTok/Instagram), plus conditional disclaimers for setup and backtest posts. Posts that don't need disclaimers (pure education, engagement, Pillar 5 AI/career) are excluded.

## Subtask 13: Auto-react and repost on all 6 platforms
- [ ] Add automated engagement to post.py — after posting, the system should also react to and repost OTHER people's content on each platform. This makes the account look active and human, not a broadcast bot. NO commenting (that stays manual).
- **Per-platform behavior:**
  - **X**: Like 5-10 tweets in the feed + Retweet 1-2 relevant tweets. Use `[data-testid="like"]` and `[data-testid="retweet"]` buttons. Target FinTwit/trading content.
  - **LinkedIn**: Like 3-5 posts in the feed. Use the Like button (reaction button). Repost 1 relevant post per session.
  - **Facebook**: React to 3-5 posts in the feed (Like button). Share 1 relevant post.
  - **Instagram**: Like 5-10 posts in the feed. Use the heart button `[aria-label="Like"]`.
  - **Reddit**: Upvote 5-10 posts in target subreddits (configured in platforms.json). Use the upvote button.
  - **TikTok**: Like 3-5 videos in the feed. Use the heart/like button.
- **Implementation approach:**
  - Create a new function `auto_engage(page, platform)` in `scripts/utils/human_behavior.py` (it already has `browse_feed` — extend it)
  - Call `auto_engage()` during the existing pre/post browsing phase (don't add a separate step)
  - Use random delays between each like/repost (human_delay pattern already exists)
  - Scroll the feed naturally (reuse existing browse_feed scrolling logic), find interactive elements, engage
  - Keep engagement counts randomized within ranges (e.g., 5-10 likes, not exactly 7 every time)
  - Log all engagement actions to poster.log
- **Safety:**
  - Add a per-platform daily engagement cap in config/.env (e.g., MAX_LIKES_X=15, MAX_RETWEETS_X=3)
  - Track daily engagement counts in a simple JSON file (`logs/engagement-tracker.json`) — reset daily
  - If cap reached, skip engagement for that platform
  - Never engage with content that has sensitive/political keywords (add a basic blocklist)
- **Selectors:** Read each platform's posting function in post.py first to understand the existing page state and selector patterns. Use the same Playwright patterns (locator-based, force=True where needed, dispatch_event where overlays intercept).

---

## Notes
- After ALL subtasks are [x], output: RALPH_ALL_TASKS_COMPLETE
- Do NOT change working platform selectors in post.py
- Do NOT add tests — verify with import checks and python -c
- Read every file before editing
- Keep changes minimal per subtask
