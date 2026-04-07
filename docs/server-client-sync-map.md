# Server-Client Data Sync Map

What data flows between the Amplifier server (FastAPI) and the local user app (Flask), when, and how conflicts are resolved.

---

## Sync Overview

```
SERVER (Vercel + Supabase)              LOCAL (User's Device)
                                        
Company, Campaign, User,                local_campaign, agent_draft,
CampaignAssignment, Post,              post_schedule, local_post,
Metric, Payout, Penalty                local_metric, local_earning,
                                        scraped_profile, settings
                                        
         ◄── poll_campaigns() ──        Campaign data (SERVER → LOCAL)
         ◄── get_earnings() ───         Earnings summary (SERVER → LOCAL)
         ── update_profile() ──►        Profile data (LOCAL → SERVER)
         ── report_posts() ────►        Post URLs (LOCAL → SERVER)
         ── report_metrics() ──►        Engagement data (LOCAL → SERVER)
         ── report_post_deleted() ►     Deletion signal (LOCAL → SERVER)
         ── accept/reject ─────►        Invitation response (LOCAL → SERVER)
```

---

## SERVER → LOCAL

### Campaign Polling

**Client function:** `server_client.poll_campaigns()`
**Server endpoints:** `GET /api/campaigns/invitations` + `GET /api/campaigns/active`
**Trigger:** Background agent every 10 minutes, or user refreshes Campaigns page
**Local storage:** `local_campaign` table via `upsert_campaign()`

**Field mapping (server → local):**

| Server Field | Local Field | Notes |
|---|---|---|
| `campaign_id` | `server_id` (PK) | Server-side campaign ID |
| `assignment_id` | `assignment_id` | User's assignment for this campaign |
| `title` | `title` | |
| `brief` | `brief` | |
| `assets` | `assets` | JSON: `{image_urls, links, hashtags, brand_guidelines}` |
| `content_guidance` | `content_guidance` | |
| `payout_rules` | `payout_rules` | JSON: rates per metric |
| `payout_multiplier` | `payout_multiplier` | Usually 1.0 |
| `company_name` | `company_name` | |
| `invitation_status` | `invitation_status` | Server assignment status |
| `invited_at` | `invited_at` | ISO timestamp |
| `expires_at` | `expires_at` | ISO timestamp |
| `responded_at` | `responded_at` | ISO timestamp |

**Conflict resolution:**
- **NEW campaign** (not in local DB): Insert with `invitation_status` from server
- **EXISTING campaign**: Update all metadata fields **EXCEPT `status`** — local status is preserved to prevent re-polling from resetting user's progress (e.g., `content_generated` back to `assigned`)
- **Exception**: Server terminal statuses (`cancelled`, `completed`, `expired`) DO overwrite local status

### Earnings Fetch

**Client function:** `server_client.get_earnings()`
**Server endpoint:** `GET /api/users/me/earnings`
**Trigger:** User navigates to Earnings page, or dashboard load
**Local storage:** Displayed directly, also cached in `local_earning` table

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `total_earned` | float | Lifetime total (all time) |
| `current_balance` | float | Available for withdrawal |
| `pending` | float | In 7-day hold period |
| `per_campaign` | array | `[{campaign_id, campaign_title, earned, pending}]` |
| `per_platform` | dict | `{x: float, linkedin: float, ...}` |
| `payout_history` | array | `[{payout_id, amount, status, created_at}]` |

**Conflict resolution:** Server is source of truth. Local display always fetches fresh from server.

---

## LOCAL → SERVER

### Profile Sync

**Client function:** `server_client.update_profile(data)`
**Server endpoint:** `PATCH /api/users/me`
**Trigger:** After onboarding (step 5), after profile refresh (every 7 days), manual re-scrape

**Fields sent:**

| Field | Source | Description |
|---|---|---|
| `platforms` | `scraped_profile` table | `{x: {username, connected: true}, linkedin: {...}, ...}` |
| `follower_counts` | `scraped_profile` table | `{x: 1500, linkedin: 500, ...}` |
| `niche_tags` | Onboarding selection | `["finance", "tech", "crypto"]` |
| `audience_region` | Onboarding / IP detection | `"us"`, `"uk"`, `"india"`, etc. |
| `mode` | Settings | `"semi_auto"` or `"full_auto"` |
| `scraped_profiles` | `scraped_profile` table | Per-platform summary: `{platform: {follower_count, bio, engagement_rate, profile_data, ...}}` |

**What stays local (NOT synced):**
- `recent_posts` content (too large, privacy concern)
- `profile_pic_url` (local path)
- Detailed `profile_data` for non-LinkedIn platforms

**Conflict resolution:** Client always overwrites server with latest scraped data. No merge logic.

### Post Reporting

