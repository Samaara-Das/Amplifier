# Troubleshooting

Common problems, causes, and fixes for the Amplifier engine, user app, and server.

---

## Session and Authentication Issues

### Platform Session Expired

| | |
|---|---|
| **Problem** | Posting fails with "login page detected" or platform redirects to login. |
| **Cause** | The persistent browser profile cookie has expired. Platforms expire sessions after days/weeks of inactivity. |
| **Fix** | Re-authenticate via CLI or dashboard: |

```bash
# Check which sessions are expired
python scripts/utils/session_health.py

# Re-authenticate a specific platform (opens visible browser)
python scripts/utils/session_health.py --platform x --reauth
```

The session health checker looks for platform-specific auth selectors (e.g., X's `SideNav_NewTweet_Button`, LinkedIn's `feed-identity-module`) vs login indicators (e.g., X's `loginButton`, LinkedIn's `login__form`). Status values: green (logged in), yellow (uncertain), red (session expired).

### Server 401 Unauthorized

| | |
|---|---|
| **Problem** | Campaign polling, post syncing, or metric reporting returns 401. |
| **Cause** | JWT token expired (24-hour TTL by default) or `config/server_auth.json` is missing/corrupt. |
| **Fix** | Re-run onboarding to get a fresh token: |

```bash
python scripts/onboarding.py
```

The server client (`scripts/utils/server_client.py`) reads the token from `config/server_auth.json`. If the file doesn't exist, it throws `RuntimeError: Not logged in. Run onboarding first.` The server's JWT expiry is configured via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default: 1440 = 24 hours).

### Playwright Profile Corrupted

| | |
|---|---|
| **Problem** | Browser launch crashes with errors about locked databases or corrupt profile data. |
| **Cause** | A previous Playwright process didn't shut down cleanly, leaving lock files in the profile directory. |
| **Fix** | Kill any lingering Chromium processes, then delete the corrupted profile: |

```bash
# Kill lingering Chromium processes (Windows)
taskkill /F /IM chromium.exe 2>nul

# Delete and recreate the profile (loses session -- must re-login)
rm -rf profiles/x-profile
python scripts/login_setup.py x
```

Profile directories are at `profiles/<platform>-profile/`. Each platform has its own persistent Chromium profile.

---

## Posting Failures

### X: Post Button Disabled

| | |
|---|---|
| **Problem** | `post.py` logs "X: post button is DISABLED -- no content to post." |
| **Cause** | Image upload failed silently. The `data-testid="fileInput"` file input didn't attach the image, or the `attachments` preview never appeared within 15 seconds. |
| **Fix** | Verify the image file exists and is a valid PNG/JPG. Check `logs/x_before_post.png` screenshot. If the image is too large, resize it. For text-only posts, ensure `content.x` is not empty. |

### X: Overlay Div Blocks Clicks

| | |
|---|---|
| **Problem** | Standard `.click()` on the tweet button does nothing. |
| **Cause** | X has an overlay div that intercepts pointer events on the post button. |
| **Fix** | Already handled -- `post.py` uses `Ctrl+Enter` keyboard shortcut after focusing the textbox with `force=True`. If this still fails, check if X has changed their DOM structure. |

### LinkedIn: Compose Modal Doesn't Open

| | |
|---|---|
| **Problem** | Clicking "Start a post" doesn't open the compose modal. |
| **Cause** | Shadow DOM timing issue. The `LI_COMPOSE_TRIGGER` button was clicked before the page fully loaded, or the modal is behind a shadow root. |
| **Fix** | The code retries 3 times with 2-second delays between attempts. If it still fails, LinkedIn may have changed their DOM. Check the selector: `[role="button"]:has-text("Start a post")`. Use Playwright's `locator()` (which pierces shadow DOM), never `wait_for_selector()`. |

### LinkedIn: Image Paste Fails

