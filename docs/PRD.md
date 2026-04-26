# Amplifier — Product Requirements Document (PRD)

**Version**: 1.0
**Date**: April 2, 2026
**Status**: V1 Built — 15/43 tasks done. Server currently offline (Vercel taken down, migrating to Hostinger KVM VPS — Task #41). 4-phase content agent live (Task #14).

---

## Table of Contents

1. [Product Concept](#1-product-concept)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [Target Users](#4-target-users)
5. [System Architecture](#5-system-architecture)
6. [Feature Specifications](#6-feature-specifications)
   - 6.1 [Amplifier Server (Marketplace)](#61-amplifier-server-marketplace)
   - 6.2 [Company Dashboard](#62-company-dashboard)
   - 6.3 [Admin Dashboard](#63-admin-dashboard)
   - 6.4 [User App (Desktop)](#64-user-app-desktop)
   - 6.5 [Posting Engine](#65-posting-engine)
   - 6.6 [Content Generation](#66-content-generation)
   - 6.7 [Personal Brand Engine](#67-personal-brand-engine)
7. [Data Models](#7-data-models)
8. [API Specification](#8-api-specification)
9. [Monetization & Billing](#9-monetization--billing)
10. [Trust & Safety](#10-trust--safety)
11. [Technical Constraints](#11-technical-constraints)
12. [Implementation Status](#12-implementation-status)
13. [Future Roadmap](#13-future-roadmap)

---

## 1. Product Concept

### What is Amplifier?

Amplifier is a **two-sided marketplace** that connects companies who want social media exposure with everyday people who want to earn money by posting about products they use.

**For companies:** Create a campaign describing your product. Amplifier's AI matches you with relevant creators, generates authentic content, handles posting across 6 platforms, tracks engagement metrics, and bills you only for real performance (impressions, likes, shares, clicks).

**For users (Amplifiers):** Accept campaign invitations matched to your niche. AI generates platform-native content for you. Review and approve (or let it auto-post). Earn money from your posts' engagement. Cash out when you hit $10.

**The key insight:** Most people on social media aren't influencers — they're normal people with 200-2000 followers. But collectively, thousands of normal people generate massive reach at a fraction of influencer rates. Amplifier turns this long tail into a distribution channel.

### Design Principles

1. **User-side compute.** All AI content generation, browser automation, and credential handling happen on the user's device. The server never sees passwords or runs browsers. This eliminates platform ban risk at scale and keeps user credentials private.

2. **AI-native everything.** Campaign briefs are AI-generated from company URLs. Content is AI-generated per platform. Matching uses AI scoring of user profiles against campaign briefs. The human is in the loop for quality control, not for grunt work.

3. **Performance-based billing.** Companies pay for real engagement (impressions, likes, shares, clicks), not for posts. This aligns incentives — users want high-engagement content, companies want ROI, Amplifier wants both.

4. **Platform-native content.** A tweet is not a LinkedIn post is not a Reddit thread. Every piece of content is generated specifically for the platform it will appear on, with the right tone, length, format, and culture.

5. **Human emulation.** Browser automation uses persistent profiles, character-by-character typing with random delays, feed browsing before/after posting, and randomized behavior to avoid platform detection.

### How It's Different

| Traditional Influencer Marketing | Amplifier |
|---|---|
| Pay upfront per post | Pay per engagement (performance-based) |
| Negotiate with each influencer | AI matches + generates + posts automatically |
| Need 10K+ followers to qualify | Anyone with a social media account can earn |
| Content created by influencer (variable quality) | AI-generated, platform-native, brand-guided content |
| Manual tracking via screenshots | Automated metric scraping + billing |
| Expensive ($500-$50K per influencer) | Micro-earnings across thousands of users ($0.50-$50 per user per campaign) |

---

## 2. Problem Statement

### For Companies

Social media marketing is broken for small-to-mid companies:
- **Influencer marketing is expensive.** A single Instagram post from a mid-tier influencer costs $500-$5,000. Most small businesses can't afford it.
- **Reach is concentrated.** 1% of users generate 90% of content. Companies compete for the same small pool of creators.
- **ROI is opaque.** You pay upfront and hope for results. No performance guarantee.
- **Content is inconsistent.** Each influencer interprets the brief differently. Quality varies wildly.

### For Users

Normal people can't monetize their social media:
- **Platform monetization has high bars.** YouTube needs 1,000 subscribers. TikTok Creator Fund needs 10,000 followers. Most people will never qualify.
- **Affiliate marketing is saturated.** Every post looks like an ad. Audiences tune out.
- **No easy way to earn.** People spend hours on social media daily but earn nothing from it.

### The Gap

There's a massive, untapped distribution channel: the billions of normal social media users who have 100-2,000 followers each. If you could coordinate them to post authentic, platform-native content about products they'd actually use, you'd have:
- **Massive reach** at low cost (1,000 users × 500 followers = 500K potential impressions)
- **Authentic content** (real people posting on their real profiles)
- **Performance alignment** (pay only for engagement that actually happens)

Amplifier fills this gap.

---

## 3. Solution Overview

### Three Connected Systems

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AMPLIFIER SERVER                            │
│                  (FastAPI + Supabase PostgreSQL)                    │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Campaign  │  │ AI       │  │ Billing  │  │ Trust &  │          │
│  │ CRUD     │  │ Matching │  │ Engine   │  │ Fraud    │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Company  │  │ Admin    │  │ JWT Auth │  │ Stripe   │          │
│  │ Dashboard│  │ Dashboard│  │          │  │ Payments │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
│                                                                     │
│  Deployed: Vercel + Supabase (US East)                             │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ REST API (JWT auth)
                       │
┌──────────────────────┴──────────────────────────────────────────────┐
│                     AMPLIFIER USER APP                              │
│                    (User's Desktop — Windows)                       │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Flask    │  │ Background│  │ Content  │  │ Metric   │          │
│  │ Dashboard│  │ Agent    │  │ Generator│  │ Scraper  │          │
│  │ (5222)   │  │ (60s loop)│ │ (AI APIs)│  │ (tiered) │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Local    │  │ Profile  │  │ Session  │  │ Posting  │          │
│  │ SQLite   │  │ Scraper  │  │ Health   │  │ Engine   │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
│                                                                     │
│  All AI, posting, and credential handling stays on user's device   │
└─────────────────────────────────────────────────────────────────────┘
```

### Core Workflow

1. **Company creates campaign** → Sets product, brief, budget, payout rates, targeting
2. **AI matches users** → Gemini scores user profiles against campaign brief (hard filters + AI relevance scoring)
3. **Users get invitations** → 3-day TTL, max 3 active campaigns per user
4. **User accepts** → AI generates platform-native content for each connected platform
5. **User reviews** → Semi-auto: approve/edit/reject. Full-auto: auto-post.
6. **Posting engine fires** → Playwright automation with human emulation, posts to LinkedIn/Facebook/Reddit (X disabled 2026-04-14)
7. **Metrics scraped** → At T+1h, T+6h, T+24h, T+72h via APIs (X, Reddit) or browser scraping (LinkedIn, Facebook)
8. **Billing runs** → Incremental billing on every metric submission. User earns, company budget deducted, Amplifier takes 20%.
9. **User cashes out** → $10 minimum, Stripe Connect payout

---

## 4. Target Users

### Companies (Demand Side)

| Segment | Description | What They Need |
|---|---|---|
| Small businesses | Local shops, SaaS startups, D2C brands | Affordable reach (<$500/campaign), easy setup, measurable ROI |
| Marketing agencies | Managing multiple brands | White-label campaigns, CSV exports, multi-campaign management |
| E-commerce | Product launches, seasonal promotions | Visual content, multi-platform, quick turnaround |
| Tech companies | Developer tools, B2B SaaS | LinkedIn-heavy distribution, niche targeting |

### Users / Amplifiers (Supply Side)

| Segment | Description | Motivation |
|---|---|---|
| Working professionals | 500-2K followers on LinkedIn/X | Side income, low effort (semi-auto mode) |
| Students | Active on X, Reddit, TikTok | Pocket money, build social media skills |
| Stay-at-home parents | Active on Facebook, Instagram | Flexible income while managing home |
| Micro-influencers | 1K-10K followers, niche expertise | Additional income stream beyond sponsorships |
| Trading/finance community | Active on X, Reddit, LinkedIn | Earn while sharing market insights |

### Anti-Users (Who This Is NOT For)

- Mega-influencers (100K+ followers) — too expensive for the model, better served by traditional deals
- Bot networks — trust scoring + fraud detection + human emulation requirements filter these out
- Companies wanting guaranteed viral content — this is performance-based, not guaranteed

---

## 5. System Architecture

### Technology Stack

| Component | Technology | Why |
|---|---|---|
| **Server** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) | Fast async API, modern Python ecosystem |
| **Production DB** | Supabase PostgreSQL (US East) | Managed PostgreSQL, connection pooling via pgbouncer |
| **Local Dev DB** | SQLite | Zero-config local development |
| **Auth** | JWT (24h expiry, HS256) | Stateless, works with desktop app |
| **Server Hosting** | Vercel (serverless Python) | Free tier, auto-scaling, global CDN |
| **Company/Admin UI** | Jinja2 server-rendered templates | No frontend build step, SEO-friendly, fast iteration |
| **User App** | Flask (port 5222) + Playwright + Local SQLite | Desktop app, local compute, persistent browser profiles |
| **Content Gen** | Gemini 2.5 Flash → Mistral Small → Groq Llama 3.3 | Free-tier AI APIs with fallback chain |
| **Image Gen** | Gemini → Cloudflare Workers AI → Together AI → Pollinations → PIL | Free-tier image generation with fallback chain via ImageManager |
| **Browser Automation** | Playwright (Chromium) | Stealth mode, persistent profiles, multi-platform |
| **Payments** | Stripe Checkout (company top-ups) + Stripe Connect Express (user payouts) | Industry standard, handles compliance |
| **Scheduling** | Windows Task Scheduler + async background agent | Reliable, runs headless |

### Data Flow

```
Company creates campaign
    ↓ POST /api/company/campaigns
Server stores in PostgreSQL
    ↓ Active campaigns matched to users
AI Matching runs (Gemini reads scraped profiles)
    ↓ CampaignAssignment created (pending_invitation)
User App polls (GET /api/campaigns/invitations)
    ↓ User sees invitation in dashboard
User accepts (POST /api/campaigns/invitations/{id}/accept)
    ↓ Assignment status → accepted
Background agent triggers content gen
    ↓ Gemini/Mistral/Groq generates platform-native content
Drafts stored in local SQLite (agent_draft table)
    ↓ Semi-auto: user reviews in dashboard. Full-auto: auto-approved.
Post scheduler calculates optimal time
    ↓ post_schedule table entry (queued)
Background agent executes at scheduled time
    ↓ Playwright posts to platform with human emulation
Post URL captured
    ↓ POST /api/metrics/posts (batch report)
Metric scraper runs at T+1h, T+6h, T+24h, T+72h
    ↓ POST /api/metrics/metrics (batch submit)
Billing engine runs (incremental, on each metric submit)
    ↓ User earnings credited, campaign budget deducted, 20% platform cut
User requests payout at $10+ balance
    ↓ Stripe Connect transfer
```

### Deployment Topology

```
Internet
    │
    ├── Vercel (serverless) ─── FastAPI app
    │       │
    │       └── Supabase PostgreSQL (aws-1-us-east-1)
    │               Connection: transaction pooler (port 6543)
    │               Config: NullPool + prepared_statement_cache_size=0
    │
    ├── Company browser → Company Dashboard (server-rendered Jinja2)
    │
    ├── Admin browser → Admin Dashboard (server-rendered Jinja2)
    │
    └── User's Windows Desktop
            │
            ├── Flask Dashboard (localhost:5222)
            ├── Background Agent (async 60s loop)
            ├── Playwright (persistent browser profiles per platform)
            ├── Local SQLite (data/local.db)
            └── AI API calls (Gemini, Mistral, Groq — keys stored locally)
```

---

## 6. Feature Specifications

### 6.1 Amplifier Server (Marketplace)

The server is a FastAPI application deployed to Vercel with Supabase PostgreSQL. It exposes ~90 routes total (27 JSON API + 36 admin dashboard + ~21 company dashboard + 2 system + 2 health) and serves two server-rendered web dashboards.

#### Authentication

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register` | POST | User registration (email, password) → JWT token |
| `/api/auth/login` | POST | User login → JWT token |
| `/api/auth/company/register` | POST | Company registration (name, email, password) → JWT token |
| `/api/auth/company/login` | POST | Company login → JWT token |

- JWT tokens expire in 24 hours (1440 minutes)
- Algorithm: HS256
- Passwords hashed with bcrypt (passlib)
- Company and user auth are separate namespaces

#### Campaign Management (Company)

| Endpoint | Method | Description |
|---|---|---|
| `/api/company/campaigns` | POST | Create campaign (draft status, no budget deduction) |
| `/api/company/campaigns` | GET | List all company campaigns with stats |
| `/api/company/campaigns/{id}` | GET | Campaign detail with per-user invitation status |
| `/api/company/campaigns/{id}` | PATCH | Edit campaign or change status (draft→active deducts budget) |
| `/api/company/campaigns/{id}` | DELETE | Delete draft campaign (refunds budget) |
| `/api/company/campaigns/{id}/budget-topup` | POST | Add funds to active campaign |
| `/api/company/campaigns/{id}/clone` | POST | Duplicate campaign as new draft |
| `/api/company/campaigns/{id}/export` | GET | Export CSV report (users, posts, metrics, earnings) |
| `/api/company/campaigns/ai-wizard` | POST | AI generates campaign brief from product URLs |
| `/api/company/campaigns/reach-estimate` | POST | Estimate reach for targeting criteria |
| `/api/company/campaigns/{id}/reach-estimate` | GET | Reach estimate for existing campaign |

**Campaign Status Lifecycle:**
```
draft → active → paused → active (resume)
                → completed (budget exhausted or manually)
                → cancelled
```

**Campaign Creation Fields:**
- `title` — Campaign name
- `brief` — Detailed description of product and what to communicate
- `content_guidance` — Tone, must-include phrases, must-avoid phrases, style guidelines
- `assets` — JSON: `{image_urls, links, hashtags, brand_guidelines}`
- `company_urls` — Company website URLs (used by AI wizard for scraping)
- `budget_total` — Total budget in USD (minimum $50)
- `payout_rules` — `{rate_per_1k_impressions, rate_per_like, rate_per_repost, rate_per_click}`
- `targeting` — `{min_followers: {x: 100, linkedin: 50}, niche_tags, required_platforms, target_regions, min_engagement}`
- `penalty_rules` — `{post_deleted_24h: 5.00, off_brief: 2.00, fake_metrics: 50.00}`
- `max_users` — Cap on total accepted users
- `start_date`, `end_date` — Campaign duration
- `budget_exhaustion_action` — `auto_pause` or `auto_complete`

**AI Campaign Wizard:**
1. Company provides: product description, goal, URLs, target niches, regions, platforms, budget range
2. Server deep-crawls company URLs (BFS, up to 10 pages, 2 hops)
3. Gemini generates: enriched title, detailed brief, content guidance, suggested payout rates, targeting
4. Returns draft JSON for company review (does NOT create campaign)
5. Company reviews, edits, then calls POST /campaigns to create

#### Campaign Matching (AI-Driven)

**Hard Filters (all must pass):**
1. Campaign is active with remaining budget
2. User not already invited to this campaign
3. Campaign `accepted_count` < `max_users`
4. User has at least 1 required platform connected
5. User meets minimum follower count per platform
6. User meets minimum engagement rate
7. User's audience region matches campaign target regions
8. User is below their tier's active campaign limit (Seedling: 3, Grower: 10, Amplifier: unlimited)
9. User status is not suspended/banned

**AI Scoring (Gemini):**
- Reads user's full scraped profile data (bio, recent posts with engagement metrics, follower/following counts, extended platform fields)
- Reads campaign brief, content guidance, targeting criteria
- Weighted scoring across 4 criteria (0-100 total):
  - Topic relevance: 40% — do their posts/bio match the campaign topic? Niche depth rewarded.
  - Audience fit: 25% — would their followers be interested? Judged per required platform, not averaged.
  - Authenticity fit: 20% — would this person promoting this product feel natural?
  - Content quality: 15% — writing quality, engagement relative to follower count, originality.
- Brand safety filter: controversial/offensive content → score capped 20-40 regardless of relevance
- Self-selected niches weighted equally to AI-detected niches for topic relevance
- Minimum score threshold: 40 (campaigns scoring below 40 are not invited)
- Results cached 24 hours per (campaign, user) pair
- On AI failure: falls back to niche-overlap scoring (each overlapping niche = +25 points, base 50 if no niche targeting, minimum 10)

**Invitation Flow:**
1. User polls GET `/api/campaigns/mine` → triggers matching if < 3 active campaigns
2. New matches create CampaignAssignment with `status=pending_invitation`, `expires_at=now+3days`
3. User sees invitations in dashboard with campaign details, payout rates, required platforms
4. User accepts (max 3 active) or rejects
5. Stale invitations auto-expire on next fetch

#### User Profile & Earnings

| Endpoint | Method | Description |
|---|---|---|
| `/api/users/me` | GET | Get authenticated user profile |
| `/api/users/me` | PATCH | Update profile (platforms, followers, niches, region, mode, scraped_profiles) |
| `/api/users/me/earnings` | GET | Earnings breakdown: total, balance, pending, per-campaign, per-platform, payout history |
| `/api/users/me/payout` | POST | Request withdrawal ($10 minimum) |

#### Post & Metric Reporting

| Endpoint | Method | Description |
|---|---|---|
| `/api/metrics/posts` | POST | Batch register posted URLs (platform, URL, content hash, timestamp) |
| `/api/metrics/metrics` | POST | Batch submit metrics (impressions, likes, reposts, comments, clicks) — triggers billing |

#### Admin API

| Endpoint | Method | Description |
|---|---|---|
| `/api/admin/users` | GET | List users (filterable by status) |
| `/api/admin/users/{id}/suspend` | POST | Suspend user |
| `/api/admin/users/{id}/unsuspend` | POST | Unsuspend user |
| `/api/admin/stats` | GET | System stats (user counts, campaign counts, post count, total payouts) |
| `/api/admin/flagged-campaigns` | GET | Campaigns flagged for review |

### 6.2 Company Dashboard

Server-rendered Jinja2 templates. Blue theme (#2563eb), DM Sans font, gradient stat cards, SVG Heroicons navigation.

**Pages:**

1. **Login/Register** (`/company/login`) — Email + password form, toggle between login and register
2. **Dashboard** (`/company/`) — Overview with campaign KPIs, budget usage, ROI, alerts, recent campaigns
3. **Campaigns List** (`/company/campaigns`) — Table of all campaigns with status badge, budget (remaining/total), user count, post count, impressions, engagement, earnings. Search, status filter, sort.
4. **Create Campaign** (`/company/campaigns/create`) — Multi-step form OR AI wizard:
   - **Step 1 (Basics):** Product name, description, goal, company URLs
   - **Step 2 (Audience):** Target niches, regions, required platforms, min followers, min engagement
   - **Step 3 (Content):** Content guidance, must-include, must-avoid, assets (images, links, hashtags)
   - **Step 4 (Budget):** Budget amount, payout rates, penalty rules, max users, start/end dates
   - **AI Wizard:** Input product URL → AI generates complete brief + targeting + rates
5. **Campaign Detail** (`/company/campaigns/{id}`) — Stat cards (budget, users, posts, impressions, engagement), per-platform breakdown, creator table (user, platform, posts, impressions, earned), invitation funnel (sent/accepted/rejected/expired), budget management (top-up, pause, resume)
6. **Billing** (`/company/billing`) — Company balance, budget allocations, Stripe Checkout for top-ups (test mode: manual balance credit)
7. **Influencers** (`/company/influencers`) — Cross-campaign influencer performance: all users assigned to company campaigns with engagement metrics
8. **Stats** (`/company/stats`) — Campaign performance aggregates, platform breakdown, monthly spend trend
9. **Settings** (`/company/settings`) — Company name, email update

### 6.3 Admin Dashboard

Server-rendered, password-protected (cookie auth).

**Pages:**

1. **Login** (`/admin/login`) — Password-only form
2. **Overview** (`/admin/`) — Stat cards (total users, active users, total campaigns, active campaigns, total posts, platform revenue), recent activity, system alerts
3. **Users** (`/admin/users`) — Paginated user table with search, status filter, sort. Trust score, mode, platform count, total earned, status. Actions: suspend/unsuspend/ban, adjust trust score.
4. **User Detail** (`/admin/users/{id}`) — Individual user with assignments, posts, payouts, penalties history
5. **Companies** (`/admin/companies`) — Paginated company list with search, status filter, sort. Actions: add/deduct funds, suspend/unsuspend.
6. **Company Detail** (`/admin/companies/{id}`) — Individual company with campaigns and financial summary
7. **Campaigns** (`/admin/campaigns`) — Paginated campaign table with search, status filter, sort. Actions: pause/resume/cancel.
8. **Campaign Detail** (`/admin/campaigns/{id}`) — Campaign assignments, posts with metrics
9. **Financial** (`/admin/financial`) — Payout dashboard with pagination and status filters. Manual billing cycle trigger, manual payout trigger.
10. **Fraud Detection** (`/admin/fraud`) — Penalties list with summary stats (appeals, low-trust users), manual fraud check trigger, appeal approve/deny actions
11. **Analytics** (`/admin/analytics`) — Per-platform post stats, engagement metrics, top performers
12. **Review Queue** (`/admin/review-queue`) — Flagged campaigns (content screening), approve/reject with refund
13. **Audit Log** (`/admin/audit-log`) — Paginated admin action history with action/target type filters
14. **Settings** (`/admin/settings`) — System config display (platform_cut, payout threshold, etc.)

### 6.4 User App (Desktop)

Flask web app (localhost:5222) + background agent running on user's Windows desktop.

#### Onboarding (5 Steps)

**Step 1 — API Keys:**
- User creates free API keys: Gemini (required), Mistral (optional), Groq (optional)
- Step-by-step instructions with direct signup links for each provider
- Test button validates each key with a real API call
- At least 1 key required to proceed
- Keys stored locally in SQLite settings table, NEVER sent to server

**Step 2 — Connect Platforms:**
- Cards for LinkedIn, Facebook, Reddit (enabled); X, Instagram, TikTok (disabled)
- "Connect" button launches Playwright browser with persistent profile
- User logs in manually, closes browser when done
- Connection verified by checking for auth indicators (compose button, profile link, etc.)

**Step 3 — Profile Scraping (3-tier pipeline):**
- Auto-runs after platform connection
- Tier 1 (text): Extracts all visible page text, sends to AiManager for structured extraction
- Tier 2 (CSS selectors): Supplements with platform-specific CSS queries for follower counts, posts, etc.
- Tier 3 (Gemini Vision): Screenshot + vision model if key fields still missing after Tier 1/2
- Per-platform deep extraction: LinkedIn experience/education/featured/honors/interests, Facebook About sub-tabs/Reels/More, Reddit karma/age/subreddits, private profile handling
- AI niche detection from post content (5 niches from 21 categories)
- Real-time polling (3-second intervals) shows scraping progress in UI
- Data stored locally + synced to server

**Step 4 — Niche & Region:**
- 21 niche options: finance, trading, investing, crypto, technology, ai, business, marketing, lifestyle, education, health, fitness, food, travel, entertainment, gaming, sports, fashion, beauty, parenting, politics
- AI-detected niches shown as suggestions (user manually selects)
- Region selection: US, UK, India, EU, Global

**Step 5 — Operating Mode:**
- **Semi-auto (default):** AI generates daily content. User reviews, edits, approves before posting.
- **Full-auto:** AI generates and posts automatically. No human review step.

#### Dashboard

- **Stats bar:** Active campaigns, pending invitations, posts this month, total earned
- **Platform health:** Green/red indicators for each connected platform's session status
- **Campaign cards:** Status, brief preview, payout rates, approve/reject drafts

#### Campaign Tabs

1. **Campaigns** — List of accepted campaigns with status, generated drafts, approve/reject buttons
2. **Posts** — History of all posted content with URLs, platform, timestamp, status
3. **Earnings** — Total earned, current balance, per-campaign breakdown, payout history, request withdrawal button
4. **Settings** — Mode toggle, region, API key management, session health status
5. **Onboarding** — Re-run onboarding steps if needed

#### Background Agent

Async event loop running continuously with staggered task intervals:

| Task | Interval | Description |
|---|---|---|
| **Execute Due Posts** | 60s | Check post_schedule for queued posts, execute via Playwright |
| **Campaign Polling** | 10 min | GET /api/campaigns/invitations + active campaigns, upsert to local DB |
| **Content Generation** | 2 min check | Generate daily drafts for accepted campaigns (if not yet generated today) |
| **Metric Scraping** | 60s | Revisit posted URLs at T+1h, T+6h, T+24h, T+72h to scrape engagement |
| **Session Health** | 30 min | Verify platform browser sessions are still logged in |
| **Profile Refresh** | 7 days | Re-scrape all connected platform profiles |

**Desktop Notifications:** New campaign invitations, posts published, post failures, session expiry, profile refreshed.

### 6.5 Posting Engine

Multi-platform Playwright automation with human behavior emulation.

#### Supported Platforms

| Platform | Status | Post Types | Key Technique |
|---|---|---|---|
| **X (Twitter)** | **DISABLED** (2026-04-14) | Text, Image+Text, Image-only | Disabled after 2 account blocks by anti-bot detection. Re-enable only with X API v2 or stealth browser. Code preserved. |
| **LinkedIn** | Enabled | Text, Image+Text, Image-only | `page.locator()` pierces shadow DOM. ClipboardEvent paste for images. |
| **Facebook** | Enabled | Text, Image+Text, Image-only | ClipboardEvent paste for images. Profile URL as permalink fallback. |
| **Reddit** | Enabled | Title+Body, Image+Title | Posts to user profile (`/user/{username}/submit`). Lexical editor via JS focus. |
| **Instagram** | Disabled | Image+Caption | Disabled in `config/platforms.json`. Multi-step dialog (Create→Post→Upload→Next→Next→Caption→Share). Code preserved. |
| **TikTok** | Disabled | Video+Caption | Disabled in `config/platforms.json`. Draft.js editor. VPN required in some regions. Code preserved. |

#### Human Emulation

| Behavior | Implementation | Parameters |
|---|---|---|
| **Typing** | Character-by-character via keyboard events | 30-80ms per char, 5% chance of 300-800ms thinking pause |
| **Between-action delays** | Random sleep between UI interactions | 500-2000ms |
| **Feed browsing** | Scroll through home feed before/after posting | 1-3 seconds, 2-4 posts viewed |
| **Anti-detection flags** | `--disable-blink-features=AutomationControlled` | On all browser launches |
| **Persistent profiles** | Stored in `profiles/{platform}-profile/` | Reuse sessions across runs |

#### Post Scheduling

Region-aware scheduling with platform-specific peak engagement windows:

| Platform | Peak Windows (local time) |
|---|---|
| X | 8-10am, 12-1pm, 5-7pm |
| LinkedIn | 8-10am, 12-1pm |
| Facebook | 12-2pm, 7-9pm |
| Reddit | 8-11am, 6-9pm |

**Rules:**
- Minimum 30-second spacing between any two posts
- Same platform, different campaign: 60-second spacing
- Daily post cap: `min(active_campaigns × 4, 20)` (scales down with more campaigns)
- 1-15 minute random jitter per slot to avoid patterns
- 3-day lookahead for available slots

#### URL Capture

After posting, the engine captures the post's permalink:
- **X:** Navigate to profile, find latest tweet URL
- **LinkedIn:** Check "View post" dialog, fallback to activity feed
- **Facebook:** Profile URL fallback (React UI doesn't expose permalinks easily)
- **Reddit:** Redirect URL after submission contains `?created=t3_XXXXX`

URLs are reported to the server via POST `/api/metrics/posts` for metric scraping.

### 6.6 Content Generation

AI-powered, platform-native content generation with provider fallback chain.

#### Text Generation

**Provider Chain:** Gemini 2.5 Flash → Gemini 2.0 Flash → Gemini 2.5 Flash Lite → Mistral Small → Groq Llama 3.3 70B

**Research Phase (optional):**
1. Extract company URLs from campaign assets
2. Deep scrape via webcrawler (up to 10 pages, 2 hops)
3. Build ~3000 character research brief injected into content prompt
4. Falls back transparently if URLs unavailable or scrape fails

**Content Prompt Structure:**
- Campaign brief, content guidance, must-include/must-avoid phrases
- Platform-specific format rules:
  - **X:** Max 280 chars. Punchy hook + key benefit + 1-3 hashtags.
  - **LinkedIn:** 500-1500 chars. Story format, aggressive line breaks, personal experience, question at end. 3-5 hashtags.
  - **Facebook:** 200-800 chars. Conversational, like telling friends. Ask question for comments. 0-2 hashtags.
  - **Reddit:** JSON `{title, body}`. Title 60-120 chars (non-clickbait). Body 500-1500 chars (genuine, specific pros AND cons, no hashtags/emojis).
- UGC tone (authentic, personal, not corporate)
- Hook patterns: problem-solution, surprise, social proof, curiosity gap, contrarian
- Anti-AI language guards (banned words: "game-changer", "unlock your potential", "leverage", etc.)
- Anti-repetition: previous post hooks injected to force fresh content
- Daily variation via day number tracking

**Output Format:**
```json
{
  "x": "tweet text",
  "linkedin": "post text",
  "facebook": "post text",
  "reddit": {"title": "...", "body": "..."},
  "image_prompt": "vivid description for image generation"
}
```

#### Image Generation

**Three generation modes via ImageManager with automatic provider fallback:**
- **img2img** (when campaign has product photos): transforms a product photo into a UGC scene using `ImageManager.transform()`
- **txt2img** (no product photo): generates from AI-enhanced UGC prompt using `ImageManager.generate()`

**Provider Chain (Gemini → Cloudflare → Together → Pollinations → PIL):**
1. Gemini Flash Image (~500 free/day, supports both txt2img and img2img)
2. Cloudflare Workers AI (FLUX.1-schnell)
3. Together AI (FLUX.1-schnell free)
4. Pollinations AI (turbo)
5. PIL branded template (dark background + white text) — last resort

All free-tier APIs. Rate limiting handled with automatic fallback to next provider on 429.

**UGC Post-Processing Pipeline (`scripts/ai/image_postprocess.py`):** Applied automatically after every successful generation — desaturation (13%), warm/cool color cast, film grain (Gaussian sigma=8), vignetting (25%), JPEG at quality 80, EXIF injection (iPhone 15 Pro, Galaxy S24, Pixel 8 Pro). Requires `numpy` and `piexif`.

**Campaign Image Pipeline (`scripts/background_agent.py`):** Downloads ALL product images from `campaign.assets.image_urls` to `data/product_images/{campaign_id}/`. `_pick_daily_image()` rotates through them by day number so each day's post uses a different product photo.

### 6.7 Personal Brand Engine

Separate from the campaign marketplace — a personal social media automation pipeline for the project creator's own brand.

**Three-Phase Pipeline:**
1. **Generate** — PowerShell script invokes Claude CLI to write draft JSON files. Per-slot generation (6 daily slots), content pillar rotation, CTA rotation based on account age, legal disclaimers.
2. **Review** — Flask dashboard (localhost:5111) with platform-by-platform previews, character counts, edit capability, approve/reject buttons.
3. **Post** — Same Playwright posting engine used by the campaign system.

**Content Strategy (built into generation prompt):**
- 5 content pillars: "Stop Losing Money", "Make Money While You Sleep", "The Market Cheat Code", "Proof Not Promises", "Future-Proof Your Income"
- Emotion-first principle: every post leads with an emotional hook (greed, fear, security, freedom, FOMO)
- Value-first principle: every post delivers actionable value a beginner can implement today
- Platform-native formatting per platform
- CTA rotation: Month 1 = 100% value. Month 2+ = 80% value / 15% soft CTA / 5% direct CTA.

**Scheduling (US-aligned from India):**

| Slot | IST Time | EST Time | Purpose |
|---|---|---|---|
| 1 | 18:30 | 8:00 AM | Morning scroll — East Coast waking up |
| 2 | 20:30 | 10:00 AM | Mid-morning — peak LinkedIn + X |
| 3 | 23:30 | 1:00 PM | Lunch break — high TikTok/Instagram |
| 4 | 01:30 | 3:00 PM | Afternoon — post-market discussion |
| 5 | 04:30 | 6:00 PM | Evening scroll — highest TikTok engagement |
| 6 | 06:30 | 8:00 PM | Night wind-down — strong Instagram/Facebook |

---

## 7. Data Models

### Server Database (Supabase PostgreSQL)

#### Company
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| name | varchar(255) | Company display name |
| email | varchar(255), unique | Login email |
| password_hash | varchar(255) | bcrypt hash |
| balance | decimal(12,2) | Available funds for campaigns (legacy float) |
| balance_cents | int | Available funds in integer cents |
| created_at, updated_at | timestamptz | Server defaults |

#### Campaign
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| company_id | int (FK→Company) | Owning company |
| title | varchar(255) | Campaign name |
| brief | text | Detailed product description |
| status | varchar(20) | draft, active, paused, completed, cancelled |
| screening_status | varchar(20) | pending, approved, flagged, rejected |
| assets | jsonb | `{image_urls, links, hashtags, brand_guidelines}` |
| content_guidance | text | Tone, must-include, must-avoid |
| company_urls | jsonb[] | Company website URLs |
| budget_total | decimal(12,2) | Total budget |
| budget_remaining | decimal(12,2) | Remaining budget |
| budget_exhaustion_action | varchar(20) | auto_pause or auto_complete |
| budget_alert_sent | boolean | True when <20% remaining |
| payout_rules | jsonb | `{rate_per_1k_impressions, rate_per_like, rate_per_repost, rate_per_click}` |
| targeting | jsonb | `{min_followers, niche_tags, required_platforms, target_regions, min_engagement}` |
| penalty_rules | jsonb | `{post_deleted_24h, off_brief, fake_metrics}` |
| max_users | int | Cap on accepted users |
| invitation_count | int | Total invitations sent |
| accepted_count | int | Total accepted |
| rejected_count | int | Total rejected |
| expired_count | int | Total expired |
| campaign_version | int | Incremented on content edits |
| ai_generated_brief | boolean | True if AI-assisted |
| start_date, end_date | timestamptz | Campaign duration |
| created_at, updated_at | timestamptz | Server defaults |

#### User
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| email | varchar(255), unique | Login email |
| password_hash | varchar(255) | bcrypt hash |
| device_fingerprint | varchar(255) | Device identification |
| status | varchar(20) | active, suspended, banned |
| platforms | jsonb | `{x: {username, connected}, linkedin: {...}}` |
| follower_counts | jsonb | `{x: 1500, linkedin: 500}` |
| niche_tags | jsonb[] | `["finance", "tech"]` |
| audience_region | varchar(50) | us, uk, india, eu, global |
| trust_score | int | 0-100, starts at 50 |
| mode | varchar(20) | full_auto, semi_auto |
| tier | varchar(20) | seedling (default) / grower (20+ posts) / amplifier (100+ posts + trust≥80) |
| successful_post_count | int | Lifetime successful posts (used for tier promotion) |
| scraped_profiles | jsonb | Full scraped data per platform |
| ai_detected_niches | jsonb[] | AI-classified from post content |
| last_scraped_at | timestamptz | Last profile scrape |
| earnings_balance | decimal(12,2) | Available to withdraw (legacy float) |
| earnings_balance_cents | int | Available balance in integer cents |
| total_earned | decimal(12,2) | Lifetime total (legacy float) |
| total_earned_cents | int | Lifetime total in integer cents |
| created_at, updated_at | timestamptz | Server defaults |

#### CampaignAssignment
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| campaign_id | int (FK→Campaign) | |
| user_id | int (FK→User) | |
| status | varchar(30) | pending_invitation, accepted, content_generated, posted, paid, rejected, expired |
| content_mode | varchar(20) | ai_generated, user_customized, repost |
| payout_multiplier | decimal(3,2) | Always 1.0 in v2 |
| invited_at | timestamptz | When invitation was sent |
| responded_at | timestamptz | When user accepted/rejected |
| expires_at | timestamptz | Invitation expiry (3 days) |
| assigned_at, updated_at | timestamptz | Server defaults |

#### Post
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| assignment_id | int (FK→Assignment) | |
| platform | varchar(20) | x, linkedin, facebook, reddit, tiktok, instagram |
| post_url | text | Captured permalink |
| content_hash | varchar(64) | SHA256 of content (deduplication) |
| posted_at | timestamptz | When posted |
| status | varchar(20) | live, deleted, flagged |
| created_at | timestamptz | Server default |

#### Metric
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| post_id | int (FK→Post) | |
| impressions | int | View count |
| likes | int | |
| reposts | int | Shares/retweets |
| comments | int | |
| clicks | int | Link clicks (hardcoded 0 — browser limitation) |
| scraped_at | timestamptz | When scraped |
| is_final | boolean | True when post >7 days old |
| created_at | timestamptz | Server default |

#### Payout
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| user_id | int (FK→User) | |
| campaign_id | int (FK→Campaign, nullable) | NULL for aggregate payouts |
| amount | decimal(12,2) | Payout amount (legacy float, kept for backward compat) |
| amount_cents | int | Payout amount in integer cents (v2: eliminates float rounding) |
| period_start, period_end | timestamptz | Billing period |
| status | varchar(20) | pending → available → processing → paid; or pending → voided; processing → failed |
| available_at | timestamptz | When the 7-day earning hold period ends and the user can withdraw |
| breakdown | jsonb | `{metric_id, post_id, platform, impressions, likes, reposts, clicks, platform_cut_pct}` |
| created_at | timestamptz | Server default |

#### Penalty
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| user_id | int (FK→User) | |
| post_id | int (FK→Post, nullable) | |
| reason | varchar(30) | content_removed, off_brief, fake_metrics, platform_violation |
| amount | decimal(12,2) | Deducted from earnings (legacy float) |
| amount_cents | int | Penalty amount in integer cents |
| description | text | Details |
| appealed | boolean | |
| appeal_result | text | |
| created_at | timestamptz | Server default |

#### CampaignInvitationLog
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| campaign_id | int (FK→Campaign) | |
| user_id | int (FK→User) | |
| event | varchar(30) | sent, accepted, rejected, expired, re_invited |
| event_metadata | jsonb | Flexible context |
| created_at | timestamptz | Server default |

#### AuditLog
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| action | varchar(50) | Admin action type (suspend_user, ban_user, adjust_trust, approve_campaign, run_billing, etc.) |
| target_type | varchar(20) | user, company, campaign, payout, penalty, system |
| target_id | int | ID of the affected entity |
| details | jsonb | Action-specific context (old values, new values, reason) |
| admin_ip | varchar(45) | Admin's IP address |
| created_at | timestamptz | Server default |

#### ContentScreeningLog
| Field | Type | Description |
|---|---|---|
| id | int (PK) | Auto-increment |
| campaign_id | int (FK→Campaign, unique) | One screening per campaign |
| flagged | boolean | Whether content was flagged |
| flagged_keywords | jsonb | List of detected flagged terms |
| screening_categories | jsonb | Categories triggered (violence, hate, explicit, financial, health) |
| reviewed_by_admin | boolean | Whether admin has reviewed |
| review_result | varchar(20) | approved, rejected |
| review_notes | text | Admin review comments |
| created_at | timestamptz | Server default |

### Local Database (User's Device — SQLite, 13 tables)

| Table | Purpose |
|---|---|
| `local_campaign` | Mirror of server campaigns with local status tracking, invitation metadata |
| `agent_draft` | AI-generated content per platform per day (approved/rejected/posted flags, quality score, iteration/day number, `image_path` for generated or product image) |
| `post_schedule` | Scheduled post queue (queued → posting → posted → failed). Added: `error_code` (classified error category), `execution_log` (step-by-step trace), `max_retries` (default 3). `classify_error()` maps error messages to codes for structured exponential-backoff retry. |
| `local_post` | Posted content with URLs, sync status to server, content hash for dedup |
| `local_metric` | Scraped engagement per post with reporting status and is_final flag |
| `local_earning` | Per-campaign earnings with status (pending/paid) |
| `scraped_profile` | Per-platform profile data (UNIQUE on platform): followers, bio, engagement rate, posting frequency, extended data (LinkedIn: location, experience, education) |
| `settings` | Key-value config (mode, audience_region, API keys, onboarding_done) |
| `local_notification` | Desktop notification queue with type, read status |
| `agent_research` | Campaign research findings (web scrape results, competitor analysis) |
| `agent_content_insights` | Engagement analytics per platform/pillar for content optimization |

> Note: `agent_user_profile` was dropped 2026-04-26 (Bug #55). The content agent now reads from `scraped_profile` directly via `get_user_profiles()` — single source of truth for per-platform profile data.

---

## 8. API Specification

### Complete Endpoint Reference

**Auth (4 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | None | User registration |
| POST | `/api/auth/login` | None | User login |
| POST | `/api/auth/company/register` | None | Company registration |
| POST | `/api/auth/company/login` | None | Company login |

**Company Campaigns (11 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/company/campaigns` | Company JWT | Create campaign (draft) |
| GET | `/api/company/campaigns` | Company JWT | List campaigns |
| GET | `/api/company/campaigns/{id}` | Company JWT | Campaign detail |
| PATCH | `/api/company/campaigns/{id}` | Company JWT | Update campaign / change status |
| DELETE | `/api/company/campaigns/{id}` | Company JWT | Delete draft (refund) |
| POST | `/api/company/campaigns/{id}/budget-topup` | Company JWT | Add funds |
| POST | `/api/company/campaigns/{id}/clone` | Company JWT | Clone as new draft |
| GET | `/api/company/campaigns/{id}/export` | Company JWT | CSV export |
| POST | `/api/company/campaigns/ai-wizard` | Company JWT | AI campaign generation |
| POST | `/api/company/campaigns/reach-estimate` | Company JWT | Pre-campaign reach estimate |
| GET | `/api/company/campaigns/{id}/reach-estimate` | Company JWT | Existing campaign reach estimate |

**User Campaigns (4 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/campaigns/mine` | User JWT | Poll for matched campaigns (triggers matching) |
| GET | `/api/campaigns/invitations` | User JWT | Pending invitations (auto-expires stale) |
| POST | `/api/campaigns/invitations/{id}/accept` | User JWT | Accept invitation |
| POST | `/api/campaigns/invitations/{id}/reject` | User JWT | Reject invitation |

**Active Campaigns (2 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/campaigns/active` | User JWT | Active assignments with campaign details |
| PATCH | `/api/campaigns/assignments/{id}` | User JWT | Update assignment status |

**User Profile (4 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/users/me` | User JWT | Get profile |
| PATCH | `/api/users/me` | User JWT | Update profile |
| GET | `/api/users/me/earnings` | User JWT | Earnings breakdown |
| POST | `/api/users/me/payout` | User JWT | Request withdrawal ($10 min) |

**Posts & Metrics (2 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/metrics/posts` | User JWT | Batch register posted URLs |
| POST | `/api/metrics/metrics` | User JWT | Batch submit metrics (triggers billing) |

**Admin Dashboard (36 HTML routes via modular routers in `server/app/routers/admin/`):**

Admin routes serve server-rendered Jinja2 pages. Authentication via `admin_token` cookie. All admin actions logged to `AuditLog` table.

| Category | Routes | Key Actions |
|---|---|---|
| Auth | 3 | Login, logout |
| Overview | 1 | Dashboard KPIs |
| Users | 6 | List (paginated, search, filter), detail, suspend, unsuspend, ban, adjust trust |
| Companies | 6 | List (paginated, search, filter), detail, add/deduct funds, suspend, unsuspend |
| Campaigns | 5 | List (paginated, search, filter), detail, pause, resume, cancel |
| Financial | 5 | Payout list, run billing cycle, run payout cycle, run earning promotion, run payout processing |
| Fraud | 4 | Penalty list, run trust check, approve/deny appeals |
| Analytics | 1 | Per-platform stats |
| Review Queue | 3 | List flagged campaigns, approve, reject |
| Audit Log | 1 | Paginated admin action history |
| Settings | 1 | System config display |

**System (2 endpoints):**
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Health check |
| GET | `/api/version` | None | Version + download URL |

---

## 9. Monetization & Billing

### Revenue Model

Amplifier takes a **20% platform cut** on all earnings. Companies pay for engagement; users receive 80% of what's earned.

### Billing Formula

```
raw_earning = (impressions / 1000 × rate_per_1k_impressions)
            + (likes × rate_per_like)
            + (reposts × rate_per_repost)
            + (clicks × rate_per_click)

user_earning = raw_earning × 0.80    (user gets 80%)
platform_cut = raw_earning × 0.20    (Amplifier gets 20%)
company_cost = raw_earning           (full amount from campaign budget)
```

### Default Payout Rates (Customizable Per Campaign)

| Metric | Default Rate | Description |
|---|---|---|
| Impressions | $0.50 per 1,000 | Views/reach |
| Likes | $0.01 each | |
| Reposts/Shares | $0.05 each | |
| Clicks | $0.10 each | Currently hardcoded to 0 (browser limitation) |

### Billing Mechanics

- **Integer cents:** All money math uses integer cents internally to eliminate float rounding errors. Legacy `amount` float fields retained for backward compatibility.
- **Incremental billing:** Runs on every metric submission (not batched). Prevents under-billing.
- **Deduplication:** Tracks billed metric IDs in Payout records via `breakdown.metric_id`. Same metric never billed twice.
- **Budget capping:** Earnings capped to remaining campaign budget. No over-spend.
- **Budget exhaustion:** When remaining < $1, campaign auto-pauses or auto-completes based on `budget_exhaustion_action` setting.
- **Budget alert:** When remaining < 20% of total, `budget_alert_sent` flag set (for notification).
- **Budget top-up:** Companies can add funds anytime. Resets alert if remaining >= 20% of new total. Resumes paused campaigns.
- **Earning hold period:** New earnings stay in `pending` status for 7 days (`EARNING_HOLD_DAYS`). `promote_pending_earnings()` moves them to `available` after the hold. Allows voiding earnings if fraud is detected within the window.
- **Payout auto-processing:** `process_pending_payouts()` in payments.py auto-sends available payouts via Stripe Connect.

### Reputation Tiers

Users progress through three tiers based on successful posts and trust score:

| Tier | Unlock Criteria | Max Campaigns | Spot-Check | Auto-Post | CPM Multiplier |
|---|---|---|---|---|---|
| **Seedling** | Default | 3 | 30% | No | 1x |
| **Grower** | 20 successful posts | 10 | 10% | Yes | 1x |
| **Amplifier** | 100 posts + trust ≥ 80 | Unlimited | 5% | Yes | 2x |

Tier promotion runs automatically in `billing.py` (`_check_tier_promotion()`) on each billing cycle. The matching service enforces campaign limits per tier.

### Money Flow

```
Company adds funds (Stripe Checkout) → company.balance
Company activates campaign → balance -= budget_total → campaign.budget_remaining = budget_total
Users post + metrics scraped → billing calculates earnings
    → user.earnings_balance += earning × 0.80
    → campaign.budget_remaining -= earning (full amount)
    → Amplifier retains 0.20 difference
User requests withdrawal ($10 min) → Payout record (pending)
    → Stripe Connect transfer (stub in v1)
```

### Campaign Budget Rules

- Minimum campaign budget: $50
- Budget deducted from company balance on campaign activation (not creation)
- Draft campaigns are free to create
- Deleting a draft campaign refunds budget to company balance
- Cancelled campaigns do NOT refund remaining budget (admin decision)

---

## 10. Trust & Safety

### Trust Score System

Every user starts at trust score 50 (out of 100). Score adjusts based on events:

| Event | Adjustment | Description |
|---|---|---|
| `post_verified_live_24h` | +1 | Post confirmed live after 24 hours |
| `above_avg_engagement` | +2 | Post engagement above platform average |
| `campaign_completed` | +3 | Successfully completed a campaign |
| `user_customized_content` | +1 | User edited AI-generated content |
| `post_deleted_24h` | -10 | Post deleted within 24 hours |
| `content_flagged` | -15 | Content flagged as off-brief or inappropriate |
| `metrics_anomaly` | -20 | Engagement metrics statistically anomalous |
| `confirmed_fake_metrics` | -50 | Confirmed fake engagement (bot activity) |

Score clamped to 0-100. Score below 10 flags for admin ban review (not auto-ban).

### Fraud Detection

**Post Deletion Detection:**
- Checks posts marked "live" that are older than 24 hours
- Returns suspicious posts for spot-checking (human review needed)

**Metrics Anomaly Detection:**
- Calculates average engagement per user across all posts
- Compares to overall platform average
- Flags users with average engagement > 3× the overall average
- Returns flagged users with ratios for admin review

**Penalty System:**
- Negative trust events create Penalty records
- Penalty amount = abs(trust_adjustment) × $0.50
- Penalties deducted from earnings
- Users can appeal penalties (admin reviews)

### Content Screening

- Campaign screening status: pending → approved / flagged / rejected
- Currently auto-approved (v1)
- Future: AI quality gate scoring 85%+ required before activation

---

## 11. Technical Constraints

| Constraint | Impact | Mitigation |
|---|---|---|
| **Windows-only** | User app requires Windows 10/11 | Windows fonts in image gen, PowerShell generation, Task Scheduler |
| **Manual platform login** | Each platform needs one-time interactive login | `login_setup.py` launches Playwright browser for manual login |
| **Platform selector fragility** | Social media platforms update DOM frequently | Selectors isolated at top of each platform function for easy updates |
| **X account lockout risk** | Playwright automation detected by X | Stealth flags, human emulation, persistent profiles. Future: official API |
| **Reddit blocks headless** | "Network security" error in headless mode | Reddit always runs headed |
| **No click tracking** | Browser scraping can't capture link clicks | clicks hardcoded to 0 in metric scraping |
| **Free-tier AI limits** | Gemini/Mistral/Groq have rate limits | Provider fallback chain, graceful degradation |
| **Vercel cold starts** | Serverless function startup latency | NullPool for DB, lightweight imports |
| **pgbouncer compatibility** | Supabase transaction pooler doesn't support prepared statements | `prepared_statement_cache_size=0` in connection string |
| **No test suite** | Changes verified against real platforms only | Manual testing, screenshot capture, detailed logging |

---

## 12. Implementation Status

**Current progress: 13 of 39 tasks done** (as of 2026-04-17). 15 pending, 11 deferred.

### Batch 1: Money Loop — COMPLETE

| Component | Status | Details |
|---|---|---|
| **Server API** | Done | ~90 routes, 13 models, 7 services |
| **Company Dashboard** | Done | 10 pages, campaign CRUD, AI wizard, billing, influencers, stats, settings |
| **Admin Dashboard** | Done | 14 pages, users, companies, campaigns, financial, fraud, analytics, review queue, audit log, settings |
| **User Onboarding** | Done & Verified | 5-step flow, API keys, platform login, scraping, niche/region, mode |
| **Campaign Polling** | Done & Verified | Invitation flow, 3-day TTL, max 3 active, auto-expire |
| **Content Generation** | Done & Verified | AiManager (Gemini→Mistral→Groq), ImageManager (5-provider fallback: Gemini→Cloudflare→Together→Pollinations→PIL + UGC post-processing). Three image modes: img2img product photo, txt2img, PIL fallback. Daily image rotation. |
| **Content Review** | Done & Verified | Approve/reject/edit/restore/unapprove, Reddit JSON display, auto-reload |
| **Posting Engine** | Done & Verified | JSON script engine (3 active platforms: LinkedIn, Facebook, Reddit). URL capture working. X disabled 2026-04-14 after account lockouts. |
| **Metric Scraping** | Done & Verified | API-first (X, Reddit) + Browser Use + Playwright hybrid (LinkedIn, Facebook). Tiered schedule T+1h/6h/24h/72h. |
| **Billing** | Done & Verified | Integer cents math, earning hold period (7 days), tier CPM multiplier (2x Amplifier), earning promotion, payout auto-processing. E2E verified. |
| **Earnings Display** | Done & Verified | Per-campaign breakdown, balance, payout history in user dashboard and server admin. |
| **Deleted Post Detection** | Done & Verified | Deletion detection in fraud check, trust score penalty, void earnings. |
| **Financial Safety** | Done | AES-256-GCM encryption for API keys (client + server), structured error codes + retry lifecycle in post_schedule |
| **Reputation Tiers** | Done | Seedling/Grower/Amplifier tiers with auto-promotion in billing cycle |
| **Trust/Fraud** | Done | Trust events, deletion detection, anomaly detection |
| **Payments** | Done | Stripe Checkout (company top-ups) + Connect (user payouts, test mode). `process_pending_payouts()` auto-processing. |
| **Deployment** | Done | FastAPI + Supabase (US East). Vercel deployment currently offline (billing issue) — runs locally. |

### Batch 2: AI Brain — In Progress

| Component | Status | Details |
|---|---|---|
| **AI Matching** | Done & Verified | Weighted Gemini scoring (topic 40%, audience 25%, authenticity 20%, quality 15%). Min score 40, brand safety, self-selected niche respect. 30 unit tests + E2E verified. |
| **3-Tier Profile Scraping** | Done & Verified | Tier 1 (page text → AiManager), Tier 2 (CSS selectors), Tier 3 (Gemini Vision). LinkedIn: experience/education/featured/honors/interests. Facebook: About sub-tabs/Reels/More dropdown + display-name-anchored follower_count supplement (Bug #53 fix 2026-04-26). Reddit: private handling, karma/age/subreddits. UAT verified against 3 real profiles. Re-verified 2026-04-26 via /uat-task. |
| **4-Phase Content Agent** | Done & Verified | Task #14 — Research → Strategy → Creation → Review. Verified end-to-end 2026-04-26 via /uat-task 14: 18 ACs PASS including real LinkedIn/Facebook/Reddit posts, autonomous deletion, day-1 vs day-2 diversity. |
| **AI Campaign Quality Gate** | Pending | 85%+ quality score required before activation. Not started. |

### Pending Tasks (#14-#28)

Tasks #14-#28: 4-phase content agent, content formats (threads), free/Pro tiers, automated tests, Stripe live, PyInstaller packaging, Mac support, landing page, DB backup, UI polish tasks, server-side post URL dedup, ToS/privacy policy.

### Deferred Tasks (#29-#39)

Tasks #29-#39 deferred: political campaign support, self-learning content, video generation, FLUX.1 image gen, GDPR export, accessibility, CSV export for users, mobile responsiveness, local lightweight DB, UGC-style content formatter, repost campaign type.

---

## 13. Future Roadmap

### Phase 2: Verification & Polish (Current)

Complete verification of all built features (tasks #27-#50). Fix bugs found during testing. No new features until verification is done.

### Phase 3: Content Quality

- **4-Phase AI Content Agent** (#63) — Research → Strategy → Creation → Review pipeline. Campaign goal drives content strategy. Image intelligence via vision API. Must-include items woven naturally.
- **Platform-Specific Content Preview** (#65) — Show how content will look on each platform before posting.
- **AI Campaign Quality Gate** (#58) — Campaigns must score 85%+ on quality rubric before activation.

### Phase 4: Reliability

- **Official Social Media APIs** (#57) — Replace Playwright scraping with X API, LinkedIn API, Reddit API, Facebook API for profile data and metrics.
- **X Lockout Detection** (#66) — Detect account lockout during posting and notify user to unlock.
- **Metrics Accuracy** (#60) — Cross-validate scraped metrics vs platform analytics dashboards.
- **Session Health Improvements** (#67) — More reliable detection of expired sessions.

### Phase 5: Scale

- **FLUX.1 Image Generation** (#55) — ~$0.30/session via vast.ai GPU rental.
- **Video Generation** (#56) — Seedance 2 or similar for TikTok/Instagram Reels.
- **Self-Learning Content** (#61) — Track performance, learn from high-engagement posts, improve over time.
- **Free & Paid Tiers** (#62) — Limits on active campaigns, content features, posting frequency for free users.

### Phase 6: Distribution

- **Web-based User Dashboard** — Replace local Flask app with hosted web dashboard.
- **Lightweight Desktop Agent** — Tauri app for posting-only (no dashboard). Much smaller than current PyInstaller.
- **Mobile App** — iOS/Android for user campaign management and earnings tracking.

### Phase 7: Automation

- **OpenClaw Multi-Agent Team** — Autonomous AI agents running Amplifier 24/7: CEO agent (strategy), engineering agent (fixes), marketing agent (growth).
- **Webhook Integrations** — Companies receive real-time updates on campaign performance.
- **Public API** — Third-party companies integrate directly without the dashboard.

---

## Appendix A: Configuration Reference

### Server Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | SQLite fallback | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | — | Token signing secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | 1440 | Token TTL |
| `PLATFORM_CUT_PERCENT` | No | 20 | Amplifier's revenue cut |
| `MIN_PAYOUT_THRESHOLD` | No | 10.00 | Minimum withdrawal |
| `GEMINI_API_KEY` | No | — | For AI wizard + matching |
| `STRIPE_SECRET_KEY` | No | — | For Stripe integration |
| `STRIPE_WEBHOOK_SECRET` | No | — | Stripe webhook verification |
| `ADMIN_PASSWORD` | Yes | — | Admin dashboard password |

### User App Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Primary text + image gen |
| `MISTRAL_API_KEY` | No | — | Text gen fallback |
| `GROQ_API_KEY` | No | — | Text gen fallback |
| `CLOUDFLARE_ACCOUNT_ID` | No | — | Image gen (Workers AI) |
| `CLOUDFLARE_API_TOKEN` | No | — | Image gen (Workers AI) |
| `TOGETHER_API_KEY` | No | — | Image gen fallback |
| `X_BEARER_TOKEN` | No | — | X API for metrics |
| `REDDIT_CLIENT_ID` | No | — | Reddit API for metrics |
| `REDDIT_CLIENT_SECRET` | No | — | Reddit API for metrics |
| `CAMPAIGN_SERVER_URL` | No | Production URL | Server endpoint |
| `HEADLESS` | No | true | Browser visibility |
| `POST_INTERVAL_MIN_SEC` | No | 30 | Min wait between posts |
| `POST_INTERVAL_MAX_SEC` | No | 90 | Max wait between posts |

### Platform Configuration (config/platforms.json)

```json
{
  "x": {
    "name": "X (Twitter)",
    "compose_url": "https://x.com/compose/post",
    "home_url": "https://x.com/home",
    "timeout_seconds": 30,
    "enabled": false,
    "note": "DISABLED 2026-04-14 — 2 account blocks by anti-bot detection"
  },
  "linkedin": {
    "name": "LinkedIn",
    "home_url": "https://www.linkedin.com/feed/",
    "timeout_seconds": 30,
    "enabled": true
  },
  "facebook": {
    "name": "Facebook",
    "home_url": "https://www.facebook.com/",
    "timeout_seconds": 30,
    "enabled": true
  },
  "reddit": {
    "name": "Reddit",
    "home_url": "https://www.reddit.com/",
    "subreddits": ["Daytrading", "Forex", "StockMarket", "SwingTrading"],
    "timeout_seconds": 30,
    "enabled": true
  },
  "instagram": {
    "name": "Instagram",
    "home_url": "https://www.instagram.com/",
    "timeout_seconds": 30,
    "enabled": false
  },
  "tiktok": {
    "name": "TikTok",
    "home_url": "https://www.tiktok.com/",
    "upload_url": "https://www.tiktok.com/creator#/upload?scene=creator_center",
    "timeout_seconds": 30,
    "enabled": false,
    "note": "VPN required in some regions"
  }
}
```

---

## Appendix B: Metric Scraping Schedule

| Tier | Timing | Purpose | Billing Impact |
|---|---|---|---|
| 1 | T + 1 hour | Verify post is live | None |
| 2 | T + 6 hours | Early engagement snapshot | Triggers incremental billing |
| 3 | T + 24 hours | Primary metric (most billing here) | Triggers incremental billing |
| 4 | T + 72 hours | Settled engagement | Triggers incremental billing |
| 5+ | Every 24 hours | Ongoing (while campaign active) | Triggers incremental billing |

**Per-Platform Extraction Methods:**

| Platform | Method | Extracted Metrics |
|---|---|---|
| X | Twitter API v2 (fallback: Playwright) | impressions, likes, retweets, replies |
| Reddit | PRAW API (fallback: Playwright) | score, comments |
| LinkedIn | Playwright scraping | reactions, comments, reposts |
| Facebook | Playwright scraping | reactions, comments, shares |

---

## Appendix C: Deployed URLs

> **Note:** The previous Vercel deployment (`server-five-omega-23.vercel.app`) has been taken down. Production server is currently offline. Migration to Hostinger KVM VPS is in progress — see `docs/MIGRATION-FROM-VERCEL.md` (Task #41). Run locally in the meantime.

| Resource | URL |
|---|---|
| Company Dashboard (local) | http://localhost:8000/company/login |
| Admin Dashboard (local) | http://localhost:8000/admin/login |
| Swagger API Docs (local) | http://localhost:8000/docs |
| Health Check (local) | http://localhost:8000/health |
| GitHub (Private) | https://github.com/Samaara-Das/Amplifier |
