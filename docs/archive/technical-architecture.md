# Amplifier -- Technical Architecture

## System Overview

Amplifier is a two-sided marketplace: companies create campaigns, users (amplifiers) earn money by posting campaign content on their social media accounts.

```
Company Dashboard (Vercel)          Amplifier Server (Vercel/Supabase)          User App (Local Desktop)
     |                                      |                                        |
     | create campaign                      |                                        |
     |------------------------------------->|                                        |
     |                                      | match users via AI                     |
     |                                      |--------------------------------------->|
     |                                      |                   poll for invitations  |
     |                                      |<---------------------------------------|
     |                                      |                                        |
     |                                      | send campaign brief                    |
     |                                      |--------------------------------------->|
     |                                      |                   generate content (AI) |
     |                                      |                   post via Playwright   |
     |                                      |                   scrape metrics        |
     |                                      |<---------------------------------------|
     |                                      |                   submit metrics        |
     | view stats, metrics                  |                                        |
     |<-------------------------------------|  billing cycle                         |
     |                                      |--------------------------------------->|
     |                                      |                   earnings credited     |
```

## Three Systems

### 1. Amplifier Server (`server/`)

FastAPI + Supabase PostgreSQL (production) / SQLite (local dev). Deployed on Vercel.

- **52 API routes** across 7 routers
- **8 database models** (Company, Campaign, User, Assignment, Post, Metric, Payout, Penalty + InvitationLog)
- **5 services** (matching, billing, campaign_wizard, trust, payments, storage)
- **2 web dashboards** (company, admin) rendered with Jinja2

### 2. User App (`scripts/`)

Local Flask app (port 5222) + background agent. Runs on user's desktop.

- **5-step onboarding** wizard with Playwright browser login
- **Background agent** polling server every 5-15 min
- **Content generator** using Gemini/Mistral/Groq (free tiers)
- **Profile scraper** extracting follower data from 4 platforms
- **Post scheduler** with timezone-aware optimal timing
- **Posting engine** via Playwright with human behavior emulation

### 3. Company Dashboard (`server/app/templates/company/`)

Server-rendered Jinja2 pages. Blue `#2563eb` theme, DM Sans font.

- Campaign wizard (4-step: Basics > Audience > Content > Review)
- Campaign list with stats
- Campaign detail with per-platform breakdown
- Billing page with Stripe top-up
- Settings page

## Data Flow

### Campaign Creation (Company)
1. Company fills wizard (product info, URLs, niches, platforms, budget)
2. Server deep-crawls URLs (BFS, up to 10 pages)
3. Gemini generates detailed campaign brief from all sources
4. Campaign saved with `status=draft` or `status=active`
5. Active campaigns deduct budget from company balance

### Matching (Server)
1. User app polls `GET /api/campaigns/invitations`
2. Server runs `get_matched_campaigns()`:
   - Hard filters: platforms (at least 1), followers, region, engagement, budget, max_users
   - AI scoring: Gemini reads full scraped profile + campaign brief, scores 0-100
   - Fallback: niche-overlap scoring if AI unavailable
3. Top 10 matches become `pending_invitation` assignments (3-day TTL)
4. User accepts/rejects in their dashboard

### Content Generation (User App)
1. Background agent detects accepted campaign needing daily content
2. ContentGenerator calls Gemini/Mistral/Groq with campaign brief + user style
3. Generates platform-native content (different format per platform)
4. Drafts stored in local SQLite `agent_draft` table
5. In semi-auto mode: user reviews/edits before posting
6. In full-auto mode: posts automatically

### Posting (User App)
1. Post scheduler picks optimal time per platform per timezone
2. `post.py` launches Playwright with saved browser profile
3. Human behavior emulation (typing delays, scrolling, feed browsing)
4. Content posted, URL captured
5. Post URL synced to server via `POST /api/posts`

### Metric Scraping (User App)
1. After posting, scraper revisits posts at T+1h, T+6h, T+24h, T+72h
2. Extracts impressions, likes, reposts, comments
3. Metrics synced to server via `POST /api/metrics`
4. Server billing cycle calculates earnings

### Billing (Server)
1. Triggered by metric submission
2. Earnings = `(impressions/1000 * CPM) + (likes * rate) + (reposts * rate)`
3. Platform cut deducted (default 20%)
4. Earnings credited to user balance
5. Campaign budget_remaining decremented
6. Auto-pause at <$1 remaining

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Server API | FastAPI (Python 3.12+) |
| Server DB | Supabase PostgreSQL (prod), SQLite (dev) |
| Server ORM | SQLAlchemy 2.0 async |
| Server Auth | JWT (python-jose) |
| Server Templates | Jinja2 |
| Server Deployment | Vercel serverless |
| User App | Flask (Python) |
| User Local DB | SQLite with WAL |
| Browser Automation | Playwright (Chromium) |
| AI Content Gen | Gemini, Mistral, Groq (free tiers) |
| AI Matching | Gemini (server-side) |
| File Storage | Supabase Storage |
| Payments | Stripe (test mode) |

## Key Design Decisions

- **User-side compute**: AI generation, posting, and scraping happen on user's device. Credentials never leave the device.
- **Pull-based architecture**: User app polls server, server doesn't push to users.
- **Free AI APIs**: Content generation uses free tiers (Gemini 2.5-flash > 2.0-flash > 2.5-flash-lite, then Mistral, then Groq).
- **Persistent browser profiles**: Each platform login is saved to `profiles/{platform}-profile/` and reused for posting + scraping.
- **AI-driven matching**: Gemini reads full scraped profile data and decides fit score (0-100). No hardcoded scoring formula.
