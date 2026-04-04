# Amplifier Company Dashboard — API Reference

## Authentication

All company routes (except login/register) require a valid `company_token` JWT cookie. The token contains `{"sub": company_id, "type": "company"}` and is set on successful login.

### Login
```
POST /company/login
Content-Type: application/x-www-form-urlencoded

email=<email>&password=<password>

Success: 302 Redirect to /company/
         Set-Cookie: company_token=<jwt>; HttpOnly; SameSite=Lax; Max-Age=86400
Failure: 401 HTML with error message
```

### Register
```
POST /company/register
Content-Type: application/x-www-form-urlencoded

name=<company_name>&email=<email>&password=<password>

Success: 302 Redirect to /company/ (sets cookie)
Failure: 400 HTML if email already registered
```

### Logout
```
GET /company/logout
Response: 302 Redirect to /company/login (deletes cookie)
```

---

## Pages (GET Routes)

### Dashboard
```
GET /company/
```
No parameters. Returns overview with metrics, alerts, and recent campaigns.

### Campaigns List
```
GET /company/campaigns?page=1&search=&status=&sort=created_at&order=desc

Parameters:
  page     (int)    Default: 1            Page number
  search   (str)    Default: ""           Title substring match (ILIKE)
  status   (str)    Default: ""           Filter: draft|active|paused|completed|cancelled
  sort     (str)    Default: "created_at" Sort by: created_at|budget_total|title
  order    (str)    Default: "desc"       Sort order: asc|desc
  error    (str)    Optional              Error message to display

Pagination: 15 per page
```

### Campaign Wizard
```
GET /company/campaigns/new

Precondition: company.balance >= $50
Redirect: /company/campaigns?error=... if balance insufficient
```

### Campaign Detail
```
GET /company/campaigns/{campaign_id}

Path Parameters:
  campaign_id  (int)    Required    Campaign ID (must be owned by authenticated company)

Query Parameters:
  success  (str)    Optional    Success message to display
  error    (str)    Optional    Error message to display
```

### Influencers
```
GET /company/influencers?search=

Parameters:
  search   (str)    Default: ""    Email substring match (ILIKE)
```

### Billing
```
GET /company/billing?success=&error=&cancelled=

Parameters:
  success    (str)    Optional    Success flash message
  error      (str)    Optional    Error flash message
  cancelled  (str)    Optional    Payment cancelled indicator
```

### Billing Success (Stripe callback)
```
GET /company/billing/success?session_id=<stripe_session_id>

Parameters:
  session_id  (str)    Required    Stripe Checkout session ID

Actions: Verifies payment, credits balance, redirects to /company/billing
```

### Analytics
```
GET /company/stats
```
No parameters. Returns cross-campaign performance metrics.

### Settings
```
GET /company/settings
```
No parameters. Returns company profile form.

---

## Actions (POST Routes)

### Campaign Creation

#### Upload Asset
```
POST /company/campaigns/upload-asset
Content-Type: multipart/form-data

file=<binary>

Accepted: JPEG, PNG, WebP, GIF (images, max 4MB)
          PDF, DOCX, TXT (documents, max 4MB)

Response JSON:
{
  "url": "https://...supabase.../campaign-assets/company-{id}/images/{file}",
  "filename": "original.jpg",
  "content_type": "image/jpeg",
  "type": "image",
  "extracted_text": "..." (documents only)
}

Errors:
  400 — Unsupported file type or file too large
  401 — Not authenticated
  500 — Upload failed (Supabase not configured)
```

#### AI Generate Campaign
```
POST /company/campaigns/ai-generate
Content-Type: application/json

{
  "product_name": "string",
  "product_description": "string (required)",
  "product_features": "string",
  "campaign_goal": "brand_awareness|product_launch|event_promotion|lead_generation",
  "company_urls": ["https://..."],
  "targeting": {
    "niche_tags": ["finance", "tech"],
    "target_regions": ["US", "EU"],
    "required_platforms": ["x", "linkedin"],
    "min_followers": {"x": 1000}
  },
  "must_include": "string",
  "must_avoid": "string",
  "image_urls": ["https://..."],
  "file_contents": [{"filename": "doc.pdf", "extracted_text": "..."}]
}

Response JSON:
{
  "title": "Campaign title (max 60 chars)",
  "brief": "Full campaign brief (500-1000 words)",
  "content_guidance": "Tone and style guide (200-400 words)",
  "payout_rules": {
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "suggested_budget": 100,
  "reach_estimate": {
    "matching_users": 15,
    "estimated_impressions_low": 5000,
    "estimated_impressions_high": 15000
  },
  "ai_error": "string (only if generation failed)"
}
```