| | |
|---|---|
| **Problem** | Image doesn't appear in the LinkedIn composer. |
| **Cause** | The `ClipboardEvent` paste method may not work if LinkedIn's React app intercepts or ignores synthetic clipboard events. |
| **Fix** | The paste injects a `ClipboardEvent` with a `DataTransfer` containing the image file. If it returns "pasted" but no image appears, LinkedIn may have changed their paste handling. The post will proceed as text-only if text is available. |

### Facebook: No Post URL Captured

| | |
|---|---|
| **Problem** | Post succeeds but URL is the profile URL (`facebook.com/me`) instead of the specific post. |
| **Cause** | Facebook's React UI doesn't expose post permalinks as `<a>` links in the DOM. This is expected behavior. |
| **Fix** | The profile URL is used as a fallback. The metric scraper can still find the post by visiting the profile page. This is a known limitation. |

### Reddit: Body Text Not Entered

| | |
|---|---|
| **Problem** | Reddit post has a title but empty body. |
| **Cause** | The Lexical editor is inside shadow DOM. The `findInShadow()` JavaScript function couldn't locate `div[contenteditable="true"][data-lexical-editor="true"]` in any shadow root. |
| **Fix** | Reddit may have changed their editor component. The title-only post still goes through. Check if the submit page structure has changed at `reddit.com/user/{username}/submit`. |

### Reddit: Post Button Stays Disabled

| | |
|---|---|
| **Problem** | After filling content, the Post button never becomes enabled. |
| **Cause** | Image is still uploading. The code waits up to 15 seconds (checking every second). |
| **Fix** | If using large images, increase the wait or reduce image size. The code checks `post_btn.is_enabled()` in a loop of 15 iterations with 1-second sleeps. |

---

## Duplicate Posts

### Same Post Executes Twice

| | |
|---|---|
| **Problem** | The background agent posts the same content to the same platform twice. |
| **Cause** | Race condition in the 60-second tick. Before the fix, `get_due_posts()` could return the same post on consecutive ticks if execution took longer than 60 seconds. |
| **Fix** | Already handled. `execute_due_posts()` marks all due posts as `posting` status immediately with a single SQL UPDATE before executing any of them. Only posts with `status = 'queued'` are picked up. Check for duplicates: |

```sql
-- Find duplicate posts (same campaign + platform + date)
SELECT campaign_server_id, platform, date(posted_at) AS day, COUNT(*) AS cnt
FROM local_post
GROUP BY campaign_server_id, platform, day
HAVING cnt > 1;
```

### Duplicate Campaign Invitations

| | |
|---|---|
| **Problem** | Same campaign appears multiple times in the dashboard. |
| **Cause** | The poll returns campaigns the user already has locally. |
| **Fix** | Already handled. `poll_campaigns()` checks for existing campaigns by `campaign_id` and upserts (updates existing, creates new). The `local_campaign.server_id` is the PRIMARY KEY, preventing true duplicates. |

---

## URL Capture Failures

### Post Sent but URL Unknown

| | |
|---|---|
| **Problem** | Log shows "Post sent but URL unknown" or `post_url` is `posted_but_url_unknown:platform:id`. |
| **Cause** | The platform-specific URL extraction failed after the post was successfully submitted. Each platform has different URL capture methods that can break if the DOM changes. |
| **Fix** | The post is recorded with a placeholder URL (`posted_but_url_unknown:...`) and status `posted_no_url`. The metric scraper will attempt to find the post later. No content is lost. |

URL capture methods by platform:

| Platform | Primary Method | Fallback |
|----------|---------------|----------|
| X | Navigate to profile, find first `article[data-testid="tweet"] a[href*="/status/"]` (5 retries) | `https://x.com/posted` |
| LinkedIn | "View post" link in success dialog (`a:has-text("View post")`, 30s timeout) | Activity page `/in/me/recent-activity/all/` -> first `a[href*="/feed/update/"]` |
| Facebook | Navigate to `/me` profile page | `https://facebook.com/posted` |
| Reddit | Redirect URL query param `?created=t3_XXXXX` -> construct `/user/{username}/comments/{id}/` | Poll URL for `/comments/` path (8 attempts, 2s each) |

