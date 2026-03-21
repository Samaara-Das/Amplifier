# Amplifier API Reference

## Base URLs

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Production  | `https://amplifier-server.vercel.app` |

Interactive Swagger docs are available at `{base_url}/docs`.

---

## Authentication

### JWT Bearer Tokens

The Amplifier API uses **JWT Bearer tokens** for API authentication. There are two token types:

- **User tokens** -- issued at user registration or login. Required for user-facing endpoints (profile, campaigns, posts, metrics).
- **Company tokens** -- issued at company registration or login. Required for company campaign management and analytics.

**Token lifetime:** 24 hours (1440 minutes).

**Algorithm:** HS256.

Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

### Cookie Auth (Web Dashboards)

The server-rendered web dashboards use cookie-based authentication:

- **Company dashboard** (`/company/*`) -- uses a `company_token` cookie containing a JWT. Set automatically on login via the web form.
- **Admin dashboard** (`/admin/*`) -- uses an `admin_token` cookie with a static value. Set on login with the admin password (default: `"admin"`).

### Standard Error Format

All API errors return JSON:

```json
{
  "detail": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Bad request (validation error, invalid state transition, insufficient balance) |
| `401` | Invalid or expired credentials / token |
| `403` | Forbidden (wrong token type, account banned/suspended) |
| `404` | Resource not found |
| `422` | Unprocessable entity (Pydantic validation failure) |

---

## 1. Authentication

### POST /api/auth/register

Register a new user account.

**Auth:** None

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | User email address |
| `password` | string | Yes | User password |

```json
{
  "email": "trader@example.com",
  "password": "securepass123"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**

| Code | When |
|------|------|
| `400` | Email already registered |
| `422` | Invalid email format or missing fields |

---

### POST /api/auth/login

Log in as an existing user.

**Auth:** None

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | User email address |
| `password` | string | Yes | User password |

```json
{
  "email": "trader@example.com",
  "password": "securepass123"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid email or password |
| `403` | Account is banned |

---

### POST /api/auth/company/register

Register a new company account.

**Auth:** None

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Company display name |
| `email` | string (email) | Yes | Company email address |
| `password` | string | Yes | Company password |

```json
{
  "name": "Acme Trading Co",
  "email": "admin@acmetrading.com",
  "password": "companypass456"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**

| Code | When |
|------|------|
| `400` | Email already registered |
| `422` | Invalid email format or missing fields |

---

### POST /api/auth/company/login

Log in as an existing company.

**Auth:** None

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string (email) | Yes | Company email address |
| `password` | string | Yes | Company password |

```json
{
  "email": "admin@acmetrading.com",
  "password": "companypass456"
}
```

**Response (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid email or password |

---

## 2. User Profile

### GET /api/users/me

Get the authenticated user's profile.

**Auth:** User JWT

**Response (200):**

```json
{
  "id": 1,
  "email": "trader@example.com",
  "platforms": {
    "x": {"connected": true, "username": "@trader"},
    "linkedin": {"connected": true, "username": "trader-pro"}
  },
  "follower_counts": {
    "x": 1250,
    "linkedin": 830
  },
  "niche_tags": ["trading", "finance", "technical-analysis"],
  "trust_score": 75,
  "mode": "semi_auto",
  "earnings_balance": 42.50,
  "total_earned": 187.25,
  "status": "active"
}
```

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |
| `404` | User not found (deleted account) |

---

### PATCH /api/users/me

Update the authenticated user's profile. All fields are optional; only provided fields are updated.

**Auth:** User JWT

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `platforms` | object | No | Platform connection status (e.g., `{"x": {"connected": true}}`) |
| `follower_counts` | object | No | Follower counts per platform (e.g., `{"x": 1250}`) |
| `niche_tags` | string[] | No | Content niche tags |
| `mode` | string | No | Operation mode: `"full_auto"`, `"semi_auto"`, or `"manual"` |
| `device_fingerprint` | string | No | Device fingerprint for fraud detection |

```json
{
  "platforms": {
    "x": {"connected": true, "username": "@trader"},
    "linkedin": {"connected": true, "username": "trader-pro"},
    "reddit": {"connected": true, "username": "u/trader"}
  },
  "follower_counts": {
    "x": 1300,
    "linkedin": 850,
    "reddit": 420
  },
  "niche_tags": ["trading", "finance"],
  "mode": "full_auto"
}
```

**Response (200):** Same shape as `GET /api/users/me`.

**Errors:**

| Code | When |
|------|------|
| `400` | Invalid mode value (must be `full_auto`, `semi_auto`, or `manual`) |
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |

---

### GET /api/users/me/earnings

Get the authenticated user's earnings summary.

**Auth:** User JWT

**Response (200):**

```json
{
  "total_earned": 187.25,
  "current_balance": 42.50,
  "pending": 0.0,
  "per_campaign": []
}
```

**Notes:** The `pending` and `per_campaign` fields are placeholders that will be enriched when the billing engine aggregation is fully built.

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |

---

## 3. Campaigns (User)

### GET /api/campaigns/mine

Poll for campaigns matched to the authenticated user. Runs the matching algorithm and creates new `CampaignAssignment` records for any new matches.

**Auth:** User JWT

**Response (200):** Array of matched campaign briefs.

```json
[
  {
    "campaign_id": 5,
    "assignment_id": 12,
    "title": "Q1 Trading Signals Promo",
    "brief": "Promote our new AI-powered trading signal service. Focus on accuracy and ease of use.",
    "assets": {
      "logo_url": "https://cdn.example.com/logo.png",
      "hashtags": ["#TradingSignals", "#AI"]
    },
    "content_guidance": "Emphasize real results. Include disclaimer about past performance.",
    "payout_rules": {
      "rate_per_1k_impressions": 0.50,
      "rate_per_like": 0.01,
      "rate_per_repost": 0.05,
      "rate_per_click": 0.10
    },
    "payout_multiplier": 1.5
  }
]
```

**Notes:**
- This endpoint is designed for polling. The Amplifier user app calls it every 5-15 minutes.
- The matching algorithm applies hard filters (required platforms, min followers) and soft scoring (niche tags, trust score).
- New assignments are created with status `"assigned"` and a default payout multiplier based on user mode.

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |

---

### PATCH /api/campaigns/assignments/{assignment_id}

Update the status and/or content mode of a campaign assignment.

**Auth:** User JWT

**Query parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | New status: `"content_generated"`, `"posted"`, or `"skipped"` |
| `content_mode` | string | No | Content mode: `"repost"` (1.0x), `"ai_generated"` (1.5x), or `"user_customized"` (2.0x) |

**Example:** `PATCH /api/campaigns/assignments/12?status=posted&content_mode=ai_generated`

**Response (200):**

```json
{
  "status": "updated",
  "assignment_id": 12
}
```

**Notes:**
- Setting `content_mode` updates the `payout_multiplier` on the assignment: `repost` = 1.0x, `ai_generated` = 1.5x, `user_customized` = 2.0x.
- The user can only update assignments belonging to them.

**Errors:**

| Code | When |
|------|------|
| `400` | Invalid status value |
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |
| `404` | Assignment not found or does not belong to this user |

---

## 4. Campaigns (Company API)

### POST /api/company/campaigns

Create a new campaign. Deducts the budget from the company's balance.

**Auth:** Company JWT

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Campaign title |
| `brief` | string | Yes | Campaign brief / description for content creators |
| `assets` | object | No | Asset URLs, hashtags, brand materials. Default: `{}` |
| `budget_total` | float | Yes | Total campaign budget in USD |
| `payout_rules` | PayoutRules | Yes | Per-metric payout rates (see schema below) |
| `targeting` | Targeting | No | Targeting filters (see schema below). Default: no filters |
| `content_guidance` | string | No | Additional content guidelines |
| `penalty_rules` | object | No | Penalty configuration. Default: `{}` |
| `start_date` | datetime | Yes | Campaign start date (ISO 8601) |
| `end_date` | datetime | Yes | Campaign end date (ISO 8601) |

```json
{
  "title": "Q1 Trading Signals Promo",
  "brief": "Promote our AI-powered trading signal service. Focus on accuracy, ease of use, and real results.",
  "assets": {
    "logo_url": "https://cdn.example.com/logo.png",
    "hashtags": ["#TradingSignals", "#AI", "#Trading"]
  },
  "budget_total": 500.00,
  "payout_rules": {
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "targeting": {
    "min_followers": {"x": 500, "linkedin": 200},
    "niche_tags": ["trading", "finance", "stocks"],
    "required_platforms": ["x"]
  },
  "content_guidance": "Include disclaimer: past performance is not indicative of future results.",
  "penalty_rules": {},
  "start_date": "2026-04-01T00:00:00Z",
  "end_date": "2026-04-30T23:59:59Z"
}
```

**Response (200):**

```json
{
  "id": 5,
  "company_id": 1,
  "title": "Q1 Trading Signals Promo",
  "brief": "Promote our AI-powered trading signal service...",
  "assets": {"logo_url": "https://cdn.example.com/logo.png", "hashtags": ["#TradingSignals"]},
  "budget_total": 500.00,
  "budget_remaining": 500.00,
  "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
  "targeting": {"min_followers": {"x": 500}, "niche_tags": ["trading"], "required_platforms": ["x"]},
  "content_guidance": "Include disclaimer: past performance is not indicative of future results.",
  "status": "draft",
  "start_date": "2026-04-01T00:00:00Z",
  "end_date": "2026-04-30T23:59:59Z",
  "created_at": "2026-03-21T10:30:00Z"
}
```

**Notes:**
- The campaign is created with status `"draft"`. You must update it to `"active"` for users to see it.
- The full `budget_total` is immediately deducted from the company's balance.

**Errors:**

| Code | When |
|------|------|
| `400` | Insufficient company balance |
| `401` | Invalid or expired token |
| `403` | Not a company token |
| `422` | Validation error (missing required fields, invalid types) |

---

### GET /api/company/campaigns

List all campaigns belonging to the authenticated company, ordered by creation date (newest first).

**Auth:** Company JWT

**Response (200):** Array of `CampaignResponse` objects.

```json
[
  {
    "id": 5,
    "company_id": 1,
    "title": "Q1 Trading Signals Promo",
    "brief": "Promote our AI-powered trading signal service...",
    "assets": {},
    "budget_total": 500.00,
    "budget_remaining": 312.50,
    "payout_rules": {"rate_per_1k_impressions": 0.50},
    "targeting": {"min_followers": {}, "niche_tags": [], "required_platforms": []},
    "content_guidance": null,
    "status": "active",
    "start_date": "2026-04-01T00:00:00Z",
    "end_date": "2026-04-30T23:59:59Z",
    "created_at": "2026-03-21T10:30:00Z"
  }
]
```

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a company token |

---

### GET /api/company/campaigns/{campaign_id}

Get a single campaign by ID. The campaign must belong to the authenticated company.

**Auth:** Company JWT

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `campaign_id` | int | Campaign ID |

**Response (200):** A single `CampaignResponse` object (same shape as list items above).

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a company token |
| `404` | Campaign not found or does not belong to this company |

---

### PATCH /api/company/campaigns/{campaign_id}

Update a campaign's fields and/or status. The campaign must belong to the authenticated company.

**Auth:** Company JWT

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `campaign_id` | int | Campaign ID |

**Request body:** All fields are optional.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | Updated title |
| `brief` | string | No | Updated brief |
| `assets` | object | No | Updated assets |
| `content_guidance` | string | No | Updated content guidance |
| `status` | string | No | New status (see valid transitions below) |

**Valid status transitions:**

| From | Allowed transitions |
|------|-------------------|
| `draft` | `active`, `cancelled` |
| `active` | `paused`, `cancelled` |
| `paused` | `active`, `cancelled` |

```json
{
  "status": "active",
  "title": "Updated Campaign Title"
}
```

**Response (200):** The updated `CampaignResponse` object.

**Errors:**

| Code | When |
|------|------|
| `400` | Invalid status transition (e.g., `draft` to `paused`) |
| `401` | Invalid or expired token |
| `403` | Not a company token |
| `404` | Campaign not found or does not belong to this company |

---

## 5. Posts & Metrics

### POST /api/posts

Register posted content URLs with the server. Accepts a batch of posts.

**Auth:** User JWT

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `posts` | PostCreate[] | Yes | Array of post records |

Each `PostCreate` item:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `assignment_id` | int | Yes | Campaign assignment this post belongs to |
| `platform` | string | Yes | Platform: `"x"`, `"linkedin"`, `"facebook"`, `"reddit"`, `"tiktok"`, `"instagram"` |
| `post_url` | string | Yes | Public URL of the posted content |
| `content_hash` | string | Yes | SHA256 hash of the post content (for deduplication) |
| `posted_at` | datetime | Yes | When the post was published (ISO 8601) |

```json
{
  "posts": [
    {
      "assignment_id": 12,
      "platform": "x",
      "post_url": "https://x.com/trader/status/1234567890",
      "content_hash": "a1b2c3d4e5f6...",
      "posted_at": "2026-03-21T14:30:00Z"
    },
    {
      "assignment_id": 12,
      "platform": "linkedin",
      "post_url": "https://linkedin.com/posts/trader-pro_activity-123",
      "content_hash": "f6e5d4c3b2a1...",
      "posted_at": "2026-03-21T14:32:00Z"
    }
  ]
}
```

**Response (200):**

```json
{
  "created": [
    {"id": 1, "platform": "x"},
    {"id": 2, "platform": "linkedin"}
  ],
  "count": 2
}
```

**Notes:**
- Posts with invalid `assignment_id` values (not found or not owned by the user) are **silently skipped** -- no error is returned for those individual items.
- The `count` field reflects only the posts that were successfully created.

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |
| `422` | Validation error in request body |

---

### POST /api/metrics

Batch submit scraped engagement metrics for previously registered posts.

**Auth:** User JWT

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metrics` | MetricSubmission[] | Yes | Array of metric snapshots |

Each `MetricSubmission` item:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `post_id` | int | Yes | Post ID (from `POST /api/posts` response) |
| `impressions` | int | No | Impression count. Default: `0` |
| `likes` | int | No | Like count. Default: `0` |
| `reposts` | int | No | Repost/retweet count. Default: `0` |
| `comments` | int | No | Comment count. Default: `0` |
| `clicks` | int | No | Click count. Default: `0` |
| `scraped_at` | datetime | Yes | When the metrics were scraped (ISO 8601) |
| `is_final` | bool | No | Whether this is the final metric snapshot. Default: `false` |

```json
{
  "metrics": [
    {
      "post_id": 1,
      "impressions": 12500,
      "likes": 85,
      "reposts": 12,
      "comments": 7,
      "clicks": 34,
      "scraped_at": "2026-03-22T14:30:00Z",
      "is_final": false
    },
    {
      "post_id": 1,
      "impressions": 45200,
      "likes": 312,
      "reposts": 47,
      "comments": 23,
      "clicks": 128,
      "scraped_at": "2026-03-24T14:30:00Z",
      "is_final": true
    }
  ]
}
```

**Response (200):**

```json
{
  "accepted": 2,
  "total_submitted": 2
}
```

**Notes:**
- Metrics for posts not owned by the user (verified via the assignment chain) are **silently skipped**.
- Multiple metric snapshots can be submitted for the same post over time. The scraper typically collects at T+1h, T+6h, T+24h, and T+72h.
- The `is_final` flag marks the last scrape. Only final metrics are used for billing calculations and analytics aggregations.
- The `accepted` count may be less than `total_submitted` if some post IDs are invalid.

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a user token, or account banned/suspended |
| `422` | Validation error in request body |

---

## 6. Company Analytics

### GET /api/company/dashboard

Server-rendered HTML analytics dashboard for the authenticated company. Displays aggregate stats (total campaigns, active campaigns, total spend, reach, engagement, balance) and a campaign table with per-campaign metrics.

**Auth:** Company JWT (Bearer token)

**Response (200):** HTML page (`text/html`).

**Notes:** This is a server-rendered HTML page, not a JSON API. It is included in the `/api` prefix but returns HTML. For JSON campaign data, use `GET /api/company/campaigns`.

---

### GET /api/company/campaigns/{campaign_id}/analytics

Get detailed analytics for a single campaign, including per-platform breakdowns.

**Auth:** Company JWT (Bearer token)

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `campaign_id` | int | Campaign ID |

**Response (200):**

```json
{
  "campaign": {
    "id": 5,
    "title": "Q1 Trading Signals Promo",
    "status": "active",
    "budget_total": 500.00,
    "budget_remaining": 312.50,
    "spent": 187.50
  },
  "users": 8,
  "platforms": [
    {
      "platform": "x",
      "posts": 12,
      "impressions": 85000,
      "likes": 620,
      "reposts": 95,
      "comments": 43
    },
    {
      "platform": "linkedin",
      "posts": 8,
      "impressions": 32000,
      "likes": 280,
      "reposts": 38,
      "comments": 15
    }
  ]
}
```

**Notes:** Only final metrics (`is_final = true`) are included in the aggregations.

**Errors:**

| Code | When |
|------|------|
| `401` | Invalid or expired token |
| `403` | Not a company token |

If the campaign is not found or does not belong to the company, returns `{"error": "Campaign not found"}` with a `200` status (not a 404).

---

## 7. Admin API

> **Note:** These endpoints are currently unprotected (no admin auth dependency). In production, proper admin authentication will be added.

### GET /api/admin/users

List all users, optionally filtered by status.

**Auth:** None (MVP -- admin auth pending)

**Query parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | No | Filter by user status: `"active"`, `"suspended"`, `"banned"` |

**Response (200):**

```json
[
  {
    "id": 1,
    "email": "trader@example.com",
    "trust_score": 75,
    "mode": "semi_auto",
    "total_earned": 187.25,
    "status": "active",
    "platforms": {"x": {"connected": true}, "linkedin": {"connected": true}},
    "follower_counts": {"x": 1250, "linkedin": 830}
  }
]
```

---

### POST /api/admin/users/{user_id}/suspend

Suspend a user account. Suspended users cannot authenticate or use the API.

**Auth:** None (MVP -- admin auth pending)

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `user_id` | int | User ID to suspend |

**Response (200):**

```json
{
  "status": "suspended",
  "user_id": 1
}
```

**Errors:**

| Code | When |
|------|------|
| `404` | User not found |

---

### POST /api/admin/users/{user_id}/unsuspend

Reactivate a suspended user account.

**Auth:** None (MVP -- admin auth pending)

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `user_id` | int | User ID to unsuspend |

**Response (200):**

```json
{
  "status": "active",
  "user_id": 1
}
```

**Errors:**

| Code | When |
|------|------|
| `400` | User is not currently suspended |
| `404` | User not found |

---

### GET /api/admin/stats

Get system-wide statistics.

**Auth:** None (MVP -- admin auth pending)

**Response (200):**

```json
{
  "users": {
    "total": 42,
    "active": 38
  },
  "campaigns": {
    "total": 15,
    "active": 7
  },
  "posts": {
    "total": 523
  },
  "payouts": {
    "total": 8750.00
  }
}
```

---

## 8. Utility

### GET /health

Health check endpoint.

**Auth:** None

**Response (200):**

```json
{
  "status": "ok"
}
```

---

### GET /api/version

Version and auto-update info for the Amplifier user app.

**Auth:** None

**Response (200):**

```json
{
  "version": "0.1.0",
  "download_url": "",
  "changelog": "Initial release"
}
```

**Notes:** The `download_url` will be populated when the packaged installer is hosted.

---

## 9. Company Web Pages

Server-rendered Jinja2 HTML pages for the company dashboard. Authentication is via `company_token` cookie (JWT). Unauthenticated requests redirect to `/company/login`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/company/login` | Login page (also has register form) |
| POST | `/company/login` | Submit login form (email + password). Sets `company_token` cookie on success. |
| POST | `/company/register` | Submit registration form (name + email + password). Sets `company_token` cookie on success. |
| GET | `/company/logout` | Clear `company_token` cookie and redirect to login |
| GET | `/company/` | Campaigns list with aggregate stats (posts, users, impressions, engagement per campaign) |
| GET | `/company/campaigns/new` | Create campaign form |
| POST | `/company/campaigns/new` | Submit new campaign (title, brief, budget, payout rates, targeting, dates). Deducts budget from balance. |
| GET | `/company/campaigns/{id}` | Campaign detail page with per-platform metric breakdowns |
| POST | `/company/campaigns/{id}/status` | Change campaign status (form field: `new_status`). Follows same transition rules as the API. |
| GET | `/company/billing` | Billing page showing balance and budget allocations per campaign |
| POST | `/company/billing/topup` | Add funds to company balance (form field: `amount`). Placeholder for Stripe integration. |
| GET | `/company/settings` | Company profile settings (name, email) |
| POST | `/company/settings` | Update company name and email |

---

## 10. Admin Web Pages

Server-rendered Jinja2 HTML pages for the admin dashboard. Authentication is via `admin_token` cookie. Login with the admin password (default: `"admin"`, configurable via `ADMIN_PASSWORD` env var). Unauthenticated requests redirect to `/admin/login`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/login` | Admin login page |
| POST | `/admin/login` | Submit admin password. Sets `admin_token` cookie on success. |
| GET | `/admin/logout` | Clear `admin_token` cookie and redirect to login |
| GET | `/admin/` | Overview dashboard: user counts, campaign counts, post counts, payout totals, platform revenue, recent activity |
| GET | `/admin/users` | User management page. Optional `?status=` filter. Shows trust score, mode, platforms, earnings. |
| POST | `/admin/users/{id}/suspend` | Suspend a user (redirects back to users page) |
| POST | `/admin/users/{id}/unsuspend` | Unsuspend a user (redirects back to users page) |
| GET | `/admin/campaigns` | All campaigns across all companies, with per-campaign user count and post count |
| GET | `/admin/fraud` | Fraud detection page: recent penalties with user info |
| POST | `/admin/fraud/run-check` | Run fraud detection checks (anomaly detection, deletion fraud, trust score adjustments). Displays results inline. |
| GET | `/admin/payouts` | Payouts page: pending/paid/failed totals, payout history with user and campaign info |
| POST | `/admin/payouts/run-billing` | Trigger a billing cycle manually. Processes posts, calculates earnings, deducts budgets. |
| POST | `/admin/payouts/run-payout` | Trigger a payout cycle manually via Stripe Connect. Pays users with pending balances above threshold. |

---

## Schemas Reference

### PayoutRules

Defines per-metric payout rates for a campaign.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rate_per_1k_impressions` | float | `0.50` | USD paid per 1,000 impressions |
| `rate_per_like` | float | `0.01` | USD paid per like |
| `rate_per_repost` | float | `0.05` | USD paid per repost/retweet |
| `rate_per_click` | float | `0.10` | USD paid per click |

---

### Targeting

Defines which users are eligible for a campaign.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `min_followers` | object | `{}` | Minimum follower count per platform. E.g., `{"x": 500, "linkedin": 200}` |
| `niche_tags` | string[] | `[]` | Preferred niche tags for soft scoring. E.g., `["trading", "finance"]` |
| `required_platforms` | string[] | `[]` | User must be connected to all listed platforms. E.g., `["x", "linkedin"]` |

---

### CampaignCreate

Request body for `POST /api/company/campaigns`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Campaign title |
| `brief` | string | Yes | Campaign brief for content creators |
| `assets` | object | No | Asset URLs, hashtags, brand materials. Default: `{}` |
| `budget_total` | float | Yes | Total campaign budget (USD) |
| `payout_rules` | PayoutRules | Yes | Per-metric payout rates |
| `targeting` | Targeting | No | User targeting filters. Default: no filters |
| `content_guidance` | string | No | Additional content guidelines |
| `penalty_rules` | object | No | Penalty configuration. Default: `{}` |
| `start_date` | datetime | Yes | Campaign start date (ISO 8601) |
| `end_date` | datetime | Yes | Campaign end date (ISO 8601) |

---

### CampaignUpdate

Request body for `PATCH /api/company/campaigns/{id}`. All fields optional.

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Updated title |
| `brief` | string | Updated brief |
| `assets` | object | Updated assets |
| `content_guidance` | string | Updated content guidance |
| `status` | string | New status (`"active"`, `"paused"`, `"cancelled"` -- transition rules apply) |

---

### CampaignResponse

Returned by all company campaign endpoints.

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Campaign ID |
| `company_id` | int | Owning company ID |
| `title` | string | Campaign title |
| `brief` | string | Campaign brief |
| `assets` | object | Campaign assets |
| `budget_total` | float | Total budget (USD) |
| `budget_remaining` | float | Remaining budget (USD) |
| `payout_rules` | object | Payout rates |
| `targeting` | object | Targeting filters |
| `content_guidance` | string or null | Content guidelines |
| `status` | string | `"draft"`, `"active"`, `"paused"`, `"cancelled"`, or `"completed"` |
| `start_date` | datetime | Campaign start date |
| `end_date` | datetime | Campaign end date |
| `created_at` | datetime | Creation timestamp |

---

### CampaignBrief

Returned by `GET /api/campaigns/mine` -- the campaign info users need for content generation.

| Field | Type | Description |
|-------|------|-------------|
| `campaign_id` | int | Campaign ID |
| `assignment_id` | int | Assignment ID (unique to this user-campaign pair) |
| `title` | string | Campaign title |
| `brief` | string | Campaign brief |
| `assets` | object | Campaign assets |
| `content_guidance` | string or null | Content guidelines |
| `payout_rules` | object | Payout rates |
| `payout_multiplier` | float | User's payout multiplier based on content mode (1.0x - 2.0x) |

---

### UserProfileUpdate

Request body for `PATCH /api/users/me`. All fields optional.

| Field | Type | Description |
|-------|------|-------------|
| `platforms` | object | Platform connection status |
| `follower_counts` | object | Follower counts per platform |
| `niche_tags` | string[] | Content niche tags |
| `mode` | string | `"full_auto"`, `"semi_auto"`, or `"manual"` |
| `device_fingerprint` | string | Device fingerprint for fraud detection |

---

### UserProfileResponse

Returned by `GET /api/users/me` and `PATCH /api/users/me`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | User ID |
| `email` | string | Email address |
| `platforms` | object | Platform connection status |
| `follower_counts` | object | Follower counts per platform |
| `niche_tags` | string[] | Content niche tags |
| `trust_score` | int | Trust score (0-100) |
| `mode` | string | Operation mode |
| `earnings_balance` | float | Current unpaid balance (USD) |
| `total_earned` | float | Lifetime earnings (USD) |
| `status` | string | `"active"`, `"suspended"`, or `"banned"` |

---

### PostCreate

Individual post record within `PostBatchCreate`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `assignment_id` | int | Yes | Campaign assignment ID |
| `platform` | string | Yes | Platform: `"x"`, `"linkedin"`, `"facebook"`, `"reddit"`, `"tiktok"`, `"instagram"` |
| `post_url` | string | Yes | Public URL of the post |
| `content_hash` | string | Yes | SHA256 hash of the content |
| `posted_at` | datetime | Yes | Publication timestamp (ISO 8601) |

---

### PostBatchCreate

Request body for `POST /api/posts`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `posts` | PostCreate[] | Yes | Array of post records |

---

### MetricSubmission

Individual metric snapshot within `MetricBatchSubmit`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `post_id` | int | Yes | -- | Post ID to attach metrics to |
| `impressions` | int | No | `0` | Impression count |
| `likes` | int | No | `0` | Like count |
| `reposts` | int | No | `0` | Repost/retweet count |
| `comments` | int | No | `0` | Comment count |
| `clicks` | int | No | `0` | Click count |
| `scraped_at` | datetime | Yes | -- | When metrics were scraped (ISO 8601) |
| `is_final` | bool | No | `false` | Whether this is the final metric snapshot |

---

### MetricBatchSubmit

Request body for `POST /api/metrics`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metrics` | MetricSubmission[] | Yes | Array of metric snapshots |
