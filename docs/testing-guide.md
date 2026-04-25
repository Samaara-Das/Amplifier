# Testing Guide

How to test posting, campaign flows, matching, and the background agent. There is no automated test suite that runs against real platforms -- verification is manual against live accounts.

---

## Testing Posting (Per Platform)

### Quick Single-Platform Test

```bash
python scripts/tests/test_posting.py <platform>
```

Where `<platform>` is one of: `x`, `linkedin`, `facebook`, `reddit`, `all`.

This script posts test content in **headed mode** (browser visible, `HEADLESS=false`) and reports the post URL. Delete the post manually after verifying.

### Test All Post Types (Text, Image+Text, Image-Only)

```bash
python scripts/tests/test_all_post_types.py
```

Requires `image.png` in the project root. Tests 3 post types on all 4 platforms (12 tests total):

| Platform | Text-Only | Image+Text | Image-Only |
|----------|-----------|------------|------------|
| X | `content.x = "text"` | `content.x = "text"` + `image_path` | `content.x = ""` + `image_path` |
| LinkedIn | `content.linkedin = "text"` | `content.linkedin = "text"` + `image_path` | `content.linkedin = ""` + `image_path` |
| Facebook | `content.facebook = "text"` | `content.facebook = "text"` + `image_path` | `content.facebook = ""` + `image_path` |
| Reddit | JSON `{title, body}` | JSON `{title, body}` + `image_path` | JSON `{title, body=""}` + `image_path` |

The script prints a summary table with SUCCESS/PARTIAL/FAILED status and captured URLs.

### Draft Structure for Manual Testing

To test posting via `post.py` directly, create a JSON file in `drafts/pending/`:

```json
{
  "id": "test-001",
  "content": {
    "x": "Test post text for X. #test",
    "linkedin": "Test post text for LinkedIn.\n\nPlease ignore. #test",
    "facebook": "Test post for Facebook.",
    "reddit": "{\"title\": \"Test post title\", \"body\": \"Test body text.\"}"
  },
  "image_path": "C:/path/to/image.png"
}
```

Then run:

```bash
python scripts/post.py
```

It picks up the oldest pending draft and posts to all enabled platforms. After posting, drafts move from `drafts/pending/` to `drafts/posted/` (success) or `drafts/failed/` (failure).

### Platform-Specific Gotchas During Testing

| Platform | Gotcha |
|----------|--------|
| X | Overlay div blocks pointer events. Uses `Ctrl+Enter` keyboard shortcut to submit. If post button shows as disabled (`aria-disabled="true"`), image upload likely failed. Image upload via hidden `input[data-testid="fileInput"]`. Screenshots saved to `logs/x_before_post.png` and `logs/x_after_post.png`. |
| LinkedIn | Shadow DOM -- must use Playwright `locator()` (pierces shadow), NOT `wait_for_selector()` (does not pierce). Image upload via clipboard paste (`ClipboardEvent`). URL captured from "View post" link in success dialog, or fallback to `/in/me/recent-activity/all/`. |
| Facebook | Image upload via clipboard paste. URL capture falls back to profile URL (`/me`) since React UI doesn't expose post permalinks as `<a>` links. |
| Reddit | Posts to user profile (`/user/{username}/submit`), not to subreddits. Body text uses Lexical editor inside shadow DOM -- filled via JS `findInShadow()` + `focus()` + `keyboard.type()`. Post button may stay disabled up to 15 seconds while image uploads. URL extracted from redirect query param `?created=t3_XXXXX`. |

---

## Testing the Campaign Flow

The full campaign lifecycle: create campaign (company) -> match to user -> generate content -> approve -> post -> scrape metrics.

### Step 1: Create a Test Campaign

Use the company dashboard or the API directly:

```bash
# Register a test company (run server locally first: cd server && uvicorn app.main:app)
curl -X POST http://localhost:8000/api/auth/company/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test1234", "company_name": "TestCo"}'

# Create a campaign (use the returned token)
curl -X POST http://localhost:8000/api/campaigns \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "TEST: My Campaign",
    "brief": "Test campaign brief",
    "targeting": {"niche_tags": ["technology"], "target_regions": ["us"]},
    "payout_rules": {"rate_per_1k_impressions": 1.0},
    "budget_total": 100
  }'
```

### Step 2: Match and Accept Campaign (User Side)

```bash
# Start the campaign dashboard
python scripts/campaign_dashboard.py
# Open http://localhost:5222 -> Campaigns tab -> Accept invitation
```

