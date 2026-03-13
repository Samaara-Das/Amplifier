# Auto-Posting System — Task Context

**Last Updated**: 2026-03-13

## Current Task
- **ALL TASKS COMPLETE** — 16/16 tasks done, all 6 platforms E2E tested and working
- System is feature-complete and ready for production use

## Task Progress Summary

### Completed (16/16 tasks — 100%)
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

### No blockers remaining

## Session History

### Session 1 (2026-03-07) — MVP Build
- Built entire system from scratch following 10-task implementation plan
- Scaffolded project: dirs, config, requirements, .env
- Implemented content generator (PowerShell + Claude CLI)
  - Fixed CLAUDECODE env var blocking nested CLI calls
  - Fixed Claude writing files instead of stdout — changed to agent-mode file writing
- Implemented draft manager, human behavior emulation
- Built posting functions for X, LinkedIn, Facebook
  - **X**: `dispatch_event("click")` needed to bypass overlay div on tweet button
  - **LinkedIn**: Shadow DOM — `wait_for_selector()` fails, must use `locator().wait_for()`
  - **LinkedIn**: "Post" button ambiguity — `get_by_role("button", name="Post", exact=True)` fixes it
- E2E tested X, LinkedIn, Facebook — all working
- Added Reddit and TikTok support
  - Reddit uses shadow DOM (faceplate web components) — same locator pattern as LinkedIn
  - Reddit E2E tested and working
  - TikTok code complete but blocked (TikTok banned in India)
  - TikTok image generator built with Pillow (branded text-on-image, color schemes)

### Session 2 (2026-03-08) — Instagram, BlueSky removal, Tooling
- Added BlueSky + Instagram posting functions and image generators
- Set up project tooling (Task Master CLI, slash commands, task-context.md)
- **Removed BlueSky integration** (task 10) from all files
- **Updated TikTok config**: Removed SOCKS proxy, using Surfshark VPN system-wide
- **Instagram login setup completed**
- TikTok login attempted — blocked on phone app verification (app not on Indian Play Store)

### Session 3 (2026-03-13) — Instagram E2E (parallel session)
- **Instagram E2E tested and working** — required multiple selector iterations:
  - Create button: `[aria-label="New post"]` opens submenu, then click `svg[aria-label="Post"]`
  - Upload: file input via `input[type="file"]` inside dialog
  - Next buttons: `get_by_text("Next")` scoped to dialog + `force=True` (overlay intercepts)
  - Caption: `div[aria-label="Write a caption..."]`
  - Share: `get_by_role("button", name="Share", exact=True)` with `force=True` (2 Share elements exist — "Share" and "Share to")
  - Confirmation: wait for "Sharing" text → wait for dialog to close (up to 2 min for upload)

### Session 4 (2026-03-13) — TikTok E2E Complete
- **TikTok login completed** — user logged in via Google (email/password was rate-limited)
- **Key discovery**: TikTok web **only supports video uploads**, not photo posts
  - Original approach (upload PNG image) failed — `input[type="file"]` accepts `video/*` only
  - Installed `moviepy` + `imageio-ffmpeg` for image-to-video conversion
  - Created `generate_tiktok_video()` in `image_generator.py`:
    - Generates branded image (Pillow, 1080x1920)
    - Converts to 7-second MP4 with slow Ken Burns zoom effect (1.0x → 1.08x)
    - Uses libx264 codec, 24fps, no audio
- **Updated `post_to_tiktok()`** with correct post-upload flow:
  - Upload video via hidden `input[type="file"]` (no visibility check needed)
  - Dismiss "Turn on automatic content checks?" dialog via `Cancel` button
  - Dismiss "Got it" tooltip
  - Caption field: Draft.js editor (`div.public-DraftEditor-content`, role="combobox")
  - Must Ctrl+A → Backspace to clear pre-filled filename before typing caption
  - Post button: `button[data-e2e="post_video_button"]`
- **TikTok E2E test passed** — full flow working
- Enabled TikTok in `platforms.json`
- Marked all TikTok tasks (9, 9.5, 16) as done
- Cleaned up debug/test files

## Important Decisions Made
- **Playwright persistent contexts** for session reuse (no stored passwords, cookie-based auth)
- **`dispatch_event("click")`** over `.click()` when overlay divs intercept pointer events (X)
- **`locator().wait_for()`** over `wait_for_selector()` for shadow DOM platforms (LinkedIn, Reddit)
- **Surfshark VPN system-wide** instead of per-platform SOCKS proxy for TikTok
- **Claude CLI as agent** (--dangerously-skip-permissions) writes files directly, script validates after
- **Instagram requires image** — generates branded square image from caption text
- **TikTok requires video** — web creator center has no photo upload; generate MP4 from branded image
- **Platform order randomized** each run, 30-90s delays between platforms
- **1 random subreddit per run** to avoid spam detection
- **BlueSky removed** — user decided not to support BlueSky in v1
- **Instagram dialog buttons are DIVs, not buttons** — use `get_by_text`/`get_by_role` + `force=True`
- **TikTok login via Google** — email/password got rate-limited, Google OAuth worked

## Key Reference Files
- `scripts/post.py` — Main orchestrator + 6 platform posting functions
- `scripts/generate.ps1` — Content generator (Claude CLI, 6 platforms)
- `scripts/utils/draft_manager.py` — Draft lifecycle
- `scripts/utils/human_behavior.py` — Anti-detection behaviors
- `scripts/utils/image_generator.py` — TikTok video + Instagram image generation (moviepy, Pillow)
- `scripts/login_setup.py` — Browser login helper (6 platforms)
- `config/platforms.json` — Platform URLs, enable flags
- `config/content-templates.md` — Brand voice, platform rules
- `config/.env` — Timing/behavior config

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

# Task Master commands
task-master list --with-subtasks
task-master next
task-master set-status --id=<id> --status=done
```
