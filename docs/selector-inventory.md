# Platform Selector Inventory

Every CSS selector, aria-label, data-testid, and DOM query pattern used across posting, metric scraping, profile scraping, and session health. Update this when platform UIs change.

**Last verified:** 2026-04-07

---

## 1. Posting Selectors (JSON Scripts)

### X (Twitter) — `config/scripts/x_post.json`

| Step | Purpose | Selectors (in fallback order) |
|---|---|---|
| browse_feed | Wait for feed | `[data-testid='primaryColumn']` |
| open_compose | Navigate to compose | URL: `https://x.com/compose/post` |
| wait_textbox | Wait for compose area | `[role='textbox']` |
| upload_image | File input | `input[data-testid='fileInput']` |
| wait_image | Verify attachment | `[data-testid='attachments']` |
| focus_textbox | Focus for typing | 1. `[role='textbox']` 2. `[data-testid='tweetTextarea_0']` |
| type_text | Text input | 1. `[role='textbox']` 2. `[data-testid='tweetTextarea_0']` |
| submit | Post tweet | **Keyboard: `Ctrl+Enter`** (overlay div blocks click on post button) |
| extract_username | Get profile link | `a[data-testid="AppTabBar_Profile_Link"]` |
| extract_post_url | Find tweet URL | 1. `article[data-testid='tweet'] a[href*='/status/']` 2. `a[href*='/status/']` |

**Known fragile:** Image attachment selector. X periodically changes `fileInput` testid.

### LinkedIn — `config/scripts/linkedin_post.json`

| Step | Purpose | Selectors (in fallback order) |
|---|---|---|
| browse_feed | Wait for feed | `main` |
| open_compose | Start a post button | 1. `[role='button']:has-text('Start a post')` 2. `button.share-box-feed-entry__trigger` 3. `.share-box-feed-entry__trigger` 4. `[data-control-name='identity_welcome_card']` |
| verify_compose | Textbox appeared | `[role='textbox']` |
| paste_image | Image via ClipboardEvent | Target: `[role='textbox']` — dispatches `ClipboardEvent('paste')` with image DataTransfer |
| type_text | Text input | 1. `[role='textbox']` 2. `.ql-editor` |
| click_post | Post button | 1. `button.share-actions__primary-action` 2. `.share-box_actions button:has-text('Post')` 3. `footer button:has-text('Post')` 4. `[role='dialog'] button:has-text('Post')` |
| extract_url_dialog | Success dialog | `a:has-text('View post')` (30s timeout) |
| dismiss_dialog | Dismiss success | `button[aria-label='Dismiss']` |
| extract_url_activity | Fallback URL | Navigate to `/in/me/recent-activity/all/` then: 1. `a[href*='/feed/update/']` 2. `a[href*='urn:li:activity']` |

**Known fragile:** Compose trigger — LinkedIn changes button classes frequently. Shadow DOM requires `page.locator()`, NOT `page.wait_for_selector()`.

### Facebook — `config/scripts/facebook_post.json`

| Step | Purpose | Selectors (in fallback order) |
|---|---|---|
| browse_feed | Wait for feed | `[role='main']` |
| open_compose | Composer trigger | 1. `[aria-label="What's on your mind?"]` 2. `[aria-label*='on your mind']` |
| wait_compose | Textbox appeared | `[role='textbox']` |
| paste_image | Image via ClipboardEvent | Target: `[role='textbox']` — dispatches `ClipboardEvent('paste')` |
| type_text | Text input | 1. `[role='textbox']` 2. `[contenteditable='true']` |
| click_post | Post button | 1. `[aria-label='Post']` 2. `div[aria-label='Post']` |
| extract_url | URL capture | Navigate to `facebook.com/me` → JS extraction from activity log |

**Known fragile:** DOM heavily obfuscated — class names change constantly. Use aria-labels only.

### Reddit — `config/scripts/reddit_post.json`

| Step | Purpose | Selectors (in fallback order) |
|---|---|---|
| fill_title | Title field | 1. `textarea[name='title']` 2. `textarea[placeholder*='Title']` 3. `textarea[placeholder*='title']` |
| click_body_editor | Body editor | 1. `#post-composer_bodytext` 2. `textarea[placeholder='Body text (optional)']` |
| fill_body | Lexical editor | **JS injection:** Traverses shadow roots to find `div[contenteditable="true"][data-lexical-editor="true"]`, calls `.focus()`, then `page.keyboard.type(body)` |
| upload_image | File upload | Click "Upload files" button → `page.expect_file_chooser()` |
| click_post | Post button | 1. `button:has-text('Post')` (`.last` to avoid multiple matches) 2. `[role='button']:Post` |
| extract_url | URL capture | Wait for redirect to `**/submitted/**created=**` → extract post ID from `?created=t3_XXXXX` query param |