---

## Content Generation Failures

### All AI Providers Failed

| | |
|---|---|
| **Problem** | Content generation returns empty or errors for all platforms. |
| **Cause** | All API keys in the fallback chain are exhausted, invalid, or rate-limited. The chain is: Gemini -> Mistral -> Groq. |
| **Fix** | Check API keys in `config/.env`: |

```bash
# Verify keys are set
grep -E "GEMINI_API_KEY|MISTRAL_API_KEY|GROQ_API_KEY" config/.env
```

If all keys are exhausted, add fresh keys. The `ContentGenerator` initializes providers based on which `*_API_KEY` environment variables are set. With zero keys, `text_providers` is empty and generation will fail.

### Content Not Generated for Campaign

| | |
|---|---|
| **Problem** | Campaign is accepted but no drafts appear. |
| **Cause** | Campaign status is not in the accepted set. Only campaigns with status `assigned`, `accepted`, `content_generated`, `approved`, `posted`, or `active` get content generated. |
| **Fix** | Check the campaign status: |

```sql
SELECT server_id, title, status, invitation_status FROM local_campaign;
```

If status is `pending_invitation`, the user hasn't accepted the campaign yet. Accept it via the dashboard.

### Repetitive Content Across Days

| | |
|---|---|
| **Problem** | Generated content is too similar day over day. |
| **Cause** | The anti-repetition mechanism passes the first 80 characters of the 12 most recent drafts as `previous_hooks`. If the prompt or campaign brief is very narrow, variety is limited. |
| **Fix** | This is working as designed but can be improved by broadening the campaign brief or content guidance. The `day_number` is calculated from unique dates in the draft history to vary the prompt. |

---

## Background Agent Issues

### Agent Not Starting

| | |
|---|---|
| **Problem** | Background tasks (polling, posting, scraping) don't run. |
| **Cause** | The agent runs as an asyncio task inside the dashboard/sidecar process. If `start_background_agent()` isn't called, or the event loop isn't running, the agent won't start. |
| **Fix** | Verify the dashboard is running (`python scripts/campaign_dashboard.py`). The agent logs "Background agent started" on successful startup. Check `logs/` for agent output. If the agent was already running, it logs "Background agent already running" and returns the existing instance. |

### Agent Paused

| | |
|---|---|
| **Problem** | Agent is running but not executing any tasks. |
| **Cause** | `agent.pause()` was called (e.g., via dashboard UI). The main loop continues but skips all task execution when `self.paused = True`. |
| **Fix** | Resume via `agent.resume()` or restart the dashboard process. |

### Task Crashes Don't Stop Agent

| | |
|---|---|
| **Problem** | One task (e.g., metric scraping) errors but other tasks keep running. |
| **Cause** | This is by design. Each task in the main loop is wrapped in its own try/except. Failures are logged but don't propagate to the loop. |
| **Fix** | Check logs for the specific task error. Common: `"Campaign poll crashed"`, `"Due posts check crashed"`, `"Session health check crashed"`, `"Metric scraping crashed"`. |

---

## Server-Side Issues

### Campaign Matching Returns No Results

| | |
|---|---|
| **Problem** | User polls for campaigns but gets an empty list. |
| **Cause** | Hard filters in `matching.py` rejected all campaigns. Filters check: niche tag overlap, target region match, required platform availability, minimum follower counts. |
| **Fix** | Verify the user's profile has matching niche tags, correct audience region, and the platforms required by available campaigns. Check via API: |

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/users/me
```

### Server Unreachable (Connection Errors)

| | |
|---|---|
| **Problem** | `server_client.py` logs "Server unreachable" with exponential backoff retries. |
| **Cause** | Server not running, wrong URL in `CAMPAIGN_SERVER_URL`, or network issue. Production server is at `https://api.pointcapitalis.com`. |
| **Fix** | The client retries 3 times with exponential backoff (5s, 10s, 20s). If all retries fail, the error propagates. Check health: |

