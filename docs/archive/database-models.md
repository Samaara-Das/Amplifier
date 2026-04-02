# Amplifier -- Database Models

## Server Database (Supabase PostgreSQL / SQLite)

### Company
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| name | varchar(255) | Company name |
| email | varchar(255) | Unique, indexed |
| password_hash | varchar(255) | pbkdf2:sha256 |
| balance | numeric(12,2) | Available funds for campaigns |
| created_at | datetime | Auto-set |
| updated_at | datetime | Auto-update |

### Campaign
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| company_id | int (FK) | References Company, indexed |
| title | varchar(255) | Campaign name |
| brief | text | Detailed campaign brief (AI-generated) |
| assets | jsonb | `{image_urls:[], file_urls:[], file_contents:[], hashtags:[], brand_guidelines:""}` |
| budget_total | numeric(12,2) | Initial budget |
| budget_remaining | numeric(12,2) | Current available budget |
| payout_rules | jsonb | `{rate_per_1k_impressions, rate_per_like, rate_per_repost, rate_per_click}` |
| targeting | jsonb | `{min_followers:{}, min_engagement, niche_tags:[], target_regions:[], required_platforms:[]}` |
| content_guidance | text | Instructions for creators (nullable) |
| penalty_rules | jsonb | `{post_deleted_24h, off_brief, fake_metrics}` |
| status | varchar(20) | draft, active, paused, completed, cancelled (indexed) |
| start_date | datetime(tz) | Campaign start |
| end_date | datetime(tz) | Campaign end |
| company_urls | jsonb | URLs provided during wizard |
| ai_generated_brief | bool | True if AI enriched the brief |
| budget_exhaustion_action | varchar(20) | auto_pause or auto_complete |
| budget_alert_sent | bool | True when budget <20% |
| screening_status | varchar(20) | pending, approved, flagged, rejected (indexed) |
| campaign_version | int | Incremented on content edits |
| invitation_count | int | Total invitations sent |
| accepted_count | int | Total accepted |
| rejected_count | int | Total rejected |
| expired_count | int | Total expired |
| max_users | int (nullable) | Cap on acceptances |
| created_at | datetime | Auto-set |
| updated_at | datetime | Auto-update |

### User
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| email | varchar(255) | Unique, indexed |
| password_hash | varchar(255) | pbkdf2:sha256 |
| device_fingerprint | varchar(255) | Optional (nullable) |
| platforms | jsonb | `{x: {connected: true}, linkedin: {connected: true}, ...}` |
| follower_counts | jsonb | `{x: 0, linkedin: 9497, ...}` |
| niche_tags | jsonb | `["finance", "tech", "ai"]` |
| audience_region | varchar(50) | us, uk, india, eu, latam, sea, global |
| trust_score | int | 0-100, default 50 |
| mode | varchar(20) | full_auto, semi_auto |
| earnings_balance | numeric(12,2) | Withdrawal-ready balance |
| total_earned | numeric(12,2) | Lifetime earnings |
| status | varchar(20) | active, suspended, banned (indexed) |
| scraped_profiles | jsonb | Full per-platform scraped data (bio, posts, engagement, etc.) |
| ai_detected_niches | jsonb | AI-classified niches (deprecated, use niche_tags) |
| last_scraped_at | datetime(tz) | Last profile refresh |
| created_at | datetime | Auto-set |
| updated_at | datetime | Auto-update |

### CampaignAssignment
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| campaign_id | int (FK) | References Campaign, indexed |
| user_id | int (FK) | References User, indexed |
| status | varchar(30) | pending_invitation, accepted, content_generated, posted, paid, rejected, expired |
| content_mode | varchar(20) | ai_generated, user_customized |
| payout_multiplier | numeric(3,2) | Always 1.0 in v2 |
| invited_at | datetime | When invitation sent |
| responded_at | datetime | When user accepted/rejected (nullable) |
| expires_at | datetime | 3 days after invitation (indexed) |
| assigned_at | datetime | Auto-set |
| updated_at | datetime | Auto-update |

### Post
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| assignment_id | int (FK) | References CampaignAssignment, indexed |
| platform | varchar(20) | x, linkedin, facebook, reddit |
| post_url | text | Full URL to posted content |
| content_hash | varchar(64) | SHA256 of content |
| posted_at | datetime(tz) | When post went live |
| status | varchar(20) | live, deleted, flagged |
| created_at | datetime | Auto-set |

### Metric
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| post_id | int (FK) | References Post, indexed |
| impressions | int | View count |
| likes | int | Like count |
| reposts | int | Retweet/share count |
| comments | int | Comment count |
| clicks | int | Link clicks (future, currently 0) |
| scraped_at | datetime(tz) | When metrics collected |
| is_final | bool | Whether this is the settled metric |
| created_at | datetime | Auto-set |

### Payout
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| user_id | int (FK) | References User, indexed |
| campaign_id | int (FK) | References Campaign (nullable for withdrawals) |
| amount | numeric(12,2) | Payout amount |
| period_start | datetime(tz) | Billing period start |
| period_end | datetime(tz) | Billing period end |
| status | varchar(20) | pending, processing, paid, failed |
| breakdown | jsonb | Detailed earnings breakdown |
| created_at | datetime | Auto-set |

### Penalty
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| user_id | int (FK) | References User, indexed |
| post_id | int (FK) | References Post (nullable) |
| reason | varchar(30) | content_removed, off_brief, fake_metrics |
| amount | numeric(12,2) | Penalty deducted |
| description | text | Details (nullable) |
| appealed | bool | Whether user appealed |
| appeal_result | text | Appeal decision (nullable) |
| created_at | datetime | Auto-set |

---

## Local Database (User App -- SQLite at `data/local.db`)

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| local_campaign | Tracked campaigns | server_id, assignment_id, status, invitation_status |
| local_post | Posted content | campaign_server_id, platform, post_url, content_hash, synced |
| local_metric | Engagement data | post_id, impressions, likes, reposts, comments, is_final |
| local_earning | Earnings log | campaign_server_id, amount, period, status |
| settings | Key-value config | key (PK), value |
| scraped_profile | Platform profiles | platform (UNIQUE), follower_count, bio, recent_posts (JSON), profile_data (JSON) |
| post_schedule | Post queue | campaign_server_id, platform, scheduled_at, content, status |
| agent_draft | Generated drafts | campaign_id, platform, draft_text, approved, posted |
| agent_research | Campaign research | campaign_id, research_type, content, source_url |
| local_notification | Event feed | type, title, message, data (JSON), read |

---

## Relationships Diagram

```
Company 1--* Campaign 1--* CampaignAssignment *--1 User
                                    |
                                    1
                                    |
                                    * Post 1--* Metric

User 1--* Payout
User 1--* Penalty
Campaign 1--* CampaignInvitationLog *--1 User
```
