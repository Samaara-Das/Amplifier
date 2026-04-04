# Amplifier Company Dashboard — Concept Document

## 1. Purpose

The Company Dashboard is the B2B interface for businesses that want to promote their products and services through influencer marketing on Amplifier. It lets companies create AI-powered campaigns, manage budgets, track influencer performance, and measure ROI — all from a single web portal.

## 2. Problem Statement

Companies want to reach real audiences through authentic social media content. Traditional advertising is expensive and ignored. Influencer marketing works, but managing it is painful:

- **Finding influencers** is time-consuming — companies don't know who has the right audience
- **Creating campaign briefs** requires marketing expertise many small businesses lack
- **Tracking performance** across platforms is fragmented
- **Paying creators** fairly requires complex metric-based calculations
- **Measuring ROI** is often guesswork

Amplifier solves this by automating the entire pipeline: AI writes the campaign brief, the platform matches with relevant influencers, creators post content, metrics are scraped automatically, and payments are calculated based on actual performance.

The Company Dashboard is how businesses interact with this system.

## 3. Target Users

**Primary:** Small-to-medium businesses and marketing teams that want to run influencer campaigns without a dedicated influencer marketing team. They may not have marketing expertise — the AI wizard handles the heavy lifting.

**Secondary:** Marketing agencies managing campaigns on behalf of clients.

## 4. Core Principles

### 4.1 AI-First Campaign Creation
The 4-step campaign wizard is the centerpiece. Companies describe their product, the AI crawls their website, and generates a complete campaign brief, content guidelines, payout rates, and budget suggestions. The company reviews and adjusts — not starts from scratch.

### 4.2 Pay for Performance
Companies pay based on actual results (impressions, likes, reposts, clicks), not upfront fees to individual influencers. The payout rules are transparent and set during campaign creation. The platform takes a 20% cut.

### 4.3 Full Transparency
Every dollar is tracked: budget allocated, budget spent, budget remaining. Per-platform breakdown shows which platforms deliver the best ROI. Per-influencer metrics show who's performing. No black boxes.

### 4.4 Zero Internal Server Errors
Every page handles edge cases: empty campaigns, zero metrics, missing data, null JSON fields. No user action produces a 500 error.

### 4.5 Self-Service
Companies can create campaigns, add funds, pause/resume/cancel campaigns, edit briefs, and top up budgets — all without contacting support.

## 5. Feature Scope

### 5.1 Dashboard (Overview)
A landing page that gives companies an instant read on their marketing performance:
- **8 metric cards:** Account balance, active campaigns, influencers, posts, impressions, engagement, total spent, cost per 1K impressions
- **Smart alerts:** Low balance warnings, draft campaigns waiting to activate, campaigns running low on budget
- **Recent campaigns table:** Last 5 campaigns with budget progress, impressions, and engagement
- **Quick action buttons:** Create Campaign, Add Funds, View Analytics

### 5.2 Campaigns (List + Search/Filter)
Paginated, searchable campaign list with:
- Search by title
- Filter by status (draft, active, paused, completed, cancelled)
- Sort by date, budget, or title
- Budget progress bars with color coding (green < 70%, yellow 70-90%, red > 90%)
- Screening status indicators (flagged campaigns)
- 15 campaigns per page with pagination controls

### 5.3 Campaign Creation (AI Wizard)
A 4-step wizard that transforms product information into a complete campaign:

**Step 1 — Product Basics:** Name, description, features, campaign goal (brand awareness, product launch, event promotion, lead generation), product URLs (deep-crawled by the AI), image uploads, document uploads

**Step 2 — Target Audience:** Niche categories (21 options), geographic regions (7 options), required platforms (4 options), minimum follower counts per platform, maximum creators, minimum engagement rate

**Step 3 — Content Direction:** Must-include phrases (chip input), must-avoid topics, tone guidance. The "Generate with AI" button triggers the wizard.

**Step 4 — Review & Activate:** AI-generated brief preview with reach estimates, editable title/brief/guidance/payout rates/budget/dates. Options to save as draft or activate immediately.

