# Local Database Schema

SQLite database stored at `data/local.db`. Used by the Amplifier user app to track campaigns, posts, metrics, earnings, and agent pipeline state locally on the user's device. Credentials and content never leave the device.

**Connection settings**: WAL journal mode (`PRAGMA journal_mode=WAL`), `sqlite3.Row` row factory.

---

## Table: `local_campaign`

Mirrors campaigns from the Amplifier server. Upsert logic preserves local status to prevent re-polling from resetting progress.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `server_id` | INTEGER | **PK** | Campaign ID from the server |
| `assignment_id` | INTEGER | UNIQUE | The user's assignment ID for this campaign |
| `title` | TEXT | NOT NULL | Campaign title |
| `brief` | TEXT | NOT NULL | Campaign brief/description |
| `assets` | TEXT | `'{}'` | JSON string of campaign assets (image URLs, links, hashtags, brand guidelines) |
| `content_guidance` | TEXT | NULL | Tone, must-include phrases, forbidden phrases |
| `payout_rules` | TEXT | `'{}'` | JSON string of payout rates (rate_per_1k_impressions, rate_per_like, etc.) |
| `payout_multiplier` | REAL | `1.0` | Legacy field -- not used in v2 billing |
| `status` | TEXT | `'assigned'` | Local workflow status: `pending_invitation`, `assigned`, `accepted`, `content_generated`, `approved`, `posted`, `active`, `skipped`, `cancelled` |
| `content` | TEXT | NULL | Generated content (set when status moves to `content_generated`) |
| `invitation_status` | TEXT | `'pending_invitation'` | Invitation tracking: `pending_invitation`, `accepted`, `rejected`, `expired` |
| `invited_at` | TEXT | NULL | ISO timestamp when invitation was received |
| `expires_at` | TEXT | NULL | ISO timestamp when invitation expires |
| `responded_at` | TEXT | NULL | ISO timestamp when user accepted/rejected |
| `scraped_data` | TEXT | `'{}'` | JSON blob of scraped content research data |
| `company_name` | TEXT | NULL | Company display name |
| `created_at` | TEXT | `datetime('now')` | Row creation timestamp |
| `updated_at` | TEXT | `datetime('now')` | Last update timestamp |

---

## Table: `local_post`

Tracks posts made for campaigns. Posts are synced to the server after creation.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Local post ID |
| `campaign_server_id` | INTEGER | NULL | FK to `local_campaign.server_id` |
| `assignment_id` | INTEGER | NULL | Assignment ID for server reporting |
| `platform` | TEXT | NOT NULL | Platform name: `x`, `linkedin`, `facebook`, `reddit` |
| `post_url` | TEXT | NULL | URL of the published post (captured after posting) |
| `content` | TEXT | NULL | Text content that was posted |
| `content_hash` | TEXT | NULL | Hash of content for dedup on server side |
| `posted_at` | TEXT | NULL | ISO timestamp when the post went live |
| `status` | TEXT | `'posted'` | Post status |
| `server_post_id` | INTEGER | NULL | Post ID assigned by the server after sync |
| `synced` | INTEGER | `0` | `0` = not yet reported to server, `1` = synced |

**Foreign keys**: `campaign_server_id` references `local_campaign(server_id)`.

---

## Table: `local_metric`

Scraped engagement metrics for posts. Multiple rows per post (scraped at different times). The metric scraper decides the scraping schedule.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Metric row ID |
| `post_id` | INTEGER | NOT NULL | FK to `local_post.id` |
| `impressions` | INTEGER | `0` | View count |
| `likes` | INTEGER | `0` | Like/heart count |
| `reposts` | INTEGER | `0` | Repost/retweet/share count |
| `comments` | INTEGER | `0` | Comment/reply count |
| `clicks` | INTEGER | `0` | Link click count |
| `scraped_at` | TEXT | NOT NULL | ISO timestamp of when metrics were scraped |
| `is_final` | INTEGER | `0` | `1` if this is the final scrape for this post |
| `reported` | INTEGER | `0` | `0` = not yet sent to server, `1` = reported |

