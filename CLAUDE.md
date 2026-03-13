# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# One-time login for a platform (opens browser for manual login + 2FA)
python scripts/login_setup.py <platform>   # x | linkedin | facebook | instagram | reddit | tiktok

# Generate drafts (calls Claude Code CLI internally)
powershell scripts/generate.ps1            # default count from .env (GENERATE_COUNT)
powershell scripts/generate.ps1 -count 3

# Review generated drafts before posting
python scripts/review_dashboard.py         # opens http://localhost:5111

# Post oldest approved draft to all enabled platforms
python scripts/post.py

# Register Windows Task Scheduler jobs (run as Admin)
powershell scripts/setup_scheduler.ps1
```

## Architecture

Three-phase pipeline: **generate** (PowerShell + Claude CLI) → **review** (Flask dashboard) → **post** (Python + Playwright).

### Content Generation (`scripts/generate.ps1`)
PowerShell invokes `claude --dangerously-skip-permissions` to write draft JSON files directly to `drafts/review/`. Must unset `CLAUDECODE` env var first to allow nested CLI calls. Each draft contains platform-specific content for all 6 platforms in a single JSON file. Supports text-only and text+image formats (X, LinkedIn, Facebook can use either).

### Review Dashboard (`scripts/review_dashboard.py`)
Flask app on localhost:5111. Shows all drafts in `drafts/review/` with platform-by-platform previews, character counts, and edit capability. User approves or rejects each draft. Approved drafts move to `drafts/pending/`, rejected to `drafts/rejected/`. Nothing gets posted without explicit approval.

### Posting (`scripts/post.py`)
Async Python orchestrator. Picks the oldest pending (approved) draft, launches a separate persistent Chromium browser context per platform (stored in `profiles/<platform>-profile/`), posts sequentially in randomized order with 30-90s delays between platforms. Supports headless mode via `HEADLESS=true` in `.env`.

Draft lifecycle: `drafts/review/` → `drafts/pending/` (approved) → `drafts/posted/` (success) or `drafts/failed/` (failure). Also `drafts/rejected/` for rejected drafts. Managed by `scripts/utils/draft_manager.py`.

### Human Behavior Emulation (`scripts/utils/human_behavior.py`)
Every platform interaction includes 1-5 minutes of pre/post browsing (scrolling, profile clicks, mouse movements) and character-by-character typing (30-120ms per char with 5% chance of longer pauses). Configured via `config/.env` timing values.

### Image/Video Generation (`scripts/utils/image_generator.py`)
- **X, LinkedIn, Facebook**: Generates 1200x675 landscape branded image when draft has `image_text` field. Text-only posts skip image generation.
- **TikTok**: Generates 1080x1920 branded image → converts to 7s MP4 with Ken Burns zoom (via moviepy + Pillow + numpy). TikTok web only accepts video uploads.
- **Instagram**: Generates 1080x1080 square branded image from caption text.

## Platform-Specific Selector Patterns

Each platform function in `post.py` has selector constants at the top. Key gotchas:

- **X**: Overlay div intercepts pointer events — must use `dispatch_event("click")` on the post button, not `.click()`. Image upload via hidden `input[data-testid="fileInput"]`.
- **LinkedIn**: Shadow DOM — use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()` (does not pierce). Image upload via file input or `expect_file_chooser`.
- **Facebook**: Image upload via "Photo/video" button then hidden file input.
- **Reddit**: Shadow DOM (faceplate web components) — Playwright locators pierce automatically
- **TikTok**: Draft.js editor requires `Ctrl+A → Backspace` to clear pre-filled filename before typing caption. Needs VPN (blocked in India).
- **Instagram**: Multi-step dialog flow (Create → Post submenu → Upload → Next → Next → Caption → Share). All buttons need `force=True` due to overlay intercepts.

## Configuration

- `config/platforms.json` — Enable/disable platforms, set URLs, configure subreddits and proxy per platform
- `config/.env` — Timing params (browse duration, typing delays, post intervals), headless mode, not secrets
- `config/content-templates.md` — Brand voice, content pillars, emotion-first + value-first principles, platform format rules

## Scheduling (US-aligned)

Generation runs at 09:00 IST (user reviews during the day). Posting at 6 daily slots:
- 18:30, 20:30, 23:30, 01:30, 04:30, 06:30 IST = 8AM, 10AM, 1PM, 3PM, 6PM, 8PM EST

## Key Constraints

- Windows-only (Windows fonts in image generator, PowerShell for generation, Task Scheduler for automation)
- Each platform needs a one-time manual login via `login_setup.py` to establish the persistent browser profile
- Per-platform proxy support in `_launch_context()` for geo-restricted platforms (configured in `platforms.json`)
- Currently only X, LinkedIn, Facebook enabled. Instagram, Reddit, TikTok disabled for now.
- Reddit posts to 1 random subreddit per run from the configured list
- No test suite exists — verify changes by running against real platforms
