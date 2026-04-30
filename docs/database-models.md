# Amplifier -- Database Models

## Server Database (Supabase PostgreSQL / SQLite)

### Company
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| name | varchar(255) | Company name |
| email | varchar(255) | Unique, indexed |
| password_hash | varchar(255) | pbkdf2:sha256 |
| balance | numeric(12,2) | Available funds for campaigns (legacy) |
| balance_cents | int | Available funds in integer cents (v2) |
| status | varchar(20) | active (default) |
| tos_accepted_at | timestamptz (nullable) | When the company accepted ToS + Privacy Policy at registration. Required for new registrations (`accept_tos: true` on `POST /api/auth/company/register`). Added 2026-04-30 (Task #28). |
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
| campaign_type | varchar(20) | `ai_generated` (default) or `repost` (deferred feature) |
| campaign_goal | varchar(30) | brand_awareness, leads, virality, engagement |
| tone | varchar(30) | Campaign tone (nullable) |
| preferred_formats | jsonb | Per-platform format preferences |
| disclaimer_text | text | FTC/legal disclaimer (nullable) |
| created_at | datetime | Auto-set |
| updated_at | datetime | Auto-update |

### CampaignPost (repost content per platform — deferred feature)
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| campaign_id | int (FK) | References Campaign |
| platform | varchar(20) | x, linkedin, facebook, reddit |
| content | text | Post text |
| image_url | text (nullable) | Image URL |
| post_order | int | Ordering within platform (default 1) |
| scheduled_offset_hours | int | Offset from campaign start (default 0) |
| created_at | datetime | Auto-set |

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
| tier | varchar(20) | Reputation tier: seedling (default), grower, amplifier |
| successful_post_count | int | Lifetime successful posts (drives tier promotion) |
| trust_score | int | 0-100, default 50 |
| mode | varchar(20) | full_auto, semi_auto |
| earnings_balance | numeric(12,2) | Withdrawal-ready balance (legacy) |
| earnings_balance_cents | int | Withdrawal-ready balance in integer cents (v2) |
| total_earned | numeric(12,2) | Lifetime earnings (legacy) |
| total_earned_cents | int | Lifetime earnings in integer cents (v2) |
| stripe_account_id | varchar(255) | Stripe Connect Express account ID — set when user completes onboarding. Required for `POST /api/users/me/payout` (returns 400 when null). Added 2026-04-30 (Task #18 + Task #19 readiness). |
| tos_accepted_at | timestamptz (nullable) | When the user accepted ToS + Privacy Policy at registration. Required for new registrations (`accept_tos: true` on `POST /api/auth/register`). Added 2026-04-30 (Task #28). |
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
| content_mode | varchar(20) | ai_generated, user_customized, repost |
| payout_multiplier | numeric(3,2) | Always 1.0 in v2 |
| invited_at | datetime | When invitation sent |
| responded_at | datetime | When user accepted/rejected (nullable) |
| expires_at | datetime | 3 days after invitation (indexed) |
| decline_reason | text (nullable) | Reason for rejection (quick-select or custom text) |
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
| amount | numeric(12,2) | Payout amount (legacy) |
| amount_cents | int | Payout amount in integer cents (v2) |
| period_start | datetime(tz) | Billing period start |
| period_end | datetime(tz) | Billing period end |
| status | varchar(20) | pending, available, processing, paid, failed, voided |
| available_at | datetime(tz) | When earning becomes withdrawable (created_at + 7 days) |
| breakdown | jsonb | Detailed earnings breakdown |
| created_at | datetime | Auto-set |

### Penalty
| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| user_id | int (FK) | References User, indexed |
| post_id | int (FK) | References Post (nullable) |
| reason | varchar(30) | content_removed, off_brief, fake_metrics |
| amount | numeric(12,2) | Penalty deducted (legacy) |
| amount_cents | int | Penalty deducted in integer cents (v2) |
| description | text | Details (nullable) |
| appealed | bool | Whether user appealed |
| appeal_result | text | Appeal decision (nullable) |
| created_at | datetime | Auto-set |

---

## Local Database (User App -- SQLite at `data/local.db`)

> **Note (2026-04-26):** The `agent_user_profile` table was **dropped** (Bug #55). It had no active writer; `get_user_profiles()` always returned empty, causing content-agent strategy refinement to silently no-op. Profile reads now go through `scraped_profile` (the table the profile scraper actually writes to during onboarding). Fresh DB inits no longer create `agent_user_profile`.

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| local_campaign | Tracked campaigns | server_id, assignment_id, title, brief, assets, content_guidance, payout_rules, payout_multiplier, status, invitation_status, invited_at, expires_at, responded_at |
| local_post | Posted content | campaign_server_id, platform, post_url, content_hash, synced |
| local_metric | Engagement data | post_id, impressions, likes, reposts, comments, is_final |
| local_earning | Earnings log | campaign_server_id, amount, period, status |
| settings | Key-value config | key (PK), value |
| scraped_profile | Platform profiles | platform (UNIQUE), follower_count, following_count, display_name, profile_pic_url, bio, recent_posts (JSON), engagement_rate, posting_frequency, ai_niches (JSON), profile_data (JSON) |
| post_schedule | Post queue | campaign_server_id, platform, scheduled_at, content, image_path, status, error_code, execution_log, max_retries |
| agent_draft | Generated drafts | campaign_id, platform, draft_text, image_path, approved, posted |
| agent_research | Campaign research | campaign_id, research_type, content, source_url |
| agent_content_insights | Content performance tracking | platform, pillar_type, hook_type, avg_engagement_rate, sample_count, best_performing_text |
| local_notification | Event feed | type, title, message, data (JSON), read |

---

## Relationships Diagram

```
Company 1--* Campaign 1--* CampaignAssignment *--1 User
                  |                     |
                  1                     1
                  |                     |
                  * CampaignPost        * Post 1--* Metric

User 1--* Payout
User 1--* Penalty
Campaign 1--* CampaignInvitationLog *--1 User
```
