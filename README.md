# Amplifier

Fully autonomous social media posting system that generates content via Claude Code CLI and posts to 6 platforms (X, LinkedIn, Facebook, Instagram, Reddit, TikTok) using Playwright browser automation with human behavior emulation.

## Prerequisites

- **Windows 10/11**
- **Python 3.11+**
- **Claude Code CLI** (installed and authenticated)
- **PowerShell 5.1+** (Windows default)

## Installation

```powershell
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install Playwright's Chromium browser
playwright install chromium
```

## Configuration

### `config/.env`
Non-sensitive settings: timing, delays, browsing behavior. Adjust `AUTO_POSTER_ROOT` to your project path.

### `config/content-templates.md`
Brand voice, content pillars, hooks, and platform-specific rules. Edit this to control what kind of content gets generated.

### `config/platforms.json`
Platform URLs, timeouts, enable/disable flags, per-platform proxy config, and subreddit list for Reddit.

## Usage

### 1. Login to Platforms (one-time)

```powershell
python scripts/login_setup.py x
python scripts/login_setup.py linkedin
python scripts/login_setup.py facebook
python scripts/login_setup.py instagram
python scripts/login_setup.py reddit
python scripts/login_setup.py tiktok
```

Each command opens a browser. Log in manually, complete 2FA, then close the browser. Sessions are saved in `profiles/`.

### 2. Generate Content

```powershell
# Generate 2 drafts (default)
powershell scripts/generate.ps1

# Generate a specific number
powershell scripts/generate.ps1 -count 3
```

Drafts are saved to `drafts/pending/` as JSON files.

### 3. Post Content

```powershell
python scripts/post.py
```

Picks the oldest pending draft, posts to all enabled platforms with human behavior emulation (browsing, typing delays, mouse movements), then moves the draft to `drafts/posted/` or `drafts/failed/`.

### 4. Set Up Scheduled Automation

```powershell
# Run as Administrator
powershell scripts/setup_scheduler.ps1
```

Registers two Windows Task Scheduler tasks:
- **AutoPoster-Generate**: Runs at 8 AM, 1 PM, 6 PM (2 drafts each = 6/day)
- **AutoPoster-Post**: Runs every 2 hours starting at 9 AM

## Project Structure

```
config/              Configuration files (.env, platforms.json, content-templates.md)
drafts/pending/      Drafts awaiting posting
drafts/posted/       Successfully posted drafts
drafts/failed/       Failed drafts with error info
profiles/            Persistent browser login sessions per platform (gitignored)
scripts/             Main scripts (post.py, generate.ps1, login_setup.py)
  utils/             Shared modules (draft_manager, human_behavior, image_generator)
logs/                Log files (gitignored)
```

## Troubleshooting

### Session expired (redirected to login)
Re-run `python scripts/login_setup.py <platform>` for the affected platform.

### Selectors broken (can't find compose area)
Platform UI changed. Update the selector constants at the top of each platform function in `scripts/post.py`.

### No drafts being posted
Check `drafts/pending/` for files. Check `logs/poster.log` for errors.

### TikTok posting fails with proxy/network error
TikTok is blocked in some regions. Connect a VPN (e.g. Surfshark) to a non-blocked server, or configure a SOCKS proxy in `config/platforms.json` under the `tiktok.proxy` key.

### Generator producing invalid JSON
Check `logs/generator.log`. The generator strips markdown fences and validates JSON. If Claude's output format changes, check the prompt in `scripts/generate.ps1`.

## Architecture

- **Content Generation**: PowerShell calls Claude Code CLI with content guidelines. Claude acts as a social media marketer (not a coder) and writes draft JSON files directly to `drafts/pending/`. Each draft contains platform-specific content for all 6 platforms.
- **Posting**: Python/Playwright with persistent browser profiles. Each platform gets 1-5 min of pre/post-post browsing to emulate human behavior. Platform order is randomized with 30-90s delays between platforms.
- **Image/Video Generation**: TikTok requires video uploads — the system generates a branded 1080x1920 image and converts it to a 7s MP4 with a Ken Burns zoom effect (Pillow + moviepy). Instagram generates a 1080x1080 square branded image from the caption text.
- **Anti-detection**: Character-by-character typing (30-120ms), random scrolling, mouse movements, profile clicking, randomized platform order.

## Platform Notes

- **TikTok** is geo-blocked in some regions (e.g. India). Connect a VPN before running the poster. Per-platform proxy support is available in `platforms.json`.
- **Reddit** posts to 1 random subreddit per run from the list configured in `platforms.json`.
- **Instagram** uses a multi-step dialog flow (Create → Post submenu → Upload image → crop → filter → caption → Share).
