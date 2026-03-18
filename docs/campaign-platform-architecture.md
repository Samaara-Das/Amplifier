# Campaign Platform Architecture

## Overview

A two-sided marketplace where **companies** pay to promote their products/campaigns, and **users** earn money by auto-posting campaign content to their social media accounts using an AI-powered desktop application.

### Key Principle: User-Side Compute

All AI content generation, browser automation, and metric scraping happens on the user's device. The server is a lightweight campaign marketplace — it never touches social media credentials, never runs AI inference, never posts on anyone's behalf.

## System Components

```
┌─────────────────────────────────────────────────────────┐
│                    CENTRAL SERVER                        │
│  (Cloud — FastAPI + PostgreSQL + Redis)                  │
│                                                         │
│  Campaign CRUD │ User Registry │ Matching Engine         │
│  Metric Aggregation │ Billing │ Trust/Fraud              │
│  Company Dashboard │ Admin Dashboard                     │
│                                                         │
│                    REST API                              │
└──────────────────────┬──────────────────────────────────┘
                       │
            HTTPS (pull-based polling)
                       │
     ┌─────────────────┼─────────────────┐
     │                 │                 │
┌────▼────┐      ┌────▼────┐      ┌────▼────┐
│ User App│      │ User App│      │ User App│    x 1,000+ users
│(Desktop)│      │(Desktop)│      │(Desktop)│
│         │      │         │      │         │
│ Claude  │      │ Claude  │      │ Claude  │
│ CLI     │      │ CLI     │      │ CLI     │
│ Poster  │      │ Poster  │      │ Poster  │
│ Engager │      │ Engager │      │ Engager │
│ Scraper │      │ Scraper │      │ Scraper │
└─────────┘      └─────────┘      └─────────┘
```

## Communication: Pull-Based

User apps poll the server every 5-15 minutes. No persistent websocket connections.

- Resilient to offline users (they just poll when back online)
- Server doesn't need to track connection state for 1,000+ devices
- Simple REST API, standard HTTP

## Campaign Flow

```
1. Company creates campaign on server (brief, assets, budget, targeting, payout rules)
2. Server matches campaign to eligible users based on targeting criteria
3. User app polls: GET /api/campaigns/mine → receives list of assigned campaigns
4. User app generates content locally via Claude CLI using campaign brief
5. User app posts to 6 platforms via Playwright (existing auto-poster engine)
6. User app scrapes engagement metrics after posting (revisit posts at intervals)
7. User app reports: POST /api/metrics → post URLs, impressions, likes, reposts
8. Server aggregates metrics, calculates payouts
9. Company sees results in dashboard, budget decremented
10. User sees earnings in local dashboard
```

## Data Model

### Server (PostgreSQL)

**company** — organizations that create campaigns
- id, name, email, password_hash, billing_info, balance, api_key, created_at

**campaign** — promotion briefs from companies
- id, company_id (FK)
- title, brief (text — what to promote and how)
- assets (JSONB — image URLs, links, hashtags, brand guidelines)
- budget_total, budget_remaining (decimal)
- payout_rules (JSONB — rate_per_1k_impressions, rate_per_like, rate_per_repost, rate_per_click)
- targeting (JSONB — min_followers_per_platform, niche_tags[], required_platforms[])
- content_guidance (text — tone, must-include phrases, forbidden phrases)
- penalty_rules (JSONB — what triggers penalties, deduction amounts)
- status (draft | active | paused | completed | cancelled)
- start_date, end_date, created_at

**user** — people running the desktop app
- id, email, password_hash, device_fingerprint
- platforms (JSONB — which social accounts connected, usernames)
- follower_counts (JSONB — per platform, self-reported initially, verified via scraping)
- niche_tags (text[] — finance, tech, lifestyle, fitness, etc.)
- trust_score (integer 0-100, default 50)
- mode (full_auto | semi_auto | manual)
- earnings_balance, total_earned (decimal)
- status (active | suspended | banned)
- created_at

**campaign_assignment** — which users get which campaigns
- id, campaign_id (FK), user_id (FK)
- status (assigned | content_generated | posted | metrics_collected | paid | skipped)
- content_mode (ai_generated | user_customized | repost)
- payout_multiplier (decimal — 1.0 repost, 1.5 AI gen, 2.0 user-customized)
- assigned_at

