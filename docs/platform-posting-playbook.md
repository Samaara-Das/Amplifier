# Amplifier -- Platform Posting Playbook

**File:** `scripts/post.py`

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

### Selectors
```python
X_COMPOSE_URL = "https://x.com/compose/post"
X_TEXTBOX = '[role="textbox"]'
X_POST_BUTTON = '[data-testid="tweetButton"]'
X_FILE_INPUT = 'input[data-testid="fileInput"]'  # or input[type="file"][accept*="image"]
X_ATTACHMENTS = '[data-testid="attachments"]'
X_PROFILE_LINK = 'a[data-testid="AppTabBar_Profile_Link"]'
X_TWEET_ARTICLE = 'article[data-testid="tweet"]'
```

### Posting Flow
1. Browse home
2. Navigate to compose URL
3. Wait for textbox
4. Upload image (if available) via hidden file input
5. Type content character-by-character
6. Click post button via **`dispatch_event("click")`** (NOT `.click()` -- overlay div intercepts)
7. Navigate to profile, find latest tweet URL

### Known Issues
- **Overlay div intercepts clicks** -- must use `dispatch_event("click")` on post button
- **Image upload**: file input may be hidden -- tries 3 selector variants
- **URL capture**: tweets may not load immediately -- retry loop (3 attempts) with scrolling
- **Account lockout**: X detects Playwright automation and locks accounts. CRITICAL blocker.

---

## LinkedIn

### Selectors
```python
LI_COMPOSE_TRIGGER = '[role="button"]:has-text("Start a post")'
LI_TEXTBOX = '[role="textbox"]'
LI_POST_BUTTON = page.get_by_role("button", name="Post", exact=True)
LI_ACTIVITY_URL = "{profile_url}/recent-activity/all/"
```

### Posting Flow
1. Browse home
2. Click compose trigger
3. Upload image BEFORE typing:
   - Strategy 1: hidden `input[type="file"]` -> `set_input_files()`
   - Strategy 2: click media button -> file chooser
     - `button[aria-label="Add a photo"]`
     - `button[aria-label="Add media"]`
     - `button:has(li-icon[type="image"])`
4. Type content in textbox
5. Click Post button
6. Navigate to activity page, find latest post URL

### Known Issues
- **Shadow DOM** -- use `page.locator()` (pierces shadow DOM), NOT `page.wait_for_selector()` (does not)
- **Image upload via file chooser** -- use `page.expect_file_chooser()` context manager
- **Activity page**: URL must strip query params before appending `/recent-activity/all/`

---

## Facebook

### Selectors
```python
FB_COMPOSER_TRIGGER = '[aria-label="What\'s on your mind?"]'
FB_TEXTBOX = '[role="textbox"]'
FB_POST_BUTTON = '[aria-label="Post"]'
FB_PHOTO_BUTTON = '[aria-label="Photo/video"]'  # or "Photo/Video"
```

### Posting Flow
1. Browse home
2. Click composer trigger
3. Upload image (if available):
   - Click photo/video button (tries 4 selector variants)
   - Find file input (`input[type="file"][accept*="image"]`)
   - `set_input_files()`
4. Type content using `.last` textbox (Facebook renders multiple textboxes)
5. Click Post button
6. Navigate to own profile, find latest post URL

### Known Issues
- **Multiple textboxes** -- always use `page.locator(FB_TEXTBOX).last`
- **DOM heavily obfuscated** -- class names change constantly, use aria-labels
- **Post scraping** -- `role="article"` no longer works. Body text parsing via "Comment as" markers.

---

## Reddit

### Selectors
```python
REDDIT_SUBMIT_URL = "https://www.reddit.com/r/{subreddit}/submit"
REDDIT_TITLE = 'textarea[name="title"]'
REDDIT_BODY = '[role="textbox"][name="body"]'  # or div[contenteditable="true"][name="body"]
REDDIT_POST_BUTTON = 'button:has-text("Post")'
```

### Posting Flow
1. Browse home
2. Navigate to random subreddit submit page (from `platforms.json` list)
3. Fill title field
4. Fill body field
5. Click Post button
6. Extract URL from redirect (contains `/comments/`)
7. Navigate home, browse feed

### Content Structure
- Reddit content can be string (first 120 chars = title, rest = body) or dict (`{title, body}`)

### Known Issues
- **Headless blocked** -- Reddit blocks headless browsers entirely ("network security" error). Scraper runs headed, but posting still uses headless (may need headed mode too).
- **Subreddit selection** -- random from configured list. May not match campaign topic well.

---

## TikTok

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