#### Save Campaign
```
POST /company/campaigns/new
Content-Type: application/x-www-form-urlencoded

Form Fields:
  title                   (str, required)
  brief                   (str, required)
  budget                  (float, required, min $50)
  rate_per_1k_impressions (float, default 0.50)
  rate_per_like           (float, default 0.01)
  rate_per_repost         (float, default 0.05)
  rate_per_click          (float, default 0.10)
  min_followers_json      (str, JSON, default "{}")
  niche_tags              (list[str], from checkboxes)
  target_regions          (list[str], from checkboxes)
  required_platforms      (list[str], from checkboxes)
  content_guidance        (str, optional)
  start_date              (str, ISO datetime, required)
  end_date                (str, ISO datetime, required)
  campaign_status         (str, "draft"|"active", default "draft")
  budget_exhaustion_action (str, "auto_pause"|"auto_complete")
  max_users               (int, optional)
  min_engagement          (float, default 0.0)
  image_urls_json         (str, JSON array)
  file_urls_json          (str, JSON array)
  file_contents_json      (str, JSON array)
  scraped_knowledge_json  (str, JSON, optional)

Validations:
  - budget >= $50
  - If status="active": company.balance >= budget
  - campaign_status must be "draft" or "active"

Actions:
  - Creates Campaign record
  - If status="active": deducts budget from company.balance

Response: 302 Redirect to /company/campaigns/{id}?success=...
```

### Campaign Management

#### Change Status
```
POST /company/campaigns/{campaign_id}/status
Content-Type: application/x-www-form-urlencoded

new_status=<active|paused|cancelled>

Valid Transitions:
  draft  → active (deducts budget), cancelled
  active → paused, cancelled (refunds remaining)
  paused → active, cancelled (refunds remaining)

Response: 302 Redirect to campaign detail
```

#### Edit Campaign
```
POST /company/campaigns/{campaign_id}/edit
Content-Type: application/x-www-form-urlencoded

title                   (str, required)
brief                   (str, required)
content_guidance        (str, optional)
rate_per_1k_impressions (float)
rate_per_like           (float)
rate_per_repost         (float)
rate_per_click          (float)
end_date                (str, ISO datetime, optional)
budget_exhaustion_action (str, "auto_pause"|"auto_complete")

Actions:
  - Updates campaign fields
  - If title/brief/guidance changed: increments campaign_version, sets screening_status="approved"

Response: 302 Redirect with success message
```

#### Top Up Campaign Budget
```
POST /company/campaigns/{campaign_id}/topup
Content-Type: application/x-www-form-urlencoded

amount=<float>

Validations:
  - amount > 0
  - company.balance >= amount

Actions:
  - campaign.budget_remaining += amount
  - campaign.budget_total += amount
  - company.balance -= amount
  - If paused with auto_pause: reactivates to "active"
  - If budget >= 20% of total: clears budget_alert_sent

Response: 302 Redirect with success message
```

### Billing

#### Add Funds
```
POST /company/billing/topup
Content-Type: application/x-www-form-urlencoded

amount=<float>

Validations: amount > 0

Actions (with Stripe):
  - Creates Stripe Checkout Session
  - Redirects to Stripe hosted page

Actions (without Stripe / test mode):
  - Instantly credits company.balance
  - Redirects to /company/billing?success=...
```

### Settings

#### Update Profile
```
POST /company/settings
Content-Type: application/x-www-form-urlencoded

name=<string>
email=<string>

Validations: Email uniqueness if changed
Response: Re-renders settings page with success/error message
```

---

## Complete Route Summary

```
GET  /company/login                          → Login/register form
POST /company/login                          → Authenticate
POST /company/register                       → Create account
GET  /company/logout                         → End session
GET  /company/                               → Dashboard overview
GET  /company/campaigns                      → Campaign list (paginated, filterable)
GET  /company/campaigns/new                  → Campaign wizard
POST /company/campaigns/upload-asset         → File upload to Supabase
POST /company/campaigns/ai-generate          → AI campaign brief generation
POST /company/campaigns/new                  → Save campaign
GET  /company/campaigns/{id}                 → Campaign detail + analytics
POST /company/campaigns/{id}/status          → Change campaign status
POST /company/campaigns/{id}/edit            → Update campaign content
POST /company/campaigns/{id}/topup           → Add budget to campaign
GET  /company/influencers                    → Cross-campaign influencer view
GET  /company/billing                        → Billing + balance
POST /company/billing/topup                  → Initiate payment
GET  /company/billing/success                → Stripe callback
GET  /company/stats                          → Cross-campaign analytics
GET  /company/settings                       → Company profile
POST /company/settings                       → Update profile
```

Total: **21 routes** (10 GET pages + 11 POST actions)