```bash
# Production
curl https://api.pointcapitalis.com/health

# Local dev
curl http://localhost:8000/health
```

### Metric Scraping Schedule

| | |
|---|---|
| **Problem** | Metrics not being collected or seem stale. |
| **Cause** | The scraper runs every 60 seconds but only scrapes posts that are due based on the schedule: T+1h, T+6h, T+24h, T+72h after posting. |
| **Fix** | Check which posts need scraping: |

```sql
-- Posts with their latest metric scrape time
SELECT p.id, p.platform, p.posted_at,
       MAX(m.scraped_at) AS last_scraped
FROM local_post p
LEFT JOIN local_metric m ON m.post_id = p.id
GROUP BY p.id
ORDER BY p.posted_at DESC
LIMIT 10;
```

---

## Environment and Configuration

### Missing config/.env

| | |
|---|---|
| **Problem** | Timing parameters, API keys, or `HEADLESS` mode not applied. |
| **Cause** | `config/.env` doesn't exist or is missing keys. |
| **Fix** | Create `config/.env` with at least the AI API keys. Key variables: |

| Variable | Purpose | Default |
|----------|---------|---------|
| `HEADLESS` | Run browser in headless mode (`true`/`false`) | `false` |
| `POST_INTERVAL_MIN_SEC` | Min seconds between platform posts | `30` |
| `POST_INTERVAL_MAX_SEC` | Max seconds between platform posts | `90` |
| `PAGE_LOAD_TIMEOUT_SEC` | Page load timeout | `30` |
| `COMPOSE_FIND_TIMEOUT_SEC` | Compose element timeout | `15` |
| `RETRY_DELAY_SEC` | Retry delay after failure | `300` |
| `GEMINI_API_KEY` | Gemini API key (primary content gen) | (none) |
| `MISTRAL_API_KEY` | Mistral API key (fallback) | (none) |
| `GROQ_API_KEY` | Groq API key (fallback) | (none) |
| `CAMPAIGN_SERVER_URL` | Override server URL | `http://localhost:8000` (set to `https://api.pointcapitalis.com` for prod) |

### Platform Not Posting

| | |
|---|---|
| **Problem** | A platform is skipped during posting. |
| **Cause** | Platform is disabled in `config/platforms.json` (`"enabled": false`). Currently Instagram and TikTok are disabled. |
| **Fix** | Check `config/platforms.json` and set `"enabled": true` for the platform. Also ensure the platform has a browser profile (`profiles/<platform>-profile/` directory exists). |

### TikTok Blocked (India)

| | |
|---|---|
| **Problem** | TikTok fails to load or is blocked. |
| **Cause** | TikTok is blocked in India. Requires a VPN proxy. |
| **Fix** | Set a proxy in `config/platforms.json` under the `tiktok` key: |

```json
{
  "tiktok": {
    "enabled": true,
    "proxy": "socks5://127.0.0.1:1080"
  }
}
```

The `_launch_context()` function in `post.py` passes the proxy to Playwright's `launch_persistent_context()`. Any platform can have a `"proxy"` key.

---

## Quick Diagnostic Commands

```bash
# Check all session health statuses
python scripts/utils/session_health.py

# Check local database for recent activity
sqlite3 data/local.db "SELECT 'campaigns:', COUNT(*) FROM local_campaign UNION ALL SELECT 'posts:', COUNT(*) FROM local_post UNION ALL SELECT 'drafts:', COUNT(*) FROM agent_draft UNION ALL SELECT 'scheduled:', COUNT(*) FROM post_schedule WHERE status='queued' UNION ALL SELECT 'failed:', COUNT(*) FROM post_schedule WHERE status='failed';"

# Check server connectivity (run server locally first)
curl -s http://localhost:8000/health

# View recent poster logs
tail -50 logs/poster.log

# View recent session health logs
tail -50 logs/session_health.log

# Check which platforms are enabled
python -c "import json; p=json.load(open('config/platforms.json')); print({k:v['enabled'] for k,v in p.items()})"
```
