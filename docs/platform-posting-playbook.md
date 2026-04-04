# Amplifier -- Platform Posting Playbook

**Primary:** `scripts/engine/script_executor.py` (JSON script engine)
**Fallback:** `scripts/post.py` (legacy hardcoded functions)

## JSON Script Engine (Primary)

Posting is now driven by declarative JSON scripts in `config/scripts/` via `scripts/engine/script_executor.py`. The engine tries the script-driven path first (`post_via_script()`); if no script exists for a platform (TikTok, Instagram), it falls back to the legacy hardcoded functions in `post.py`.

**Scripts:** `config/scripts/x_post.json`, `linkedin_post.json`, `facebook_post.json`, `reddit_post.json`

**Engine modules** (`scripts/engine/`):
| Module | Purpose |
|--------|---------|
| `script_parser.py` | Data models for parsing JSON script definitions |
| `selector_chain.py` | Fallback selector chains (3+ selectors per element) |
| `human_timing.py` | Per-step human-like delays |
| `error_recovery.py` | Retry with exponential backoff, popup dismissal |
| `script_executor.py` | Executes 13 action types (click, type, upload, wait, etc.) |

### Fallback Selector Chains

Each element in a script defines multiple selectors tried in order. If the first selector fails (stale DOM, layout change), the engine tries the next:

```json
{
  "selectors": [
    "[data-testid='tweetButton']",
    "button[aria-label='Post']",
    "button:has-text('Post')"
  ]
}
```

The chain stops at the first selector that matches. This makes posting resilient to minor UI changes without code updates.

### Error Recovery

When a step fails, the engine classifies the error and decides the retry strategy:

| Error Code | Meaning | Retry? |
|------------|---------|--------|
| `SELECTOR_FAILED` | No selector in the chain matched | Yes -- exponential backoff |
| `TIMEOUT` | Page load or element wait timed out | Yes -- exponential backoff |
| `AUTH_EXPIRED` | Login session has expired | No -- user must re-login |
| `RATE_LIMITED` | Platform throttling detected | Yes -- longer backoff |
| `UNKNOWN` | Unclassified failure | Yes -- exponential backoff |

Backoff formula: `30min * 2^retry_count`. The `post_schedule` table tracks `error_code`, `execution_log` (JSON array of step results), `retry_count`, and `max_retries` (default 3).

The engine also dismisses common popups (cookie banners, notification prompts) automatically before they block the posting flow.

---

## Browser Setup

All platforms use Playwright with persistent browser profiles:

```python
kwargs = dict(
    user_data_dir="profiles/{platform}-profile",
    headless=HEADLESS,  # from env, default false
    viewport={"width": 1280, "height": 800},
    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
)
```

Optional proxy support from `platforms.json`: `kwargs["proxy"] = {"server": proxy_url}`

## Human Behavior Emulation

| Behavior | Implementation |
|----------|---------------|
| Typing speed | 30-80ms per character (char-by-char, not paste) |
| Thinking pauses | 5% chance of 300-800ms pause per character |
| Between-action delay | 500-2000ms random |
| Feed browsing | 1-3 seconds wait on home page |
| Pre/post browsing | Browse feed before and after posting |

---

## X (Twitter)

> **Note:** X posting is now primarily handled by `config/scripts/x_post.json` via the script engine. The selectors and flow below are the legacy fallback, retained as reference.

### Selectors
```python
X_COMPOSE_URL = "https://x.com/compose/post"
X_TEXTBOX = '[role="textbox"]'
X_POST_BUTTON = '[data-testid="tweetButton"]'
```

### Posting Flow
1. Browse home
2. Navigate to compose URL
3. Wait for textbox
4. Upload image (if available) via `input[data-testid="fileInput"]` hidden file input, then wait for `[data-testid="attachments"]` preview
5. Type content character-by-character via `human_type()`
6. Submit post via **`Ctrl+Enter`** keyboard shortcut (overlay div intercepts pointer events on the post button)
7. Navigate to profile (with cache-busting query param), find latest tweet URL from `article[data-testid="tweet"] a[href*="/status/"]` (retry loop, 5 attempts)

### Known Issues
- **Overlay div intercepts clicks** -- must use `Ctrl+Enter` keyboard shortcut to submit
- **Image upload**: uses `input[data-testid="fileInput"]` directly with `set_input_files()`
- **URL capture**: tweets may not load immediately -- retry loop (5 attempts) with waits
- **Account lockout**: X detects Playwright automation and locks accounts. CRITICAL blocker.

---

## LinkedIn

