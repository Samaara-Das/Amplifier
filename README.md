# Auto-Poster System

Fully autonomous social media posting system that generates content via Claude Code CLI and posts to X, LinkedIn, and Facebook using Playwright browser automation with human behavior emulation.

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
Platform URLs, timeouts, and enable/disable flags. Instagram is disabled by default.

## Usage

### 1. Login to Platforms (one-time)

```powershell
python scripts/login_setup.py x
python scripts/login_setup.py linkedin
python scripts/login_setup.py facebook
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
config/              Configuration files
drafts/pending/      Drafts awaiting posting
drafts/posted/       Successfully posted drafts
drafts/failed/       Failed drafts with error info
profiles/            Persistent browser login sessions (gitignored)
scripts/             Main scripts
  utils/             Shared modules (draft manager, human behavior)
logs/                Log files (gitignored)
```

## Troubleshooting

### Session expired (redirected to login)
Re-run `python scripts/login_setup.py <platform>` for the affected platform.

### Selectors broken (can't find compose area)
Platform UI changed. Update the selector constants at the top of each platform function in `scripts/post.py`.

### No drafts being posted
Check `drafts/pending/` for files. Check `logs/poster.log` for errors.

### Generator producing invalid JSON
Check `logs/generator.log`. The generator strips markdown fences and validates JSON. If Claude's output format changes, check the prompt in `scripts/generate.ps1`.

## Architecture

- **Content Generation**: PowerShell calls Claude Code CLI with content guidelines. Claude acts as a social media marketer (not a coder) and outputs structured JSON.
- **Posting**: Python/Playwright with persistent browser profiles. Each platform gets 1-5 min of pre/post-post browsing to emulate human behavior.
- **Anti-detection**: Character-by-character typing (30-120ms), random scrolling, mouse movements, profile clicking, randomized platform order, 30-90s delays between platforms.
