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

# Post oldest pending draft to all enabled platforms
python scripts/post.py

# Register Windows Task Scheduler jobs (run as Admin)
powershell scripts/setup_scheduler.ps1
```

## Architecture

Two-phase pipeline: **generate** (PowerShell + Claude CLI) → **post** (Python + Playwright).

### Content Generation (`scripts/generate.ps1`)
PowerShell invokes `claude --dangerously-skip-permissions` to write draft JSON files directly to `drafts/pending/`. Must unset `CLAUDECODE` env var first to allow nested CLI calls. Each draft contains platform-specific content for all 6 platforms in a single JSON file.

### Posting (`scripts/post.py`)
Async Python orchestrator. Picks the oldest pending draft, launches a separate persistent Chromium browser context per platform (stored in `profiles/<platform>-profile/`), posts sequentially in randomized order with 30-90s delays between platforms.

Draft lifecycle: `drafts/pending/` → `drafts/posted/` (success) or `drafts/failed/` (failure). Managed by `scripts/utils/draft_manager.py`.

### Human Behavior Emulation (`scripts/utils/human_behavior.py`)
Every platform interaction includes 1-5 minutes of pre/post browsing (scrolling, profile clicks, mouse movements) and character-by-character typing (30-120ms per char with 5% chance of longer pauses). Configured via `config/.env` timing values.

### Image/Video Generation (`scripts/utils/image_generator.py`)
- **TikTok**: Generates 1080x1920 branded image → converts to 7s MP4 with Ken Burns zoom (via moviepy + Pillow + numpy). TikTok web only accepts video uploads.
- **Instagram**: Generates 1080x1080 square branded image from caption text.

## Platform-Specific Selector Patterns

Each platform function in `post.py` has selector constants at the top. Key gotchas:

- **X**: Overlay div intercepts pointer events — must use `dispatch_event("click")` on the post button, not `.click()`
- **LinkedIn**: Shadow DOM — use `page.locator().wait_for()` (pierces shadow), NOT `page.wait_for_selector()` (does not pierce)
- **Reddit**: Shadow DOM (faceplate web components) — Playwright locators pierce automatically
- **TikTok**: Draft.js editor requires `Ctrl+A → Backspace` to clear pre-filled filename before typing caption. Needs VPN (blocked in India).
- **Instagram**: Multi-step dialog flow (Create → Post submenu → Upload → Next → Next → Caption → Share). All buttons need `force=True` due to overlay intercepts.

## Configuration

- `config/platforms.json` — Enable/disable platforms, set URLs, configure subreddits and proxy per platform
- `config/.env` — Timing params (browse duration, typing delays, post intervals), not secrets
- `config/content-templates.md` — Brand voice and content rules fed to Claude during generation

## Key Constraints

- Windows-only (Windows fonts in image generator, PowerShell for generation, Task Scheduler for automation)
- Each platform needs a one-time manual login via `login_setup.py` to establish the persistent browser profile
- Per-platform proxy support in `_launch_context()` for geo-restricted platforms (configured in `platforms.json`)
- Reddit posts to 1 random subreddit per run from the configured list
- No test suite exists — verify changes by running against real platforms