**Known fragile:** Lexical editor in shadow DOM — body field requires JS traversal. Post button may stay disabled 15s during image upload.

---

## 2. Metric Scraping Selectors

**File:** `scripts/utils/metric_scraper.py`

### X (Twitter) — `_scrape_x()`

| Metric | Selector/Strategy | Notes |
|---|---|---|
| All metrics | `[role="group"]` (first only — main post) → child `[aria-label]` elements | Parse aria-label text for "view", "like", "repost", "repl"/"comment" |
| Views/Impressions | aria-label containing "view" | Fallback: `[aria-label*="views"]` |
| Likes | aria-label containing "like" | Parsed from first role=group |
| Reposts | aria-label containing "repost" or "retweet" | Parsed from first role=group |
| Comments | aria-label containing "repl" or "comment" | Parsed from first role=group |
| Deletion check | Body text: "This post is unavailable", "Account suspended", "This post was deleted" | Also HTTP 404 |

**Important:** Only uses the **first** `[role="group"]` element to avoid picking up metrics from quoted/embedded posts.

### LinkedIn — `_scrape_linkedin()`

| Metric | Selector/Strategy | Notes |
|---|---|---|
| Reactions (likes) | Strategy 1: `[aria-label*=" and "][aria-label*=" other"]` ("Name and N others") | Primary |
| Reactions (likes) | Strategy 2: `.social-details-social-counts__reactions-count` | Fallback CSS class |
| Reactions (likes) | Strategy 3: `[aria-label*="more reaction"]` ("See N more reactions") | Fallback |
| Comments | `[aria-label*="comments on"]` | Fallback: regex `(\d+)\s*comments?` in body text |
| Reposts | `[aria-label*="reposts of"]` | Fallback: regex `(\d+)\s*reposts?` in body text |
| Impressions | Regex: `([\d,]+)\s*(?:impressions?|views?)` | Body text only |
| Deletion check | "This content isn't available", "This page doesn't exist" | Also login redirect detection |

### Facebook — `_scrape_facebook()`

| Metric | Selector/Strategy | Notes |
|---|---|---|
| Likes | `[aria-label*="reaction"]` | "Like: N people" pattern |
| Likes (fallback) | `[aria-label^="Like:"]` | Alt pattern |
| Comments | Body text parsing: engagement bar inline numbers | 2-3 consecutive lines, last group = target post |
| Shares | Body text parsing: engagement bar inline numbers | Part of same consecutive group |
| Views | Regex: `([\d,.]+[KkMm]?)\s*views?` | Video posts only |
| Deletion check | "This content isn't available", CAPTCHA, login page title | |

### Reddit — `_scrape_reddit()`

| Metric | Selector/Strategy | Notes |
|---|---|---|
| Upvotes (score) | `shreddit-post[score]` element attribute | Primary |
| Comments | `shreddit-post[comment-count]` element attribute | Primary |
| Upvotes (fallback) | `[data-testid="post-unit-score"]` | Backup selector |
| Comments (fallback) | `[data-testid="post-comment-count"]` | Backup selector |
| Views | Regex: `([\d,.]+[KkMm]?)\s*views?` | Body text parsing |
| Deletion check | `shreddit-post[removed="true"]`, "[removed]", "[deleted]" | Also 404 |

### Number Parsing (all platforms)

All scrapers handle abbreviated numbers via `_parse_number()`:

| Input | Output |
|---|---|
| `"1,234"` | 1234 |
| `"1.2K"` or `"1.2k"` | 1200 |
| `"12K"` | 12000 |
| `"3.4M"` | 3400000 |
| `""`, `null`, `"--"` | 0 |

---

## 3. Metric Collection API

**File:** `scripts/utils/metric_collector.py`

### X API v2 (when `X_BEARER_TOKEN` is set)

| Metric | API Field | Endpoint |
|---|---|---|
| Impressions | `public_metrics.impression_count` | `GET /tweets/{id}?tweet.fields=public_metrics` |
| Likes | `public_metrics.like_count` | Same |
| Reposts | `public_metrics.retweet_count` | Same |
| Comments | `public_metrics.reply_count` | Same |
| Deletion | HTTP 404 or empty `data` field | Same |

### Reddit API (PRAW, when `REDDIT_CLIENT_ID` is set)

| Metric | PRAW Property |
|---|---|
| Upvotes | `submission.score` |
| Comments | `submission.num_comments` |
| Views | **Not available via PRAW** — falls back to Playwright |

---

## 4. Profile Scraping Selectors

