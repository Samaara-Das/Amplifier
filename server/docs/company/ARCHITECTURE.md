# Amplifier Company Dashboard — Architecture Document

## 1. System Architecture

```
Browser (Company User)
    │
    ▼
FastAPI (Uvicorn)
    │
    ├── /company/login      → login.py       (auth)
    ├── /company/            → dashboard.py   (overview)
    ├── /company/campaigns   → campaigns.py   (list, create, detail, edit, topup, status)
    ├── /company/influencers → influencers.py  (cross-campaign creator view)
    ├── /company/billing     → billing.py      (payments, Stripe)
    ├── /company/stats       → stats.py        (analytics)
    └── /company/settings    → settings.py     (profile)
    │
    ├──→ Gemini API (campaign brief generation)
    ├──→ Stripe API (payment processing)
    ├──→ Supabase Storage (file uploads)
    │
    ▼
SQLAlchemy (Async)
    │
    ├── SQLite (local development)
    └── PostgreSQL via Supabase (production)
```

## 2. File Structure

```
server/app/
├── routers/
│   └── company/
│       ├── __init__.py      # Combined router, shared helpers (auth, pagination)
│       ├── login.py         # Login/register/logout
│       ├── dashboard.py     # Overview with metrics, alerts, recent campaigns
│       ├── campaigns.py     # Campaign CRUD, wizard, detail, edit, topup, status
│       ├── influencers.py   # Cross-campaign influencer performance
│       ├── billing.py       # Balance management, Stripe integration
│       ├── stats.py         # Cross-campaign analytics
│       └── settings.py      # Company profile
│
├── services/
│   ├── campaign_wizard.py   # AI brief generation (Gemini + URL crawling)
│   ├── payments.py          # Stripe Checkout integration
│   ├── storage.py           # Supabase file uploads + text extraction
│   ├── billing.py           # Earnings calculation from metrics
│   ├── matching.py          # Campaign-to-user matching
│   └── trust.py             # Trust score management
│
├── models/
│   ├── company.py           # Company model (name, email, balance, status)
│   ├── campaign.py          # Campaign model (brief, budget, targeting, payout_rules)
│   ├── assignment.py        # CampaignAssignment (user-campaign link)
│   ├── post.py              # Post (platform, URL, status)
│   ├── metric.py            # Metric (impressions, likes, reposts, comments, clicks)
│   ├── payout.py            # Payout (amount, status, breakdown)
│   └── user.py              # User (influencer profiles)
│
├── templates/
│   ├── base.html            # Shared layout (sidebar + main)
│   └── company/
│       ├── _nav.html          # Shared navigation (8 items + logout)
│       ├── login.html         # Dual-tab login/register
│       ├── dashboard.html     # Overview with metrics grid, alerts, recent campaigns
│       ├── campaigns.html     # Campaign list with search/filter/pagination
│       ├── campaign_wizard.html # 4-step AI wizard (1,387 lines)
│       ├── campaign_create.html # Simple form (legacy, superseded by wizard)
│       ├── campaign_detail.html # Campaign analytics + modals (479 lines)
│       ├── influencers.html   # Cross-campaign influencer table
│       ├── billing.html       # Balance + Stripe top-up + allocations
│       ├── stats.html         # Cross-campaign analytics
│       └── settings.html      # Company profile form
│
└── core/
    ├── config.py             # Pydantic settings
    ├── database.py           # SQLAlchemy engine + session
    └── security.py           # JWT + password hashing
```

## 3. Authentication Architecture

```
Login Flow:
┌────────────────┐   POST /company/login     ┌──────────────────┐
│ Login Form     │ ────────────────────────→  │ Verify password  │
│ (email + pass) │                            │ against DB hash  │
└────────────────┘                            └────────┬─────────┘
                                                       │
                                         ┌─────────────┴──────────────┐
                                         │                            │
                                   valid password            invalid password
                                         │                            │
                                         ▼                            ▼
                                Create JWT token             Re-render login
                                {"sub": id, "type":          with error message
                                 "company"}
                                         │
                                         ▼
                                Set cookie:
                                company_token=<jwt>
                                httponly, samesite=lax
                                max_age=24h
                                         │
                                         ▼
                                Redirect to /company/

Protected Route:
┌──────────────┐    company_token cookie    ┌─────────────────────┐
│ Any page     │ ────────────────────────→  │ get_company_from_   │
│ request      │                            │ cookie() dependency │
└──────────────┘                            └────────┬────────────┘
                                                     │
                                       ┌─────────────┴──────────┐
                                       │                        │
                                 valid JWT +              invalid/missing
                                 company exists                 │
                                       │                        ▼
                                       ▼               Redirect to
                                 Process request        /company/login
                                 with company obj
```