**Foreign keys**: `post_id` references `local_post(id)`.

---

## Table: `local_earning`

Tracks earnings per campaign period. Updated from server billing cycle results.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Earning row ID |
| `campaign_server_id` | INTEGER | NULL | Campaign this earning is for |
| `amount` | REAL | `0.0` | Earned amount in USD |
| `period` | TEXT | NULL | Billing period identifier |
| `status` | TEXT | `'pending'` | `pending` or `paid` |
| `updated_at` | TEXT | `datetime('now')` | Last update timestamp |

---

## Table: `settings`

Key-value store for app configuration (user mode, server URL, auth tokens, etc.).

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `key` | TEXT | **PK** | Setting name |
| `value` | TEXT | NULL | Setting value (stored as string) |

Common keys: `mode` (`semi_auto` or `full_auto`).

---

## Table: `scraped_profile`

Per-platform scraped profile data. One row per platform (UNIQUE constraint on `platform`). Used for campaign matching and server sync.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Row ID |
| `platform` | TEXT | NOT NULL, UNIQUE | Platform name |
| `follower_count` | INTEGER | `0` | Number of followers |
| `following_count` | INTEGER | `0` | Number of accounts followed |
| `bio` | TEXT | NULL | Profile bio text |
| `display_name` | TEXT | NULL | Display name on the platform |
| `profile_pic_url` | TEXT | NULL | URL to profile picture |
| `recent_posts` | TEXT | `'[]'` | JSON array of recent post summaries |
| `engagement_rate` | REAL | `0.0` | Calculated engagement rate |
| `posting_frequency` | REAL | `0.0` | Average posts per day/week |
| `ai_niches` | TEXT | `'[]'` | JSON array of AI-detected niche tags |
| `profile_data` | TEXT | NULL | JSON blob with extended fields (location, about, experience, education). LinkedIn only for now. |
| `scraped_at` | TEXT | NOT NULL | ISO timestamp of last scrape |

---

## Table: `post_schedule`

Queue of posts scheduled for future execution by the background agent. Created when drafts are approved (auto or manual).

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Schedule row ID |
| `campaign_server_id` | INTEGER | NOT NULL | FK to `local_campaign.server_id` |
| `platform` | TEXT | NOT NULL | Target platform |
| `scheduled_at` | TEXT | NOT NULL | ISO timestamp of when to post |
| `content` | TEXT | NULL | Post text content |
| `image_path` | TEXT | NULL | Local path to image file for the post |
| `draft_id` | INTEGER | NULL | Logical FK to `agent_draft.id` (no DB constraint) |
| `status` | TEXT | `'queued'` | `queued`, `posting`, `posted`, `posted_no_url`, `failed` |
| `error_message` | TEXT | NULL | Error details if status is `failed` or `posted_no_url` |
| `actual_posted_at` | TEXT | NULL | ISO timestamp of when the post actually went live |
| `local_post_id` | INTEGER | NULL | ID of the resulting `local_post` row after posting |
| `created_at` | TEXT | `datetime('now')` | Row creation timestamp |

**Foreign keys**: `campaign_server_id` references `local_campaign(server_id)`.

**Indexes**: `ix_post_schedule_status_time` on `(status, scheduled_at)`.

---

## Table: `agent_user_profile`

Agent pipeline table. Stores the user's writing style and voice per platform, extracted from their real posts. Used to generate on-brand content.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Row ID |
| `platform` | TEXT | UNIQUE | Platform name |
| `bio` | TEXT | NULL | User's bio on this platform |
| `recent_posts` | TEXT | NULL | JSON string of recent posts for style reference |
| `style_notes` | TEXT | NULL | AI-extracted style notes (tone, vocabulary, patterns) |
| `follower_count` | INTEGER | `0` | Follower count at extraction time |
| `extracted_at` | TEXT | NULL | ISO timestamp of when profile was extracted |