> **Note:** LinkedIn posting is now primarily handled by `config/scripts/linkedin_post.json` via the script engine. The selectors and flow below are the legacy fallback, retained as reference.

### Selectors
```python
LI_COMPOSE_TRIGGER = '[role="button"]:has-text("Start a post")'
LI_TEXTBOX = '[role="textbox"]'
LI_POST_BUTTON = page.get_by_role("button", name="Post", exact=True)
```

### Posting Flow
1. Browse home
2. Click compose trigger (retry up to 3 times if modal doesn't open)
3. Paste image BEFORE typing (if available):
   - Read image file, base64-encode it
   - Focus textbox, then dispatch a **`ClipboardEvent('paste')`** via `locator.evaluate()` (creates a `DataTransfer` with the image `File` object)
   - This approach pierces shadow DOM where `set_input_files()` on hidden file inputs fails
4. Type text via **`page.keyboard.type(text, delay=50)`** (more reliable for shadow DOM contenteditable than `human_type`)
5. Click Post button
6. Capture URL from **"View post" link** in success dialog (30s timeout), dismiss with "Not now"
7. Fallback URL capture: navigate to `/in/me/recent-activity/all/`, find `a[href*="/feed/update/"]`

### Known Issues
- **Shadow DOM** -- use `page.locator()` (pierces shadow DOM), NOT `page.wait_for_selector()` (does not)
- **Image upload via ClipboardEvent paste** -- `locator.evaluate()` pierces shadow DOM for the paste target
- **Text input** -- `keyboard.type()` is more reliable than char-by-char `human_type` for LinkedIn's contenteditable

---

## Facebook

> **Note:** Facebook posting is now primarily handled by `config/scripts/facebook_post.json` via the script engine. The selectors and flow below are the legacy fallback, retained as reference.

### Selectors
```python
FB_COMPOSER_TRIGGER = '[aria-label="What\'s on your mind?"], [role="button"]:has-text("What\'s on your mind")'
FB_TEXTBOX = '[role="textbox"]'
FB_POST_BUTTON = '[aria-label="Post"]'
```

### Posting Flow
1. Browse home
2. Click composer trigger
3. Paste image (if available) via **`ClipboardEvent('paste')`**:
   - Read image file, base64-encode it
   - Focus first textbox, then dispatch ClipboardEvent via `locator.evaluate()` (same approach as LinkedIn)
4. Type text via **`page.keyboard.type(text, delay=50)`** on first textbox
5. Click Post button
6. Capture URL: navigate to `https://www.facebook.com/me` and use the **profile URL as fallback** (Facebook's React UI doesn't expose post permalinks as `<a>` links)

### Known Issues
- **DOM heavily obfuscated** -- class names change constantly, use aria-labels
- **Image upload via ClipboardEvent paste** -- replaces the old photo/video button + file input approach
- **URL capture** -- profile URL is used as reliable fallback since Facebook no longer exposes direct post links easily

---

## Reddit

> **Note:** Reddit posting is now primarily handled by `config/scripts/reddit_post.json` via the script engine. The selectors and flow below are the legacy fallback, retained as reference.

### Selectors
```python
REDDIT_SUBMIT_URL = "https://www.reddit.com/user/{username}/submit"
REDDIT_TITLE = 'textarea[name="title"], textarea[placeholder*="Title"]'
REDDIT_POST_BUTTON = 'button:has-text("Post")'  # uses .last to avoid multiple matches
```

### Posting Flow
1. Navigate to `/user/me/` to discover username from redirect URL
2. Navigate to **user profile submit page** (`/user/{username}/submit`) -- NOT a subreddit
3. For image posts: switch to **"Images & Video" tab**, click **"Upload files"** button, use `page.expect_file_chooser()` to upload via file chooser, wait for upload to complete
4. Fill title field via `locator.fill()`
5. Fill body field (if provided) via **JS focus on Lexical editor** in shadow DOM:
   - `page.evaluate()` traverses shadow roots to find `div[contenteditable="true"][data-lexical-editor="true"]`
   - Calls `.focus()` on it, then types via `page.keyboard.type(body)`
6. Click Post button (`.last`, wait for enabled state up to 15s for image upload)
7. Capture URL from redirect: wait for `**/submitted/**created=**` URL pattern, extract post ID from **`?created=t3_XXXXX`** query param, construct URL as `/user/{username}/comments/{post_id}/`
8. Fallback: poll URL for `/comments/` or `created=` query params (8 attempts)

### Content Structure
- Reddit content can be string (first 120 chars = title, rest = body) or dict (`{title, body}`) or JSON string

### Known Issues
- **Posts to user profile** -- all posts go to `/user/{username}/submit`, not to subreddits
- **Lexical editor in shadow DOM** -- body field requires JS traversal of shadow roots to focus
- **Image upload timing** -- Post button may be disabled while image is still uploading; code polls `is_enabled()` up to 15 times

---

## TikTok

> **Note:** No JSON script exists for TikTok. This legacy hardcoded function is the only posting path. TikTok is currently disabled in `platforms.json`.

### Selectors
```python
UPLOAD_URL = "https://www.tiktok.com/creator#/upload?scene=creator_center"
CAPTION_FIELD = 'div.public-DraftEditor-content'  # or div[role="combobox"][contenteditable]
POST_BUTTON = '[data-e2e="post_video_button"]'  # or button:has-text("Post")
```

### Posting Flow
1. Browse home (with proxy if configured -- blocked in India)
2. Navigate to upload URL
3. Upload video via hidden file input
4. Dismiss dialogs (Cancel/Got it buttons)
5. **Clear pre-filled caption** -- Ctrl+A, Backspace (Draft.js pre-fills filename)
6. Type caption
7. Scroll post button into view, click
8. Browse home

### Known Issues
- **Blocked in India** -- requires VPN/proxy (configured in `platforms.json`)
- **Draft.js editor** -- pre-fills with filename, must clear before typing
- **Currently disabled** -- `"enabled": false` in `platforms.json`

---

## Instagram

> **Note:** No JSON script exists for Instagram. This legacy hardcoded function is the only posting path. Instagram is currently disabled in `platforms.json`.

### Selectors
```python
CREATE_BUTTON = '[aria-label="New post"]'  # or '[aria-label="Create"]'
POST_SUBMENU = 'svg[aria-label="Post"]'
FILE_INPUT = 'input[type="file"]'
SELECT_BUTTON = 'button:has-text("Select from computer")'
CAPTION_FIELD = 'textarea[aria-label="Write a caption..."]'  # or div[aria-label], textarea, [role="textbox"]
SHARE_BUTTON = dialog.get_by_role("button", name="Share", exact=True)
```

### Posting Flow (multi-step dialog)
1. Browse home twice (clean sidebar)
2. Click Create button (SVG icon)
3. Click Post from submenu
4. Wait for dialog
5. Upload image:
   - Try file input directly
   - Or click "Select from computer" -> file chooser
6. Click "Next" (crop step)
7. Click "Next" (filter step)
8. Fill caption (tries 7 selector variants)
9. Click Share (**force=True** -- overlay intercepts)
10. Wait for "Sharing" text, then dialog close (120s timeout)
11. Browse home

### Known Issues
- **All buttons need `force=True`** -- overlay intercepts standard clicks
- **Multi-step dialog** -- Create > Post submenu > Upload > Next > Next > Caption > Share
- **Caption selectors** -- Instagram changes these frequently, tries 7 variants
- **Currently disabled** -- `"enabled": false` in `platforms.json`

---

## Slot Scheduling (IST -> EST mapping)

| Slot | IST | EST | Primary Platforms |
|------|-----|-----|-------------------|
| 1 | 18:30 | 8:00 AM | X (daily), LinkedIn (Tue-Fri) |
| 2 | 20:30 | 10:00 AM | Facebook (daily) |
| 3 | 23:30 | 1:00 PM | X (daily), Reddit (Tue/Thu/Sat) |
| 4 | 01:30 | 3:00 PM | X (daily) |
| 5 | 04:30 | 6:00 PM | TikTok (daily) |
| 6 | 06:30 | 8:00 PM | Instagram (daily) |

## Timing Constants

| Env Var | Default | Purpose |
|---------|---------|---------|
| `POST_INTERVAL_MIN_SEC` | 30 | Min seconds between posts |
| `POST_INTERVAL_MAX_SEC` | 90 | Max seconds between posts |
| `PAGE_LOAD_TIMEOUT_SEC` | 30 | Page load timeout |
| `COMPOSE_FIND_TIMEOUT_SEC` | 15 | Compose window timeout |
| `HEADLESS` | false | Browser visibility |
| `RETRY_DELAY_SEC` | 300 | Retry delay on failure (5 min) |

## MVP Platform Status

| Platform | Enabled | Status |
|----------|---------|--------|
| X | Yes | Working, but account lockout risk |
| LinkedIn | Yes | Working |
| Facebook | Yes | Working |
| Reddit | Yes | Working (headed mode for scraping) |
| TikTok | No | Blocked in India, needs VPN |
| Instagram | No | Code preserved, disabled |