## 4. Campaign Creation Flow

```
Step 1: Product Info          Step 2: Targeting           Step 3: Content
┌─────────────────┐          ┌────────────────┐          ┌────────────────┐
│ • Product name  │          │ • Niche tags   │          │ • Must-include │
│ • Description   │    →     │ • Regions      │    →     │ • Must-avoid   │
│ • Features      │          │ • Platforms    │          │ • Tone         │
│ • Goal          │          │ • Min followers│          │                │
│ • URLs (crawled)│          │ • Max creators │          │ [Generate AI]  │
│ • Images/Files  │          └────────────────┘          └───────┬────────┘
└─────────────────┘                                             │
                                                                ▼
                                                   POST /campaigns/ai-generate
                                                   (JSON body with all data)
                                                                │
                                                   ┌────────────┴───────────┐
                                                   │                        │
                                            ┌──────▼──────┐         ┌──────▼──────┐
                                            │ Deep crawl  │         │ Gemini API  │
                                            │ company URLs│    →    │ generates   │
                                            │ (BFS, 10pg) │         │ brief, rates│
                                            └─────────────┘         └──────┬──────┘
                                                                           │
                                                                    Step 4: Review
                                                                    ┌──────▼──────┐
                                                                    │ • Title     │
                                                                    │ • Brief     │
                                                                    │ • Guidance  │
                                                                    │ • Rates     │
                                                                    │ • Budget    │
                                                                    │ • Dates     │
                                                                    │             │
                                                                    │ [Save Draft]│
                                                                    │ [Activate]  │
                                                                    └──────┬──────┘
                                                                           │
                                                                POST /campaigns/new
                                                                    (form data)
                                                                           │
                                                                    ┌──────▼──────┐
                                                                    │ Create      │
                                                                    │ Campaign    │
                                                                    │ record      │
                                                                    │             │
                                                                    │ If active:  │
                                                                    │ deduct      │
                                                                    │ balance     │
                                                                    └─────────────┘
```

## 5. Budget Flow

```
Company Balance ─────────────────────────────────────────────────
    │                                                           │
    │  ┌── Add Funds ──┐                                       │
    │  │ Stripe        │    ┌── Activate Campaign ──┐          │
    │  │ Checkout  ────┼──→ │ Budget deducted from  │          │
    │  │ OR test mode  │    │ balance to campaign   │          │
    │  └───────────────┘    └──────────┬────────────┘          │
    │                                  │                        │
    │                     ┌────────────▼────────────┐          │
    │                     │ Campaign Budget         │          │
    │                     │ ┌─────────────────────┐ │          │
    │                     │ │ budget_total        │ │          │
    │                     │ │ budget_remaining    │ │          │
    │                     │ └────────┬────────────┘ │          │
    │                     │          │               │          │
    │                     │    ┌─────▼──────┐       │          │
    │                     │    │ Metrics     │       │          │
    │                     │    │ processed   │       │          │
    │                     │    │ → payouts   │       │          │
    │                     │    │ → budget    │       │          │
    │                     │    │   reduced   │       │          │
    │                     │    └─────────────┘       │          │
    │                     │                          │          │
    │  ┌── Cancel ────────┤                          │          │
    │  │ Refund remaining │  budget_remaining → 0    │          │
    │  │ to balance  ─────┼──────────────────────────┼──→ balance
    │  └──────────────────┤                          │
    │                     │                          │
    │  ┌── Top Up ────────┤                          │
    │  │ Transfer from    │  budget_remaining += amt │
    │  │ balance to       │  budget_total += amt     │
    │  │ campaign    ─────┼──────────────────────────┘
    │  └──────────────────┘
    │
```

## 6. Data Model Relationships