Or trigger polling directly:

```bash
python scripts/campaign_runner.py --once
```

### Step 3: Generate Content

Content generates automatically when the background agent detects an accepted campaign (every 2 minutes via `generate_daily_content()`). To trigger manually, open the dashboard and use the "Generate" button.

The content generator uses a provider fallback chain: Gemini -> Mistral -> Groq. API keys are loaded from `config/.env` (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`).

### Step 4: Approve and Schedule

In the dashboard (http://localhost:5222):
1. Go to Campaigns tab
2. Click the campaign
3. Review generated drafts (stored in `agent_draft` table)
4. Approve or edit

In **full_auto** mode, drafts are auto-approved and auto-scheduled with 30-minute spacing starting 5 minutes from generation time.

### Step 5: Verify Posting

Posts execute when `scheduled_at` time arrives. The background agent checks every 60 seconds. Before executing, posts are marked as `posting` to prevent duplicate execution from the next tick.

```bash
# Check scheduled posts in the local database
sqlite3 data/local.db "SELECT id, platform, scheduled_at, status FROM post_schedule ORDER BY scheduled_at DESC LIMIT 10;"
```

### Step 6: Verify Metric Scraping

After posting, the metric scraper revisits posts at T+1h, T+6h, T+24h, and T+72h:

```bash
# Check scraped metrics
sqlite3 data/local.db "SELECT p.platform, m.impressions, m.likes, m.reposts, m.scraped_at FROM local_metric m JOIN local_post p ON m.post_id = p.id ORDER BY m.scraped_at DESC LIMIT 10;"
```

---

## Testing Matching (E2E)

A dedicated test creates fake users and campaigns on the production server, then verifies matching:

```bash
# Create test data (3 campaigns + 3 users with different niches)
python scripts/tests/test_matching_e2e.py setup

# Run matching tests (verifies each user matches the correct campaigns)
python scripts/tests/test_matching_e2e.py test

# Clean up test data from production
python scripts/tests/test_matching_e2e.py cleanup
```

The test creates:

| Campaign | Target Niches | Expected Match |
|----------|---------------|----------------|
| CodeVault Pro (tech) | `technology`, `ai`, `business` | Tech user |
| GlowUp Skincare (beauty) | `beauty`, `fashion`, `lifestyle` | Beauty user |
| FitTrack Home Gym (fitness) | `fitness`, `health`, `sports` | Fitness user |

And 3 users with corresponding niche profiles. The test verifies both positive matches (user matches correct campaign) and negative matches (user does NOT match wrong campaign).

**Note**: This test runs against a local server (`http://localhost:8000`) and creates real data. Production server is offline — always run locally. Always run `cleanup` after testing.

---

## Verifying the Background Agent

The background agent (`scripts/background_agent.py`) runs as an asyncio task inside the dashboard process. It manages all automated tasks on a staggered schedule.

### Agent Task Intervals

| Task | Interval | Function | What It Does |
|------|----------|----------|--------------|
| Due posts check | 60s | `execute_due_posts()` | Executes queued posts whose `scheduled_at` has passed |
| Campaign polling | 10 min | `poll_campaigns()` | Polls server for new campaign invitations |
| Content generation | 2 min | `generate_daily_content()` | Generates daily content for accepted campaigns |
| Metric scraping | 60s | `run_metric_scraping()` | Scrapes engagement metrics from posted URLs |
| Session health check | 30 min | `check_sessions()` | Verifies platform login sessions are valid |
| Profile refresh | 7 days | `refresh_profiles()` | Re-scrapes connected platform profiles |

Individual task failures do not crash the agent -- each task is wrapped in try/except.

### Checking Agent Status

The agent stores notifications in the `local_notification` table:

```sql
-- Recent notifications from the agent
SELECT type, title, message, created_at
FROM local_notification
ORDER BY created_at DESC
LIMIT 20;
```

Notification types: `new_campaigns`, `post_published`, `post_failed`, `session_expired`, `profile_refreshed`.

### Checking Session Health

```bash
# CLI: check all connected platforms
python scripts/utils/session_health.py

# Check specific platform
python scripts/utils/session_health.py --platform x

# Re-authenticate (opens visible browser for manual login)
python scripts/utils/session_health.py --platform linkedin --reauth
```

Session status values:
- **green**: Authenticated elements found on platform home page
- **yellow**: Uncertain -- neither auth nor login elements detected
- **red**: Login page elements detected, session expired

Health results are cached in `settings` table under key `session_health`.

---

## Checking Local Database State

The local SQLite database is at `data/local.db`. Useful queries:

### Campaigns

```sql
-- All campaigns with status
SELECT server_id, title, status, invitation_status, company_name, created_at
FROM local_campaign
ORDER BY created_at DESC;

-- Accepted campaigns (ones that get content generated)
SELECT server_id, title, status
FROM local_campaign
WHERE status IN ('assigned', 'accepted', 'content_generated', 'approved', 'posted', 'active');
```

### Drafts

```sql
-- Today's drafts
SELECT id, campaign_id, platform, substr(draft_text, 1, 80) AS preview, approved, posted, iteration, created_at
FROM agent_draft
WHERE date(created_at) = date('now')
ORDER BY created_at DESC;

-- Pending drafts (generated but not approved)
SELECT id, campaign_id, platform, approved, posted
FROM agent_draft
WHERE approved = 0 AND posted = 0;

-- Draft count per campaign per day (checks if daily generation ran)
SELECT campaign_id, date(created_at) AS day, COUNT(*) AS drafts
FROM agent_draft
GROUP BY campaign_id, day
ORDER BY day DESC;
```

### Scheduled Posts

```sql
-- Upcoming scheduled posts
SELECT id, campaign_server_id, platform, scheduled_at, status, draft_id
FROM post_schedule
WHERE status = 'queued'
ORDER BY scheduled_at ASC;

-- Recent post history (all statuses)
SELECT id, platform, scheduled_at, status, error_message
FROM post_schedule
ORDER BY scheduled_at DESC
LIMIT 20;

-- Failed posts (with error details)
SELECT id, platform, scheduled_at, error_message
FROM post_schedule
WHERE status = 'failed'
ORDER BY scheduled_at DESC;

-- Posts currently being executed
SELECT id, platform, scheduled_at
FROM post_schedule
WHERE status = 'posting';
```

### Posted Content

```sql
-- All posts with URLs
SELECT id, campaign_server_id, platform, post_url, posted_at, synced, status
FROM local_post
ORDER BY posted_at DESC;

-- Unsynced posts (not yet reported to server)
SELECT id, platform, post_url, posted_at
FROM local_post
WHERE synced = 0;
```

### Metrics

```sql
-- Latest metrics per post
SELECT p.platform, p.post_url, m.impressions, m.likes, m.reposts, m.comments, m.scraped_at, m.is_final
FROM local_metric m
JOIN local_post p ON m.post_id = p.id
ORDER BY m.scraped_at DESC
LIMIT 20;

-- Unreported metrics (not yet sent to server)
SELECT id, post_id, impressions, likes, scraped_at
FROM local_metric
WHERE reported = 0;
```

### Settings and Session Health

```sql
-- All settings
SELECT key, substr(value, 1, 100) AS value_preview FROM settings;

-- Session health specifically (JSON blob)
SELECT value FROM settings WHERE key = 'session_health';
```

---

## Test Data Setup

### Creating a Test Draft Manually

```bash
python -c "
import json
from pathlib import Path
draft = {
    'id': 'manual-test-001',
    'content': {
        'x': 'Manual test post for X. Delete after. #test',
        'linkedin': 'Manual test for LinkedIn.\n\nPlease ignore.',
        'facebook': 'Manual test for Facebook.',
        'reddit': json.dumps({'title': 'Manual test - delete', 'body': 'Test body.'})
    }
}
Path('drafts/pending').mkdir(parents=True, exist_ok=True)
Path('drafts/pending/manual-test-001.json').write_text(json.dumps(draft, indent=2))
print('Draft created at drafts/pending/manual-test-001.json')
"
```

### Running Unit Tests

```bash
# Content generator tests (prompt validation, JSON parsing, provider chain)
python -m pytest scripts/tests/test_content_generator.py -v

# Post import verification only
python -m pytest scripts/tests/test_content_generator.py::TestPostImports -v
```

These tests do NOT hit real APIs or platforms. They verify:
- Content prompt has no personal finance references (is UGC-generic)
- Prompt has correct template placeholders (`{title}`, `{brief}`, `{content_guidance}`, `{assets}`, `{platforms}`)
- JSON parser handles markdown fences (`\`\`\`json`) and surrounding text
- Provider chain initializes correctly based on available API keys (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`)
- `post.py` imports without errors (verifies `human_delay`, `human_type`, `browse_feed` stubs exist)