### 5.4 Campaign Detail
Deep analytics for a single campaign:
- **Stats row:** Impressions, engagement, spent, creators, posts, cost/1K, cost/engagement
- **Budget progress:** Visual bar with percentage, exhaustion action, remaining amount
- **Invitation status:** Stacked bar showing accepted/pending/rejected/expired breakdown
- **Platform ROI table:** Per-platform posts, impressions, engagement, estimated spend, cost/1K, cost/engagement
- **Influencer roster:** Every creator assigned, with their posts, metrics, estimated earnings, and actual payments
- **Brief & config:** Full campaign brief, content guidance, payout rules, schedule
- **Actions:** Pause, resume, cancel (with refund), edit (modal), top up budget (modal)

### 5.5 Influencers (Cross-Campaign)
A single view of every creator who has worked on any of the company's campaigns:
- Email, connected platforms, trust score
- Campaign count, post count, total impressions, engagement, engagement rate
- Total amount paid
- Search by email

### 5.6 Billing
Financial management:
- Account balance, total allocated, total spent
- Add funds via Stripe (or instant credit in test mode)
- Campaign budget allocations table showing per-campaign breakdown
- Payment success/error handling

### 5.7 Analytics
Cross-campaign performance metrics:
- Total campaigns, active count, total spend, impressions, engagement
- Cost per 1K impressions, cost per engagement
- Best performing campaign (by engagement per dollar)
- Best performing platform (by total engagement)
- Platform breakdown with share percentages and visual bars
- Monthly spend trend

### 5.8 Settings
Company profile management:
- Update company name and email
- Email uniqueness validation

## 6. User Flows

### Campaign Creation Flow
```
Dashboard → Create Campaign → Step 1 (product) → Step 2 (audience)
→ Step 3 (content) → [AI generates brief] → Step 4 (review)
→ Save as Draft OR Activate → Campaign Detail page
```

### Budget Management Flow
```
Billing → Enter amount → Stripe Checkout (or test mode instant credit)
→ Balance updated → Create/activate campaigns with available balance
→ Campaign spends budget based on influencer metrics
→ Top up campaign or add more funds as needed
```

### Campaign Lifecycle
```
Draft → Active (deducts budget from balance)
  → Paused (can resume) → Active
  → Cancelled (refunds remaining budget)
  → Completed (budget exhausted or end date reached)
```

## 7. Technical Architecture

- **Backend:** FastAPI with async SQLAlchemy, Jinja2 templates
- **Auth:** JWT tokens in httponly cookies, company-scoped
- **AI:** Gemini API with multi-model fallback chain for campaign brief generation
- **Payments:** Stripe Checkout Sessions with webhook verification (graceful degradation without Stripe)
- **Storage:** Supabase Storage for campaign asset uploads (images, documents)
- **URL Crawling:** BFS web crawler (httpx + BeautifulSoup) for product page analysis
- **Router:** Modular package (`app/routers/company/`) with 7 sub-modules

## 8. Security

- **Authentication:** JWT-based with httponly, samesite=lax cookies
- **Authorization:** Every route verifies company ownership of resources (`campaign.company_id == company.id`)
- **File uploads:** Strict MIME type validation, 4MB size limits
- **Payment verification:** Stripe session verification with company_id matching
- **Input validation:** Budget minimums, status transition validation, email uniqueness checks
- **No client-side secrets:** All business logic runs server-side

## 9. Non-Goals

- **Multi-user access:** One login per company. No team roles or permissions.
- **API access:** Companies interact through the web dashboard only, not via REST API.
- **Real-time updates:** Request-response model. No live metric updates.
- **Campaign templates:** No ability to save and reuse campaign configurations.
- **Invoicing:** No PDF invoice generation.
- **Multi-currency:** USD only.

## 10. Success Criteria

1. A company with no marketing experience can create a complete campaign in under 10 minutes using the AI wizard
2. All 8 pages load without errors with any combination of data
3. Budget tracking is accurate — every dollar allocated, spent, and refunded is accounted for
4. Per-influencer and per-platform ROI is visible on the campaign detail page
5. The dashboard surfaces actionable alerts (low balance, draft campaigns, budget warnings)