**File:** `scripts/utils/profile_scraper.py` (1,645 lines)

### X Profile

| Field | Selector | Notes |
|---|---|---|
| Display name | `[data-testid="UserName"]` | |
| Bio | `[data-testid="UserDescription"]` | |
| Profile pic | `img[src*="profile_images"]` | Multiple fallbacks |
| Followers | `a[href$="/verified_followers"]` | |
| Following | `a[href$="/following"]` | |
| Tweet articles | `article[data-testid="tweet"]` | Scrolls 8x, collects up to 30 |
| Tweet text | `[data-testid="tweetText"]` | |
| Engagement group | `[role="group"]` | Likes/reposts/replies from aria-labels |
| Retweet context | `span[data-testid="socialContext"]` | Used to skip retweets |

### LinkedIn Profile

| Field | Selector | Notes |
|---|---|---|
| Display name | `h1.inline` or `h1.text-heading-xlarge` | |
| Headline | `div.text-body-medium` | Used as bio |
| Connections | `a[href*="/mynetwork/"] span.t-bold` | Follower count |
| Profile pic | `img.pv-top-card-profile-picture__image--show` | |
| Post container | `div.feed-shared-update-v2` | |
| Post text | `div.feed-shared-update-v2__description` or `span.break-words` | |
| Reactions | `span.social-details-social-counts__reactions-count` | |
| Comments | `button[aria-label*="comment"]` | |

**Expansions required:** Must click "...more" on About section, "Show all" on Experience/Skills/Education.

### Facebook Profile

| Field | Selector | Notes |
|---|---|---|
| Display name | `h1` (visible only) | Skips hidden h1 elements |
| Profile pic | `svg[aria-label*="rofile"] image` or `g image` | |
| Friends count | `a[href*="/friends"]` | |
| Bio/Intro | `[data-pagelet="ProfileTilesFeed_0"]` or `div:has-text("Intro")` | |
| Post container | `[role="article"]` | |
| About sections | Body text regex | Location, relationship, education, work, links |

### Reddit Profile

| Field | Selector | Notes |
|---|---|---|
| Display name | `h1` or `h2` | |
| Karma | `[id="karma"]` or `[data-testid="karma"]` | |
| Followers | Regex: `(\d+)\s*followers?` | Body text parsing |
| Post container | `shreddit-post` or `article` | Web components |
| Post title | `a[slot="title"]` or `[data-testid="post-title"]` | |
| Post score | `[data-testid="post-unit-score"]` or `faceplate-number` | |
| Profile pic | `img[alt*="avatar"]` | |

**shreddit-post attributes:** `score`, `comment-count`, `post-title`, `permalink`, `created-timestamp`, `removed`

---

## 5. Session Health Selectors

**File:** `scripts/utils/session_health.py`

### Authenticated (Green) — Session is valid

| Platform | Selectors |
|---|---|
| **X** | `a[data-testid="SideNav_NewTweet_Button"]`, `a[data-testid="AppTabBar_Profile_Link"]`, `[data-testid="primaryColumn"]` |
| **LinkedIn** | `div.feed-identity-module`, `button.share-box-feed-entry__trigger`, `img.global-nav__me-photo`, `.feed-shared-update-v2` |
| **Facebook** | `[aria-label="Create a post"]`, `[aria-label="Your profile"]`, `[role="navigation"] [data-testid="Keychain"]`, `div[role="feed"]` |
| **Reddit** | `[data-testid="create-post"]`, `button[aria-label="Open chat"]`, `faceplate-tracker[noun="user_menu"]`, `#USER_DROPDOWN_ID` |

### Login/Expired (Red) — Session needs re-auth

| Platform | Selectors |
|---|---|
| **X** | `[data-testid="loginButton"]`, `input[name="text"][autocomplete="username"]`, `a[href="/login"]` |
| **LinkedIn** | `form.login__form`, `input#username`, `.sign-in-form__sign-in-cta` |
| **Facebook** | `input[name="email"]`, `button[name="login"]`, `#loginbutton` |
| **Reddit** | `input[name="username"]`, `a[href="https://www.reddit.com/login/"]`, `faceplate-tracker[noun="login"]` |

### Lockout/Suspended Detection

| Platform | Selectors |
|---|---|
| **X** | `h1:has-text("Your account got locked")`, `h1:has-text("Account suspended")`, `a[href*="appeal"]`, `:has-text("Caution: This account is temporarily restricted")` |
| **Facebook** | `:has-text("Your Account Has Been Disabled")`, `:has-text("account is restricted")` |
| **Reddit** | `:has-text("Your account has been suspended")`, `:has-text("This account has been suspended")` |