**post** — individual social media posts created for campaigns
- id, assignment_id (FK), platform (x | linkedin | facebook | reddit | tiktok | instagram)
- post_url (text — proof of posting)
- content_hash (text — SHA256 of content, detect edits/deletions)
- posted_at
- status (live | deleted | flagged)

**metric** — engagement data scraped from posts
- id, post_id (FK)
- impressions, likes, reposts, comments, clicks (integer)
- scraped_at (timestamp)
- is_final (boolean — true after campaign ends, used for billing)

**payout** — earnings for users
- id, user_id (FK), campaign_id (FK)
- amount (decimal), period (date range)
- status (pending | processing | paid | failed)
- breakdown (JSONB — detailed earnings per metric type)

**penalty** — deductions from user earnings
- id, user_id (FK), post_id (FK)
- reason (content_removed | off_brief | fake_metrics | platform_violation)
- amount (decimal)
- appealed (boolean), appeal_result (text)
- created_at

### User App (SQLite — local mirror)

**local_campaign** — synced from server
- server_id, title, brief, assets, content_guidance, payout_rules, status

**local_post** — what was posted locally
- id, campaign_server_id, platform, post_url, content, content_hash, posted_at, synced (boolean)

**local_metric** — scraped engagement before reporting to server
- id, post_id, impressions, likes, reposts, comments, clicks, scraped_at, reported (boolean)

**local_earning** — calculated earnings per campaign
- campaign_server_id, amount, period, status

**settings** — user preferences
- key, value (mode, poll_interval, platforms_enabled, etc.)

## Campaign Matching Algorithm

When a user polls for campaigns, the server scores all active campaigns against the user's profile:

```
Hard filters (must pass all):
1. User has all required platforms the campaign targets
2. User meets minimum follower count per platform
3. User is not suspended/banned
4. Campaign has remaining budget
5. User hasn't already been assigned this campaign

Soft scoring (higher = better match):
- Niche overlap: +30 per matching niche tag
- Trust score: +0.5 per trust point
- Historical engagement rate: +20 per % above average
- Content mode willingness: +10 if user's mode matches campaign preference
```

Top N campaigns returned, sorted by score. High-trust users see the best campaigns.

## Trust & Penalty System

### Trust Score (0-100, starts at 50)

| Event | Impact |
|-------|--------|
| Post verified live after 24h | +1 |
| Above-average engagement rate | +2 |
| Campaign completed (all platforms posted) | +3 |
| User customized content (extra effort) | +1 |
| Post deleted within 24h | -10 |
| Content flagged by social platform | -15 |
| Metrics anomaly detected | -20 |
| Confirmed fake metrics | -50 + ban review |

### Fraud Detection (server background jobs)

1. **Spot-check scraping** — Server randomly picks 5% of post URLs, scrapes independently, compares to reported metrics
2. **Anomaly detection** — Flag users whose engagement is a statistical outlier vs. follower count
3. **Deletion monitoring** — User app re-checks posts at 24h and 72h. Deleted posts trigger auto-penalty
4. **Cross-user comparison** — Same campaign across many users should have proportional engagement. Outliers flagged.

## User App Modes

| Mode | Behavior | Payout Multiplier |
|------|----------|-------------------|
| Full Auto | App picks up campaigns, AI generates content, posts automatically | 1.5x (AI generated) |
| Semi-Auto | App shows campaigns, user reviews/edits AI content, approves | 2.0x (user customized) |
| Manual | User writes own content using campaign brief, approves each post | 2.0x (user customized) |
| Repost | App reposts company-provided content as-is (no AI generation) | 1.0x (base rate) |

## Content Generation (On-Device)

The existing auto-poster's Claude CLI generation pipeline is adapted:

1. Server sends campaign brief + content guidance + assets
2. User app builds a prompt: campaign brief + platform rules (from content-templates) + user's niche context
3. Claude CLI generates platform-native content for all 6 platforms (same as current generate.ps1)
4. If semi-auto/manual: content shown in local dashboard for review/edit
5. If full-auto: content goes straight to posting queue

## Metric Scraping

After posting, the user app revisits each post URL at intervals to scrape engagement:

