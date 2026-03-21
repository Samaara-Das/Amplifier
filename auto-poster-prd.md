# Amplifier — Product Requirements Document

## Document Info
- **Version**: 1.1
- **Last Updated**: 2026-03-07
- **Author**: Sammy
- **Status**: Final

---

## 1. Overview

### 1.1 Problem Statement
Manually posting content across multiple social media platforms (X, LinkedIn, Facebook, Instagram, BlueSky) is time-consuming and inconsistent. Existing API-based solutions are either paid (X API), restrictive, or require complex app approval processes (Meta, LinkedIn). A system is needed that automates both content creation and cross-platform posting from a local Windows desktop using browser automation.

### 1.2 Proposed Solution
Build an auto-posting system that runs on a Windows desktop with two main components:

1. **Content Generator** — A PowerShell script that calls Claude Code in non-interactive mode (with `--dangerously-skip-permissions`) to generate platform-specific social media content. Claude Code's output style is changed via the prompt so it behaves as a social media marketer/manager — it does NOT produce code, technical explanations, or coder-style output. It writes exclusively as a content creator crafting engaging social media posts. Generated content is saved as structured JSON draft files. The system generates 6 drafts per day (run 3 times daily, 2 drafts per run).

2. **Poster** — A Python script using Playwright (the chosen browser automation framework — see Section 5.4 for rationale) with persistent browser profiles that picks up draft files and posts content to each social media platform via browser automation. The script emulates human behavior extensively — not just during posting, but also before and after each post by browsing the feed, scrolling through posts, clicking on user profiles, and spending 1-5 minutes per platform behaving like a real user. Dedicated fake accounts are created on X, Instagram, and LinkedIn specifically for this system.

Both scripts are scheduled via Windows Task Scheduler and only run while the desktop is powered on.

### 1.3 Goals & Success Metrics

| Goal | Metric | Target |
|------|--------|--------|
| Automate content creation | Drafts generated per day without manual input | 6 drafts/day |
| Post to all target platforms | Successful post rate per platform | >90% success rate |
| Avoid bot detection | Account flags/locks/bans | Zero |
| Minimize maintenance | Time spent fixing broken selectors per month | <30 minutes |
| Content quality | Posts feel human-written and platform-native | No manual review — fully autonomous |

### 1.4 Out of Scope
- Image generation or media creation (text-only posts for v1)
- Engagement automation (likes, comments, follows, retweets) — note: the poster DOES passively browse feeds and click profiles to emulate human behavior, but does NOT actively engage (no likes/comments/follows)
- Analytics or performance tracking
- Mobile app automation
- Comment/reply management
- VPS or cloud deployment (runs only on local Windows desktop)
- BlueSky posting (already handled by existing OpenClaw bot)
- Manual review or approval of drafts — the system is fully autonomous

### 1.5 Account Strategy
- **Fake/dedicated accounts** will be created on X, Instagram, and LinkedIn specifically for this system
- These are NOT Sammy's personal accounts — they are purpose-built accounts for automated posting
- The accounts will be set up manually and logged in once via the `login_setup.py` helper
- Facebook account: TBD (may use existing or create new)

---

## 2. User Stories & Requirements

### 2.1 User Persona

**Sammy — Frontend Lead & Content Creator**
- Role: Developer and social media presence builder
- Goals: Maintain consistent posting cadence across platforms without spending time on it manually
- Pain Points: Manually writing and posting to 4+ platforms is tedious; API access is paid or restrictive; previous VPS-based browser automation attempts timed out due to datacenter IP detection
- Technical Level: Advanced (Python, Next.js, TypeScript, PowerShell, Playwright)

### 2.2 User Stories

#### Epic 1: Content Generation