**Client function:** `server_client.report_posts(posts)`
**Server endpoint:** `POST /api/posts`
**Trigger:** After each successful post execution in background agent
**Batch size:** All unsynced posts at once

**Fields sent per post:**

| Field | Source | Description |
|---|---|---|
| `assignment_id` | `local_campaign.assignment_id` | Server assignment ID |
| `platform` | `local_post.platform` | x, linkedin, facebook, reddit |
| `post_url` | `local_post.post_url` | Full URL to published post |
| `content_hash` | `local_post.content_hash` | SHA256 of posted content |
| `posted_at` | `local_post.posted_at` | ISO timestamp |

**Server response:** `{created: [{id, platform}, ...], count: int}`

**Post-sync:**
1. Map returned server post IDs to local posts
2. Set `local_post.server_post_id` = server ID
3. Set `local_post.synced = 1`

**What stays local:** `content` (full text), `image_path`, `draft_id`

**Dedup:** Server deduplicates by `(assignment_id, platform, post_url)`.

### Metric Reporting

**Client function:** `server_client.report_metrics(metrics)`
**Server endpoint:** `POST /api/metrics`
**Trigger:** After each metric scraping run (background agent, every 60s check)
**Prerequisite:** Post must be synced first (`server_post_id IS NOT NULL`)

**Fields sent per metric:**

| Field | Source | Description |
|---|---|---|
| `post_id` | `local_post.server_post_id` | Server-side post ID |
| `impressions` | `local_metric.impressions` | View count |
| `likes` | `local_metric.likes` | Like/reaction count |
| `reposts` | `local_metric.reposts` | Share/retweet count |
| `comments` | `local_metric.comments` | Comment count |
| `clicks` | `local_metric.clicks` | Always 0 (not scrapeable) |
| `scraped_at` | `local_metric.scraped_at` | ISO timestamp |
| `is_final` | `local_metric.is_final` | True at T+72h |

**Server response:** `{accepted: N, total_submitted: N, skipped_deleted: N, skipped_duplicate: N}`

**Post-sync:** Mark `local_metric.reported = 1`

**Dedup:** Server rejects duplicate `(post_id, scraped_at)` pairs.

**Side effect:** Server triggers billing on accepted metrics.

### Post Deletion Notification

**Client function:** `server_client.report_post_deleted(server_post_id)`
**Server endpoint:** `PATCH /api/posts/{post_id}/status`
**Trigger:** Metric scraper detects post was removed from platform
**Body:** `{status: "deleted"}`

**Server action:** Calls `void_earnings_for_post()` — voids all pending payouts, returns funds to campaign budget.

### Invitation Response

**Client functions:** `server_client.accept_invitation(id)`, `server_client.reject_invitation(id, reason)`
**Server endpoints:** `POST /api/campaigns/invitations/{id}/accept`, `POST /api/campaigns/invitations/{id}/reject`
**Trigger:** User clicks Accept/Reject in dashboard

**Accept side effects:**
- Server: Assignment status → `accepted`, increment `campaign.accepted_count`
- Local: `invitation_status = "accepted"`, `responded_at = now()`

**Reject side effects:**
- Server: Assignment status → `rejected`, increment `campaign.rejected_count`, store decline reason
- Local: `invitation_status = "rejected"`, `responded_at = now()`

---

## Sync Timing Summary

| Sync | Direction | Interval | Trigger |
|---|---|---|---|
| Campaign polling | SERVER → LOCAL | 10 min | Background agent periodic |
| Profile sync | LOCAL → SERVER | 7 days | Background agent `refresh_profiles()` |
| Post reporting | LOCAL → SERVER | After each post | Background agent `execute_due_posts()` |
| Metric reporting | LOCAL → SERVER | After each scrape | Background agent `run_metric_scraping()` |
| Earnings fetch | SERVER → LOCAL | On-demand | User opens Earnings page |
| Invitation response | LOCAL → SERVER | On-demand | User clicks Accept/Reject |
| Post deletion | LOCAL → SERVER | On-demand | Metric scraper detects deletion |
| Session health | LOCAL only | 30 min | Background agent `check_sessions()` |
| Content generation | LOCAL only | 2 min check | Background agent `generate_daily_content()` |

---

## Key Files

| File | Role |
|---|---|
| `scripts/utils/server_client.py` | All HTTP calls to server (auth, profiles, campaigns, posts, metrics, earnings) |
| `scripts/utils/local_db.py` | Local SQLite operations (upsert, query, mark synced) |
| `scripts/background_agent.py` | Orchestrates all sync flows on intervals |
| `scripts/utils/profile_scraper.py` | Profile scraping + `sync_profiles_to_server()` |
| `scripts/utils/metric_scraper.py` | Metric scraping + `sync_metrics_to_server()` |