- **T+1h** — first scrape (sanity check: post is live)
- **T+6h** — early engagement
- **T+24h** — primary metric (most engagement happens in first 24h)
- **T+72h** — final metric (used for billing if campaign is still active)

Scraping uses the same Playwright browser profiles already logged in.

## Billing Model

- Companies prepay a budget for each campaign
- As metrics come in, the server calculates cost:
  ```
  post_cost = (impressions / 1000 * rate_per_1k_impressions)
            + (likes * rate_per_like)
            + (reposts * rate_per_repost)
            + (clicks * rate_per_click)

  post_cost *= payout_multiplier  (1.0x repost, 1.5x AI, 2.0x custom)
  ```
- Platform takes X% cut (configurable, e.g., 20%)
- User receives (100 - X)% as earnings
- Campaign auto-pauses when budget_remaining < threshold
- Payouts processed in cycles (weekly or monthly)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Server API | Python + FastAPI |
| Server DB | PostgreSQL |
| Cache/Queue | Redis + ARQ |
| Server Hosting | Railway (MVP) → AWS (scale) |
| Company Dashboard | React or server-rendered (FastAPI + Jinja2 for MVP) |
| User App | Python (evolved from current auto-poster) |
| User Local DB | SQLite |
| User Dashboard | Flask (evolved from current review_dashboard.py) |
| Browser Automation | Playwright (existing) |
| AI Generation | Claude CLI (existing, user's own key) |
| Installer | PyInstaller + Inno Setup |
| Payments | Stripe Connect (for user payouts) |

## API Endpoints (Server)

### Auth
- POST /api/auth/register — user registration
- POST /api/auth/login — returns JWT
- POST /api/auth/company/register — company registration
- POST /api/auth/company/login — returns JWT

### Campaigns (User App)
- GET /api/campaigns/mine — poll for assigned campaigns (matched to user profile)
- PATCH /api/campaigns/assignments/{id} — update assignment status (content_generated, posted, skipped)

### Metrics (User App)
- POST /api/metrics — batch submit metrics for multiple posts
- POST /api/posts — register posted URLs with the server

### User Profile (User App)
- GET /api/users/me — get own profile
- PATCH /api/users/me — update platforms, follower counts, niche tags, mode
- GET /api/users/me/earnings — earnings summary and history

### Campaigns (Company Dashboard)
- POST /api/company/campaigns — create campaign
- GET /api/company/campaigns — list own campaigns
- GET /api/company/campaigns/{id} — campaign detail with metrics
- PATCH /api/company/campaigns/{id} — update/pause/cancel campaign
- GET /api/company/campaigns/{id}/analytics — detailed analytics (reach, engagement, spend, per-user breakdown)

### Admin
- GET /api/admin/users — list all users with trust scores
- GET /api/admin/campaigns — list all campaigns
- POST /api/admin/users/{id}/suspend — suspend user
- GET /api/admin/fraud/flags — flagged anomalies for review

## MVP Scope (1,000 Users)

### Phase 1: Server Foundation
- FastAPI project setup with PostgreSQL + Redis
- Auth system (JWT) for users and companies
- Database models and migrations (Alembic)
- Campaign CRUD API for companies
- User registration and profile API

### Phase 2: Campaign Distribution
- Campaign matching algorithm
- Assignment API (GET /campaigns/mine)
- Assignment status tracking

### Phase 3: User App Evolution
- Server communication layer (auth, polling, reporting)
- Campaign-aware content generation (adapt generate.ps1 to accept campaign briefs)
- Local SQLite database for campaigns, posts, metrics
- Updated Flask dashboard showing campaigns + earnings
- Mode selection (full auto / semi-auto / manual)

### Phase 4: Metrics & Billing
- Metric scraping (revisit posts at intervals via Playwright)
- Metric reporting API
- Server-side metric aggregation
- Billing calculation engine
- Company analytics dashboard

### Phase 5: Trust & Quality
- Trust score system
- Fraud detection background jobs
- Penalty system
- Spot-check scraping

### Phase 6: Distribution
- PyInstaller packaging
- Inno Setup installer
- Onboarding flow (register → connect platforms → set mode)
- Auto-update mechanism

### Phase 7: Payments
- Stripe Connect integration
- Automated payout cycles
- Earning withdrawal for users