```
Company (1)
    │
    ├── has many → Campaign (N)
    │                 │
    │                 ├── has many → CampaignAssignment (N)
    │                 │                 │
    │                 │                 ├── belongs to → User (1)
    │                 │                 │
    │                 │                 └── has many → Post (N)
    │                 │                                 │
    │                 │                                 └── has many → Metric (N)
    │                 │
    │                 └── has many → Payout (N)
    │                                 │
    │                                 └── belongs to → User (1)
    │
    └── balance (account funds for campaign budgets)
```

## 7. AI Integration Architecture

```
run_campaign_wizard()
    │
    ├── 1. Deep Crawl URLs
    │       ├── Seed URLs from company input
    │       ├── BFS: follow same-domain links (2 hops max, 10 pages max)
    │       ├── Extract: title, meta, headings, paragraphs
    │       └── Return: array of page content objects
    │
    ├── 2. Build AI Prompt
    │       ├── Product info (name, description, features)
    │       ├── Campaign goal
    │       ├── Crawled content (compressed)
    │       ├── Targeting criteria
    │       ├── Must-include/avoid constraints
    │       └── Image URLs for context
    │
    ├── 3. Call Gemini API
    │       ├── Primary: gemini-2.5-flash
    │       ├── Fallback 1: gemini-2.0-flash (on 429)
    │       ├── Fallback 2: gemini-2.5-flash-lite (on 429)
    │       └── Parse JSON from response (strip markdown fences)
    │
    ├── 4. Estimate Reach
    │       ├── Query matching users from DB
    │       ├── Apply targeting filters (niches, regions, platforms, followers)
    │       ├── Calculate: 5-15% of total followers as impression estimate
    │       └── Return: matching_users, impressions_low, impressions_high
    │
    └── 5. Suggest Payout Rates
            ├── High-value niches: $1.00/1K, $0.02/like
            ├── Engagement niches: $0.30/1K, $0.015/like
            └── Default: $0.50/1K, $0.01/like
```

## 8. Payment Integration

```
Stripe Flow (production):
┌────────────┐     POST /billing/topup     ┌──────────────────┐
│ Amount     │ ──────────────────────────→  │ create_company_  │
│ Input Form │                              │ checkout()       │
└────────────┘                              └────────┬─────────┘
                                                     │
                                                     ▼
                                            Stripe Checkout Session
                                            (success_url, cancel_url,
                                             metadata: company_id)
                                                     │
                                                     ▼
                                            ┌────────────────────┐
                                            │ Stripe Hosted Page │
                                            └────────┬───────────┘
                                                     │
                                    ┌────────────────┴────────────────┐
                                    │                                 │
                              Success redirect                Cancel redirect
                              /billing/success?session_id=X   /billing?cancelled=1
                                    │
                                    ▼
                            verify_checkout_session()
                            ├── Check payment_status == "paid"
                            ├── Match company_id from metadata
                            └── Credit company.balance

Test Mode (no Stripe):
┌────────────┐     POST /billing/topup     ┌──────────────────┐
│ Amount     │ ──────────────────────────→  │ Instant credit   │
│ Input Form │                              │ to balance       │
└────────────┘                              └──────────────────┘
```

## 9. Design Decisions

### Why a Modular Router Package?
The original `company_pages.py` was 1,203 lines. Splitting into 7 modules keeps each file focused: campaigns.py handles all campaign CRUD (the largest module), billing.py handles payments, etc. The shared `__init__.py` provides auth, pagination, and rendering helpers.

### Why AI-First Campaign Creation?
Most companies don't know how to write effective influencer briefs. The AI wizard reduces campaign creation from "hire a marketing consultant" to "describe your product and click Generate." The fallback chain (3 Gemini models) ensures generation rarely fails.

### Why Server-Side Pagination?
The campaigns list can grow to hundreds of campaigns per company. Client-side pagination would load all data, causing slow page loads. Server-side OFFSET/LIMIT with a parallel COUNT query is efficient at any scale.

### Why the Budget System?
The pre-payment model (add funds → allocate to campaigns) prevents overspending. Companies never owe money — they can only spend what they've deposited. Refunds on cancellation are automatic. This simplifies accounting and eliminates payment disputes.

### Why JWT in Cookies vs. Bearer Tokens?
Server-rendered Jinja2 templates can't attach Bearer tokens to requests. Cookies are sent automatically by the browser on every request, making them ideal for server-rendered web apps. The `httponly` flag prevents XSS theft.