| ID | Story | Priority | Acceptance Criteria |
|----|-------|----------|---------------------|
| US-001 | As Sammy, I want to run a single command that generates social media content so that I don't have to write posts manually | P0 | - Script calls Claude Code in non-interactive mode via PowerShell<br>- Claude Code generates content following provided templates/hooks<br>- Output is a valid JSON draft file saved to the pending drafts folder |
| US-002 | As Sammy, I want each draft to contain platform-specific variants so that content feels native to each platform | P0 | - Draft JSON has separate fields for X (≤280 chars), LinkedIn (professional tone), Facebook (conversational), Instagram (emoji/hashtag-heavy), and BlueSky (≤300 chars)<br>- Each variant reads differently, not just copy-pasted |
| US-003 | As Sammy, I want to define content templates, hooks, brand voice, and content pillars in a config file so that I can control the style of generated content | P0 | - A markdown file exists at `config/content-templates.md`<br>- Claude Code reads this file as part of its prompt<br>- Content follows the defined guidelines |
| US-004 | As Sammy, I want 6 drafts generated per day so that I have enough content for regular posting | P0 | - The generate script accepts an optional `--count N` parameter (default 2)<br>- The script is scheduled to run 3 times per day, generating 2 drafts each time (6 total)<br>- Each draft is saved as a separate JSON file with a unique ID |

#### Epic 2: Draft Management

| ID | Story | Priority | Acceptance Criteria |
|----|-------|----------|---------------------|
| US-005 | As Sammy, I want drafts organized by status so that I can track what's pending, posted, or failed | P0 | - Three folders exist: `drafts/pending/`, `drafts/posted/`, `drafts/failed/`<br>- Draft files move between folders based on posting outcome |
| US-006 | As Sammy, I want each draft file to contain metadata so that I can audit what was posted and when | P0 | - Draft JSON includes: `id`, `created_at`, `status`, `content` (with platform variants), `topic`<br>- After posting: `posted_at`, `platforms_posted` fields are added<br>- After failure: `failed_at`, `error` fields are added |
| US-007 | As Sammy, I want the poster to pick the oldest pending draft so that content is posted in the order it was created | P0 | - Drafts are sorted by file modification time (oldest first)<br>- The poster picks the first one |

#### Epic 3: Browser Automation Posting

| ID | Story | Priority | Acceptance Criteria |
|----|-------|----------|---------------------|
| US-008 | As Sammy, I want to log into each platform manually once and have the system reuse that session forever so that I never store passwords in code | P0 | - A `login_setup.py` helper script launches a persistent Playwright browser for a given platform<br>- I log in manually, complete any 2FA<br>- Session cookies/state are saved in a per-platform profile folder<br>- The poster script reuses these profiles without ever needing credentials |
| US-009 | As Sammy, I want the poster to open each platform, navigate to the compose UI, type the content, and submit the post | P0 | - For each platform (X, LinkedIn, Facebook, Instagram), a dedicated posting function exists<br>- Each function: opens the platform → navigates to compose → enters text → clicks post<br>- Uses stable selectors (aria labels, roles, data-testid attributes) over CSS classes<br>- Returns success/failure boolean |
| US-010 | As Sammy, I want the poster to emulate human behavior extensively so that platforms cannot detect it as a bot | P0 | - **Pre-post browsing**: Before making a post, the script spends 1-5 minutes (randomized) on the platform browsing the feed — scrolling through posts, stopping on a few, clicking on a user profile, reading for a moment, going back to the feed<br>- **During posting**: Character-by-character typing with random 30-120ms delays between keystrokes, with a 5% chance of a 300-800ms pause after any character<br>- **Post-post browsing**: After posting, the script spends another 1-5 minutes (randomized) browsing — scrolling the feed, viewing posts, clicking on profiles — before closing the browser<br>- Random mouse movements to non-interactive areas throughout<br>- The browser runs in headed mode (not headless) with `--disable-blink-features=AutomationControlled` flag<br>- 30-90 second wait between closing one platform's browser and opening the next |
| US-011 | As Sammy, I want the poster to handle failures gracefully so that one platform failing doesn't block others | P1 | - Each platform is posted to independently (try/except per platform)<br>- If a platform fails, the error is logged but posting continues to other platforms<br>- A draft is marked "posted" if at least one platform succeeds (with `platforms_posted` listing which ones)<br>- A draft is marked "failed" only if ALL platforms fail |
| US-012 | As Sammy, I want Instagram posting handled through Meta Business Suite on the web so that I can post from a desktop browser | P1 | - Instagram posting function navigates to Meta Business Suite (business.facebook.com) or the Instagram web compose flow<br>- OR: uses mobile viewport emulation in Playwright to access Instagram's mobile web compose<br>- This is the hardest platform — if a working approach cannot be found, skip Instagram for v1 and log a warning |

#### Epic 4: Scheduling & Automation