---

## Table: `agent_research`

Agent pipeline table. Stores research data gathered for a campaign (competitor posts, trending topics, URL content).

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Row ID |
| `campaign_id` | INTEGER | NULL | Logical FK to `local_campaign.server_id` |
| `research_type` | TEXT | NULL | Type of research (e.g., `url_scrape`, `competitor_analysis`) |
| `content` | TEXT | NULL | Research content/results |
| `source_url` | TEXT | NULL | URL that was researched |
| `created_at` | TEXT | `datetime('now')` | Row creation timestamp |

---

## Table: `agent_draft`

Agent pipeline table. Stores generated draft content per campaign per platform. Drafts go through an approval flow before posting.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Draft ID |
| `campaign_id` | INTEGER | NULL | Logical FK to `local_campaign.server_id` |
| `platform` | TEXT | NULL | Target platform |
| `draft_text` | TEXT | NULL | The generated post text |
| `pillar_type` | TEXT | NULL | Content pillar category |
| `quality_score` | REAL | `0` | AI-assigned quality score (higher = better) |
| `iteration` | INTEGER | `1` | Generation iteration / day number |
| `approved` | INTEGER | `0` | `0` = pending, `1` = approved, `-1` = rejected |
| `posted` | INTEGER | `0` | `1` if this draft has been posted |
| `created_at` | TEXT | `datetime('now')` | Row creation timestamp |

---

## Table: `agent_content_insights`

Agent pipeline table. Tracks which content types (pillar + hook combinations) perform best per platform. Used to improve future content generation.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Row ID |
| `platform` | TEXT | NULL | Platform name |
| `pillar_type` | TEXT | NULL | Content pillar category |
| `hook_type` | TEXT | NULL | Hook style used |
| `avg_engagement_rate` | REAL | `0` | Average engagement rate for this combination |
| `sample_count` | INTEGER | `0` | Number of posts in this sample |
| `best_performing_text` | TEXT | NULL | Text of the best-performing post with this combination |
| `last_updated` | TEXT | `datetime('now')` | Last update timestamp |

---

## Table: `local_notification`

Notification feed populated by the background agent. Displayed in the campaign dashboard.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | INTEGER | **PK, AUTOINCREMENT** | Notification ID |
| `type` | TEXT | NOT NULL | Notification type: `new_campaigns`, `post_published`, `post_failed`, `session_expired`, `profile_refreshed` |
| `title` | TEXT | NOT NULL | Short title for display |
| `message` | TEXT | NOT NULL | Notification body text |
| `data` | TEXT | `'{}'` | JSON string with extra data (counts, platform names, error details) |
| `read` | INTEGER | `0` | `0` = unread, `1` = read |
| `created_at` | TEXT | `datetime('now')` | Row creation timestamp |

**Indexes**: `ix_notification_read_time` on `(read, created_at DESC)`.

---

## Relationships

```
local_campaign (server_id)
  |
  |-- local_post (campaign_server_id) -----> local_metric (post_id)
  |
  |-- local_earning (campaign_server_id)
  |
  |-- post_schedule (campaign_server_id)
  |       |
  |       +-- draft_id ..................> agent_draft (id)  [logical, no FK constraint]
  |
  |-- agent_draft (campaign_id)         [logical, no FK constraint]
  |
  +-- agent_research (campaign_id)      [logical, no FK constraint]


scraped_profile          -- standalone, one row per platform (UNIQUE)
agent_user_profile       -- standalone, one row per platform (UNIQUE)
agent_content_insights   -- standalone, indexed by platform + pillar + hook
settings                 -- standalone key-value store
local_notification       -- standalone notification feed
```

Only `local_post` and `post_schedule` have enforced `FOREIGN KEY` constraints to `local_campaign`. All other cross-table references (agent_draft.campaign_id, agent_research.campaign_id, local_earning.campaign_server_id) are logical relationships without database-level enforcement.