| ID | Story | Priority | Acceptance Criteria |
|----|-------|----------|---------------------|
| US-013 | As Sammy, I want content generation to run 3 times daily so that 6 drafts are always available | P0 | - A Windows Task Scheduler task runs the generate script 3 times per day (e.g., 8 AM, 1 PM, 6 PM)<br>- Each run generates 2 drafts (total 6/day)<br>- The script completes without manual interaction<br>- Setup instructions or a PowerShell script to register the task are provided |
| US-014 | As Sammy, I want the poster to run automatically every 1-3 hours so that drafts are posted without my intervention | P0 | - A Windows Task Scheduler task runs the poster script on a repeating interval (default: every 2 hours)<br>- The poster only runs when the desktop is on (Task Scheduler's built-in behavior)<br>- If no pending drafts exist, the poster exits cleanly with a log message |
| US-015 | As Sammy, I want all activity logged to a file so that I can debug failures | P0 | - All scripts log to `logs/poster.log` and `logs/generator.log`<br>- Log format: `timestamp - level - message`<br>- Logs include: draft generated, draft picked up, posting started per platform, success/failure per platform, errors with tracebacks |

---

## 3. Functional Requirements

### 3.1 Content Generation

**FR-001: Claude Code Invocation & Persona**
- The PowerShell script (`scripts/generate.ps1`) must call Claude Code using:
  ```
  claude --dangerously-skip-permissions -p "<prompt>"
  ```
- **Critical: Claude Code's output style must be changed.** The prompt must explicitly instruct Claude Code to:
  - Act as a social media marketer and content manager
  - NOT behave like a coder, developer, or technical assistant
  - NOT produce code blocks, technical explanations, bullet-point lists, or structured analysis
  - Write ONLY in the voice of an engaging social media content creator
  - Output ONLY the JSON draft file — no commentary, no explanations, no "here's what I created" preamble
- The prompt must include the full contents of `config/content-templates.md`
- The prompt must instruct Claude Code to create a JSON file in the `drafts/pending/` folder
- The prompt must reference previously generated drafts (by listing existing filenames in `pending/` and `posted/`) so Claude Code can avoid repeating topics

**FR-002: Draft JSON Schema**
- Every draft file must conform to this schema:
  ```json
  {
    "id": "string (timestamp-based, e.g., 20260307-143022)",
    "created_at": "ISO 8601 datetime string",
    "status": "pending | posted | failed",
    "topic": "string (brief label, e.g., 'AI in fintech')",
    "content": {
      "x": "string (max 280 characters, punchy, may include hashtags)",
      "linkedin": "string (professional tone, 500-1500 characters, may use line breaks)",
      "facebook": "string (conversational tone, 200-800 characters)",
      "instagram": "string (caption with emojis and hashtags at the end, 300-1200 characters)",
      "bluesky": "string (max 300 characters)"
    },
    "posted_at": "ISO 8601 datetime string (added after posting)",
    "platforms_posted": ["x", "linkedin", ...],
    "failed_at": "ISO 8601 datetime string (added on failure)",
    "error": "string (error message on failure)"
  }
  ```
- File naming: `draft-{id}.json` (e.g., `draft-20260307-143022.json`)

**FR-003: Content Templates Config**
- File location: `config/content-templates.md`
- Must include sections for: brand voice, content pillars/topics, hook templates, per-platform rules, and any specific constraints (e.g., "never sound like generic AI", "use real examples")
- This file is user-editable — Sammy updates it whenever she wants to change the content style

**FR-004: Batch Generation**
- The generate script must accept an optional `--count N` parameter
- Default: 2 drafts per invocation
- The script is scheduled 3 times per day, producing 6 drafts total
- When N > 1, Claude Code is called N times (each call generates one draft to avoid context confusion)
- Each call includes the filenames of existing drafts in `pending/` and `posted/` so Claude Code avoids repeating topics

### 3.2 Draft Management

**FR-005: Draft Storage**
- Drafts are stored as individual JSON files in a folder-based queue:
  - `drafts/pending/` — awaiting posting
  - `drafts/posted/` — successfully posted
  - `drafts/failed/` — failed to post to any platform

**FR-006: Draft Lifecycle**
- New draft → saved to `pending/`
- Poster picks oldest file in `pending/` (sorted by file modification time)
- If posted to ≥1 platform → moved to `posted/` with `posted_at` and `platforms_posted` fields added
- If failed on ALL platforms → moved to `failed/` with `failed_at` and `error` fields added

**FR-007: Draft Manager Module**
- A Python module (`scripts/utils/draft_manager.py`) must provide:
  - `get_next_draft() -> dict | None` — returns the oldest pending draft or None
  - `mark_posted(draft, platforms_posted: list[str])` — moves draft to posted folder
  - `mark_failed(draft, error: str)` — moves draft to failed folder

### 3.3 Browser Automation Posting

**FR-008: Persistent Browser Profiles**
- Each platform has its own Playwright persistent context directory:
  - `profiles/x-profile/`
  - `profiles/linkedin-profile/`
  - `profiles/facebook-profile/`
  - `profiles/instagram-profile/`
- Profiles are created once via the `login_setup.py` helper (manual login)
- The poster script uses `pw.chromium.launch_persistent_context(user_data_dir=...)` to reuse sessions

**FR-009: Login Setup Helper**
- File: `scripts/login_setup.py`
- Usage: `python scripts/login_setup.py <platform>` where platform is `x`, `linkedin`, `facebook`, or `instagram`
- Behavior: Opens a headed Chromium browser with the persistent profile directory, navigates to the platform's login page, and waits for the user to log in manually and close the browser
- On close, the session state (cookies, localStorage, etc.) is persisted in the profile folder

**FR-010: Platform Posting Functions**
- Each platform has a dedicated async function in the poster script
- Every function must:
  1. Open a new page in the persistent context
  2. Navigate to the platform
  3. Wait for the page to load (using `wait_until="networkidle"` or similar)
  4. Perform human-like actions (scroll, mouse movement) before interacting
  5. Find the compose area using stable selectors (aria-labels, roles, data-testid)
  6. Type content character-by-character with human-like timing
  7. Click the post/submit button
  8. Wait for confirmation (page change, toast notification, or URL change)
  9. Close the page
  10. Return `True` on success, `False` on failure

**Platform-specific navigation:**

| Platform | Compose URL / Flow | Compose Selector Strategy | Post Button Strategy |
|----------|-------------------|--------------------------|---------------------|
| X | `https://x.com/compose/post` or click compose from home | `[role="textbox"]` in the compose dialog | `[data-testid="tweetButton"]` or button with aria-label containing "Post" |
| LinkedIn | `https://www.linkedin.com/feed/` → click "Start a post" | Button containing "Start a post" text → then `[role="textbox"]` in the modal | Button with text "Post" in the share dialog |
| Facebook | `https://www.facebook.com/` → click "What's on your mind?" | The composer textbox, typically `[role="textbox"]` with aria-label about "What's on your mind" | Button with aria-label "Post" |
| Instagram | TBD — try Meta Business Suite or mobile viewport emulation | TBD | TBD |

**NOTE:** These selectors are starting points. They will need to be verified and may need adjustment when first tested. The poster script should be structured so each platform's selectors are defined in one clear place at the top of the platform function (or in a config), making them easy to update.

**FR-011: Human Behavior Emulation**
- A Python module (`scripts/utils/human_behavior.py`) must provide:
  - `human_delay(min_sec, max_sec)` — async sleep for a random duration in the range
  - `human_type(page, selector, text)` — types text character-by-character with random 30-120ms delays between keystrokes, with a 5% chance of a 300-800ms pause after any character
  - `human_scroll(page, direction, amount)` — scrolls a random 200-500px with a short pause after
  - `random_mouse_movement(page)` — moves mouse to a random viewport position in 5-15 steps
  - `browse_feed(page, platform)` — **NEW: the core browsing simulation function.** Spends 1-5 minutes (randomized) on the platform doing realistic browsing:
    - Scroll the feed slowly (multiple small scrolls with pauses)
    - Stop on 2-4 random posts (pause 3-10 seconds as if reading)
    - Click on 1-2 user profiles (navigate to profile, pause 5-15 seconds, scroll their page, then go back)
    - Occasionally hover over elements (like buttons, images)
    - Random mouse movements between actions
    - All timing is randomized within ranges to avoid patterns
- These functions are called throughout each platform's posting flow:
  1. `browse_feed()` runs BEFORE the post is made (pre-post browsing)
  2. Human-like typing and clicking during the actual post
  3. `browse_feed()` runs AFTER the post is made (post-post browsing)

**FR-011a: Browsing Behavior Configuration**
- The browsing duration range (default 1-5 minutes) must be configurable via `.env`
- The number of posts to stop on (default 2-4) must be configurable
- The number of profiles to click (default 1-2) must be configurable
- All these parameters have sensible defaults and don't require configuration to work

**FR-012: Browser Launch Configuration**
- Every persistent context launch must use these settings:
  - `headless=False` (headed mode to avoid headless detection)
  - `viewport={"width": 1280, "height": 800}`
  - `args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]`
- Future enhancement: add `playwright-stealth` library integration

**FR-013: Platform Posting Order & Spacing**
- The poster iterates through platforms sequentially (not in parallel)
- Platform order is randomized each run to avoid predictable patterns
- Between each platform, wait a random 30-90 seconds (after closing one browser context, before opening the next)
- Total time per platform (including pre-browse + post + post-browse) will be approximately 4-15 minutes
- Total run time for all 4 platforms: approximately 20-70 minutes

### 3.4 Scheduling

**FR-014: Windows Task Scheduler Setup**
- Provide a PowerShell script (`scripts/setup_scheduler.ps1`) that registers two tasks:
  1. **AutoPoster-Generate**: Runs `generate.ps1 --count 2` three times daily (default: 8 AM, 1 PM, 6 PM) to produce 6 drafts/day
  2. **AutoPoster-Post**: Runs `post.py` every 2 hours (configurable interval), starting at 9 AM
- Both tasks only execute when the computer is on (Windows Task Scheduler default)
- The setup script must be idempotent (safe to run multiple times)
- Generation times and posting interval must be configurable in the script

### 3.5 Logging

**FR-015: Logging Configuration**
- Generator logs to: `logs/generator.log`
- Poster logs to: `logs/poster.log`
- Log format: `%(asctime)s - %(levelname)s - %(message)s`
- Log level: INFO (DEBUG available via environment variable or flag)
- Logs must capture: script start/end, draft picked up, each platform attempt start/result, errors with full tracebacks

---

## 4. Non-Functional Requirements

### 4.1 Performance
- Content generation: No time constraint (Claude Code takes as long as it needs)
- Posting to all 4 platforms: Must complete within 90 minutes (including browsing behavior and delays between platforms). This is longer than a simple post-and-go because each platform now includes 1-5 minutes of pre-post browsing and 1-5 minutes of post-post browsing.
- Script startup: Must launch within 10 seconds

### 4.2 Security
- No passwords, tokens, or API keys are stored in any script or config file
- Authentication is handled entirely through persistent browser profiles (cookie-based sessions)
- The `.env` file exists in `config/` but is only for non-sensitive configuration (paths, timing settings)
- `profiles/` folder must be in `.gitignore` if the project is ever version-controlled

### 4.3 Reliability
- If a platform's page fails to load within 30 seconds, timeout and skip that platform
- If the compose area cannot be found within 15 seconds, skip that platform
- All failures are logged and do not crash the script
- The poster must always exit cleanly (no zombie browser processes)

### 4.4 Compatibility
- Operating System: Windows 10/11
- Python: 3.11+
- Node.js: Not required (Claude Code handles its own runtime)
- Browser: Chromium (installed via Playwright)
- Shell: PowerShell 5.1+ (Windows default)

---

## 5. Technical Architecture

### 5.1 Project Structure

```
C:\auto-poster\
├── config\
│   ├── content-templates.md    # Brand voice, content pillars, hooks, platform rules
│   ├── platforms.json          # Platform-specific settings (selectors, URLs, timeouts)
│   └── .env                    # Non-sensitive config (paths, timing, log levels)
├── drafts\
│   ├── pending\                # Drafts waiting to be posted
│   ├── posted\                 # Successfully posted drafts (with metadata)
│   └── failed\                 # Failed drafts (with error info)
├── profiles\
│   ├── x-profile\              # Persistent Playwright profile for X
│   ├── linkedin-profile\       # Persistent profile for LinkedIn
│   ├── facebook-profile\       # Persistent profile for Facebook
│   └── instagram-profile\      # Persistent profile for Instagram
├── scripts\
│   ├── generate.ps1            # PowerShell: calls Claude Code to generate drafts
│   ├── post.py                 # Python: Playwright-based poster
│   ├── login_setup.py          # Python: one-time manual login helper
│   ├── setup_scheduler.ps1     # PowerShell: registers Windows Task Scheduler tasks
│   └── utils\
│       ├── __init__.py
│       ├── human_behavior.py   # Random delays, typing, scrolling, mouse movement
│       └── draft_manager.py    # Read/write/move draft JSON files
├── logs\
│   ├── generator.log
│   └── poster.log
├── requirements.txt            # Python dependencies
├── .gitignore                  # Excludes profiles/, logs/, drafts/posted/, drafts/failed/
└── README.md                   # Setup instructions and usage guide
```

### 5.2 Dependencies

| Dependency | Purpose | Install |
|------------|---------|---------|
| Python 3.11+ | Runtime for poster and utilities | Pre-installed or python.org |
| Playwright | Browser automation | `pip install playwright` then `playwright install chromium` |
| playwright-stealth (future) | Anti-detection patches | `pip install playwright-stealth` |
| Claude Code CLI | Content generation | Already installed (Max plan) |

### 5.4 Browser Automation Framework Decision: Playwright

**Chosen: Playwright (Python)** over Selenium, Browser Use, and Stagehand.

**Why Playwright over Selenium:**
- Native async/await support — critical since the poster runs sequentially with long delays
- Built-in `launch_persistent_context()` for reusing login sessions (Selenium requires manual cookie import/export)
- Auto-wait for elements (reduces flakiness vs Selenium's explicit waits)
- Better stealth — Selenium's `navigator.webdriver` flag is more widely detected by platforms
- `--disable-blink-features=AutomationControlled` flag removes the biggest Chromium automation fingerprint
- Playwright is actively maintained by Microsoft with frequent releases

**Why Playwright over Browser Use / Stagehand:**
- Browser Use and Stagehand consume LLM API tokens on every action (costs money per post)
- Added latency — each action requires an LLM call to reason about the page
- Overkill for v1 — the posting flows are predictable (navigate → compose → type → post)
- Both are built ON TOP of Playwright, so migrating from plain Playwright to either is a straightforward upgrade
- Browser Use and Stagehand are the planned v2.0 upgrade when selector maintenance becomes painful

**Migration path to AI automation (v2.0):**
- Browser Use and Stagehand both use Playwright under the hood
- Upgrading means replacing selector-based `page.locator()` calls with natural language `act("click the post button")` calls
- The persistent profile, human behavior emulation, and draft management code stays unchanged

### 5.3 Data Flow

```
1. Task Scheduler triggers generate.ps1 (3x daily: 8 AM, 1 PM, 6 PM)
2. generate.ps1 reads config/content-templates.md
3. generate.ps1 lists existing draft filenames for topic deduplication
4. generate.ps1 calls: claude --dangerously-skip-permissions -p "<prompt>"
   (Claude Code operates as a social media marketer, NOT a coder)
5. Claude Code creates drafts/pending/draft-{timestamp}.json
6. Repeat step 3-5 for --count drafts (default 2 per run = 6/day)
7. (Time passes — poster runs every 2 hours)
8. Task Scheduler triggers post.py
9. post.py calls draft_manager.get_next_draft()
10. Randomize platform order for this run
11. For each platform:
    a. Launch persistent context from profiles/{platform}-profile/
    b. Navigate to platform home/feed
    c. browse_feed() — spend 1-5 min browsing (scroll, view posts, click profiles)
    d. Navigate to compose area
    e. Human-like typing of content with human_type()
    f. Click post button, wait for confirmation
    g. browse_feed() — spend 1-5 min post-post browsing
    h. Close browser context
    i. Wait 30-90 seconds before next platform
12. draft_manager.mark_posted() or mark_failed()
13. post.py exits
```

---

## 6. Configuration Files

### 6.1 content-templates.md (Initial Version)

This file must be created with placeholder content that Sammy will customize. Include:

```markdown
# Content Guidelines for Auto-Poster

## Brand Voice
- Authoritative but approachable
- Technically informed — can reference real tools, frameworks, and concepts
- Occasionally contrarian or thought-provoking
- Never sounds like generic AI output — be specific, opinionated, and concise
- Use first person ("I", "my") naturally

## Content Pillars
1. **Fintech & Banking Technology** — insights about digital banking, payment systems, financial infrastructure
2. **Frontend Development** — React, Next.js, TypeScript tips, opinions, and discoveries
3. **Trading & Financial Markets** — market analysis, trading psychology, technical analysis insights
4. **AI & Developer Tools** — new tools, workflows, productivity hacks, AI-assisted development
5. **Career & Leadership** — engineering leadership, team management, career growth

## Hook Templates
Use these as starting structures (vary them, don't repeat the same hook):
- "Most developers don't realize [surprising fact about topic]..."
- "I spent [time period] building [thing]. Here's what I learned:"
- "Unpopular opinion: [contrarian take]"
- "[Specific stat or observation]. Here's why it matters:"
- "The biggest mistake I see in [domain] is [mistake]. Here's why:"
- "If you're still [common outdated practice], try [better approach] instead."
- "3 things I wish I knew about [topic] before [experience]:"
- "[Tool/framework] changed how I think about [problem]. Thread:"

## Platform-Specific Rules

### X (formerly Twitter)
- Maximum 280 characters
- One core idea per post
- Punchy, direct, conversational
- 1-3 hashtags maximum, placed naturally (not dumped at the end)
- Use line breaks sparingly for emphasis

### LinkedIn
- Professional but not corporate-speak
- 500-1500 characters is the sweet spot
- Use line breaks generously for readability
- Start with a strong hook (first 2 lines are visible before "see more")
- End with a question or call to discussion
- 3-5 relevant hashtags at the end

### Facebook
- Conversational and community-oriented
- 200-800 characters
- Can be more personal/story-driven than LinkedIn
- Minimal hashtags (0-2)

### Instagram
- Caption style — emoji-friendly but not overdone
- 300-1200 characters
- Hashtags at the very end, separated by line breaks (5-10 hashtags)
- Storytelling or tip-based format works well

### BlueSky
- Maximum 300 characters
- Similar to X but slightly more room
- Casual, community-oriented tone
- No hashtags (BlueSky culture is anti-hashtag)

## Content Rules
- NEVER generate content that sounds like it was written by AI (avoid "In today's fast-paced world", "Let's dive in", "Here's the thing", "game-changer", "leverage", "unlock")
- Every post must contain at least ONE specific detail (a tool name, a number, a real scenario)
- Vary the content pillars — don't post about the same topic twice in a row
- Vary the tone — mix educational, opinionated, personal story, and quick tips
```

### 6.2 platforms.json

```json
{
  "x": {
    "name": "X (Twitter)",
    "compose_url": "https://x.com/compose/post",
    "home_url": "https://x.com/home",
    "timeout_seconds": 30,
    "enabled": true
  },
  "linkedin": {
    "name": "LinkedIn",
    "home_url": "https://www.linkedin.com/feed/",
    "timeout_seconds": 30,
    "enabled": true
  },
  "facebook": {
    "name": "Facebook",
    "home_url": "https://www.facebook.com/",
    "timeout_seconds": 30,
    "enabled": true
  },
  "instagram": {
    "name": "Instagram",
    "home_url": "https://www.instagram.com/",
    "timeout_seconds": 30,
    "enabled": false,
    "note": "Instagram web posting is unreliable. Enable after testing with Meta Business Suite approach."
  }
}
```

### 6.3 .env

```env
# Auto-Poster Configuration
AUTO_POSTER_ROOT=C:\auto-poster
LOG_LEVEL=INFO
GENERATE_COUNT=2

# Posting behavior
POST_INTERVAL_MIN_SEC=30
POST_INTERVAL_MAX_SEC=90
PAGE_LOAD_TIMEOUT_SEC=30
COMPOSE_FIND_TIMEOUT_SEC=15

# Browsing behavior (human emulation)
BROWSE_MIN_DURATION_SEC=60
BROWSE_MAX_DURATION_SEC=300
BROWSE_POSTS_TO_VIEW_MIN=2
BROWSE_POSTS_TO_VIEW_MAX=4
BROWSE_PROFILES_TO_CLICK_MIN=1
BROWSE_PROFILES_TO_CLICK_MAX=2
```

---

## 7. Setup & Installation

### 7.1 First-Time Setup (Manual Steps)

1. Create the folder structure at `C:\auto-poster\`
2. Install Python 3.11+ (if not already installed)
3. Run `pip install playwright` and `playwright install chromium`
4. Ensure Claude Code CLI is installed and working (`claude --version`)
5. Run `python scripts/login_setup.py x` — log into X manually, close browser
6. Run `python scripts/login_setup.py linkedin` — log into LinkedIn manually, close browser
7. Run `python scripts/login_setup.py facebook` — log into Facebook manually, close browser
8. Run `python scripts/login_setup.py instagram` — log into Instagram manually, close browser
9. Edit `config/content-templates.md` to match desired brand voice
10. Test content generation: run `generate.ps1` manually, verify draft JSON is valid
11. Test posting: run `post.py` manually, verify posts appear on each platform
12. Run `setup_scheduler.ps1` to register scheduled tasks

### 7.2 Re-Login (When Sessions Expire)

- Symptoms: poster logs show authentication errors or redirects to login page
- Fix: run `python scripts/login_setup.py <platform>` for the affected platform
- Expected frequency: every few weeks for LinkedIn (most aggressive), rarely for X and Facebook

---

## 8. Release Planning

### 8.1 Milestones

| Phase | Deliverables | Description |
|-------|------------|-------------|
| **v1.0 — MVP** | Generate + Post to X + LinkedIn + Facebook | Core system working with 3 platforms, human-like behavior, scheduled automation |
| **v1.1 — Instagram** | Add Instagram posting | Either via Meta Business Suite web or mobile viewport emulation |
| **v1.2 — Stealth** | Add playwright-stealth integration | Better anti-detection for all platforms |
| **v2.0 — AI Automation** | Swap Playwright selectors for Browser Use or Stagehand | AI-powered self-healing automation that adapts to UI changes |
| **v2.1 — Media** | Add image support | Generate images (via AI image gen or stock), attach to posts |

---

## 9. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Platform detects automation and locks account | Medium | High | Human-like behavior emulation, persistent profiles, headed browser mode, residential IP (local desktop), random delays, randomized platform order |
| Platform UI changes break selectors | Medium | Medium | Use stable selectors (aria, roles, data-testid), modular per-platform code for easy updates, future upgrade to AI-powered automation |
| LinkedIn session expires frequently | High | Low | Re-run login_setup.py; log clear error messages when auth fails |
| Instagram web posting doesn't work reliably | High | Low | Instagram is disabled by default in v1; attempt Meta Business Suite approach in v1.1 |
| Claude Code generates low-quality content | Low | Medium | Detailed content templates with specific rules; manual review of first 10-20 drafts to tune templates |
| Desktop is off during scheduled posting window | Medium | Low | Acceptable — posts go out when desktop is next on; drafts queue up in pending folder |
| Claude Code CLI changes its interface | Low | Medium | Pin to known working version; the `--dangerously-skip-permissions -p` flags are stable |

---

## 10. Open Questions

- [ ] What is the best approach for Instagram web posting — Meta Business Suite, mobile viewport emulation, or another method?
- [ ] Should `platforms.json` selectors be moved into the config so they can be updated without touching Python code?
- [ ] Should the system track which content pillar was used for each draft to ensure rotation?
- [ ] For the fake accounts, should each account have a distinct persona/brand voice, or should they all post similar content?

---

## Appendix

### A. Glossary

| Term | Definition |
|------|------------|
| Claude Code | Anthropic's CLI-based AI coding assistant, used here for content generation in non-interactive mode |
| Persistent context | A Playwright browser profile that saves cookies, localStorage, and session data between runs |
| Draft | A JSON file containing platform-specific social media content awaiting posting |
| Human behavior emulation | Techniques to make automated browser actions indistinguishable from a real human (random delays, typing speed variation, scrolling, mouse movement) |
| Selector | A CSS selector, aria label, role, or data attribute used to find elements on a web page |
| Playwright | Microsoft's browser automation framework for Python, Node.js, and other languages |
| Browser Use | Open-source AI browser automation framework that uses LLMs to understand pages semantically |
| Stagehand | AI browser automation framework by Browserbase that combines natural language with Playwright code |

### B. References
- Playwright docs: https://playwright.dev/python/
- Browser Use GitHub: https://github.com/browser-use/browser-use
- Stagehand GitHub: https://github.com/browserbase/stagehand
- Stagehand Python: https://github.com/browserbase/stagehand-python
