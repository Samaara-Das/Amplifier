# Amplifier API Specification v2

**Status**: Draft -- pending review
**Date**: 2026-03-24
**Companion doc**: [PRODUCT_SPEC_V2.md](./PRODUCT_SPEC_V2.md)

---

## Base URLs

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Production  | `https://amplifier-server.vercel.app` |

Interactive Swagger docs: `{base_url}/docs`

---

## Authentication

### JWT Bearer Tokens

Two token types, both HS256 with 24-hour expiry:

- **User tokens** -- issued at user registration or login. Claims: `{"sub": "<user_id>", "type": "user"}`.
- **Company tokens** -- issued at company registration or login. Claims: `{"sub": "<company_id>", "type": "company"}`.

Include in the `Authorization` header:

```
Authorization: Bearer <token>
```

### Cookie Auth (Web Dashboards)

- **Company dashboard** (`/company/*`) -- `company_token` cookie containing a JWT. Set on login via web form.
- **Admin dashboard** (`/admin/*`) -- `admin_token` cookie with static value `"valid"`. Set on login with admin password (env var `ADMIN_PASSWORD`, default `"admin"`).

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
| `400` | Bad request (validation error, invalid state, insufficient balance) |
| `401` | Invalid or expired credentials / token |
| `403` | Forbidden (wrong token type, suspended/banned account) |
| `404` | Resource not found |
| `422` | Unprocessable entity (Pydantic validation failure) |

---

## 1. Auth Endpoints

### POST /api/auth/register

**Auth**: none
**Description**: Register a new user account. Returns a JWT token immediately.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "email": "user@example.com",       // string (EmailStr), required
  "password": "securepass123"         // string, required
}
```

**Response** (200):

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Email already registered |
| 422 | Invalid email format or missing fields |

---

### POST /api/auth/login

**Auth**: none
**Description**: Log in as an existing user.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "email": "user@example.com",       // string (EmailStr), required
  "password": "securepass123"         // string, required
}
```

**Response** (200):

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid email or password |
| 403 | Account is banned |

---

### POST /api/auth/company/register

**Auth**: none
**Description**: Register a new company account. Returns a JWT token immediately.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "name": "Acme Corp",               // string, required
  "email": "admin@acme.com",         // string (EmailStr), required
  "password": "companypass456"        // string, required
}
```

**Response** (200):

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Email already registered |
| 422 | Invalid email format or missing fields |

---

### POST /api/auth/company/login

**Auth**: none
**Description**: Log in as an existing company.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "email": "admin@acme.com",         // string (EmailStr), required
  "password": "companypass456"        // string, required
}
```

**Response** (200):

```json
{
  "access_token": "eyJhbG...",
  "token_type": "bearer"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid email or password |

---

## 2. User Profile Endpoints

### GET /api/users/me

**Auth**: user
**Description**: Get the authenticated user's profile, including scraped profile data and AI-detected niches.
**Status**: Modified -- response now includes `scraped_profiles` and `ai_detected_niches` fields.

**Request**: None (token-only).

**Response** (200):

```json
{
  "id": 1,
  "email": "user@example.com",
  "platforms": {
    "x": {"connected": true, "username": "@trader"},
    "linkedin": {"connected": true, "username": "trader-pro"},
    "facebook": {"connected": false},
    "reddit": {"connected": true, "username": "u/trader"}
  },
  "follower_counts": {
    "x": 1250,
    "linkedin": 830,
    "reddit": 420
  },
  "niche_tags": ["finance", "tech", "trading"],
  "ai_detected_niches": ["finance", "technical-analysis", "trading"],
  "audience_region": "us",
  "trust_score": 75,
  "mode": "semi_auto",
  "earnings_balance": 42.50,
  "total_earned": 187.25,
  "status": "active",
  "scraped_profiles": {
    "x": {
      "display_name": "Trader Pro",
      "bio": "Quantitative trading | Market analysis",
      "profile_picture_url": "https://pbs.twimg.com/...",
      "follower_count": 1250,
      "following_count": 340,
      "avg_engagement_rate": 3.2,
      "posting_frequency_per_week": 12.5,
      "recent_post_count": 45,
      "scraped_at": "2026-03-20T14:00:00Z"
    },
    "linkedin": {
      "display_name": "Trader Pro",
      "bio": "Senior Market Analyst | Finance enthusiast",
      "profile_picture_url": "https://media.licdn.com/...",
      "follower_count": 830,
      "following_count": 210,
      "avg_engagement_rate": 2.1,
      "posting_frequency_per_week": 4.0,
      "recent_post_count": 18,
      "scraped_at": "2026-03-20T14:02:00Z"
    }
  }
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account banned/suspended |
| 404 | User not found (deleted account) |

**Notes**:
- `scraped_profiles` is a JSON object keyed by platform name. Each entry contains the latest scraped data sent from the desktop app.
- `ai_detected_niches` is the list of niches detected by AI from the user's actual content. Separate from `niche_tags` which may have been adjusted by the user.
- Both new fields may be empty (`{}` / `[]`) if the user has not yet completed profile scraping.

---

### PATCH /api/users/me

**Auth**: user
**Description**: Update the authenticated user's profile. All fields optional; only provided fields are updated. Now accepts scraped profile data and AI-detected niches from the desktop app.
**Status**: Modified -- new fields `scraped_profiles`, `ai_detected_niches`, `audience_region`.

**Request**:

```json
{
  "platforms": {                                  // object, optional
    "x": {"connected": true, "username": "@trader"},
    "linkedin": {"connected": true, "username": "trader-pro"}
  },
  "follower_counts": {                            // object, optional
    "x": 1300,
    "linkedin": 850
  },
  "niche_tags": ["finance", "tech"],              // string[], optional -- user-confirmed niches
  "ai_detected_niches": ["finance", "trading"],   // string[], optional -- AI-detected (from desktop app)
  "audience_region": "us",                        // string, optional (us|uk|india|eu|latam|sea|global)
  "mode": "semi_auto",                            // string, optional (full_auto|semi_auto|manual)
  "device_fingerprint": "abc123...",              // string, optional
  "scraped_profiles": {                           // object, optional -- from desktop scraper
    "x": {
      "display_name": "Trader Pro",
      "bio": "Quantitative trading | Market analysis",
      "profile_picture_url": "https://pbs.twimg.com/...",
      "follower_count": 1300,
      "following_count": 345,
      "avg_engagement_rate": 3.4,
      "posting_frequency_per_week": 13.0,
      "recent_post_count": 48,
      "scraped_at": "2026-03-24T14:00:00Z"
    }
  }
}
```

**Response** (200): Same shape as `GET /api/users/me`.

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Invalid mode value (must be `full_auto`, `semi_auto`, or `manual`) |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account banned/suspended |

**Notes**:
- When `scraped_profiles` is provided, the server merges it into the existing scraped data (per-platform merge, not full replacement). The server also auto-updates `follower_counts` from the scraped data if the scraped values are newer.
- When `ai_detected_niches` is provided, it overwrites the previous AI-detected list entirely.
- The desktop app calls this endpoint after each scraping cycle (on first connect + weekly refresh).

---

### GET /api/users/me/earnings

**Auth**: user
**Description**: Get the authenticated user's earnings summary with real pending calculations and per-campaign breakdowns.
**Status**: Modified -- now returns real data instead of hardcoded zeros.

**Request**: None (token-only).

**Response** (200):

```json
{
  "total_earned": 187.25,
  "current_balance": 42.50,
  "pending": 12.80,
  "per_campaign": [
    {
      "campaign_id": 5,
      "campaign_title": "Q1 Trading Signals Promo",
      "posts": 4,
      "impressions": 45200,
      "engagement": 382,
      "earned": 28.50,
      "status": "paid"
    },
    {
      "campaign_id": 8,
      "campaign_title": "Crypto Exchange Launch",
      "posts": 2,
      "impressions": 12000,
      "engagement": 95,
      "earned": 12.80,
      "status": "pending"
    }
  ],
  "per_platform": {
    "x": 125.00,
    "linkedin": 42.25,
    "reddit": 20.00
  },
  "payout_history": [
    {
      "id": 3,
      "amount": 50.00,
      "status": "paid",
      "requested_at": "2026-03-15T10:00:00Z",
      "paid_at": "2026-03-17T14:30:00Z"
    }
  ]
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account banned/suspended |

**Notes**:
- `pending` is calculated from metrics that have been collected but not yet finalized at T+72h, or finalized but not yet billed.
- `per_campaign[].status` is one of: `pending` (metrics still being collected), `calculated` (billing done, awaiting payout), `paid` (payout complete).
- `per_platform` breaks down lifetime earnings by platform.
- `payout_history` shows the user's withdrawal history.

---

### POST /api/users/me/payout

**Auth**: user
**Description**: Request a payout withdrawal from the user's earnings balance.
**Status**: NEW.

**Request**:

```json
{
  "amount": 25.00                     // float, required -- must be >= 10.00 and <= current balance
}
```

**Response** (200):

```json
{
  "payout_id": 7,
  "amount": 25.00,
  "status": "pending",
  "message": "Payout request submitted. Processing typically takes 2-5 business days."
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Payout request created |
| 400 | Amount below $10 minimum, or exceeds current balance |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |

**Notes**:
- Minimum payout is $10.00.
- The user's `earnings_balance` is decremented immediately upon request.
- Payout is processed via Stripe Connect (skeleton for now -- marked as `pending` until admin processes it).
- If Stripe Connect is not yet configured for the user, returns 400 with instructions to set up payment details (future feature).

---

## 3. Campaign Endpoints -- User Side

### GET /api/campaigns/invitations

**Auth**: user
**Description**: Get pending campaign invitations for this user. Replaces the old `GET /api/campaigns/mine` polling endpoint. Only returns campaigns with `pending_invitation` status (not yet accepted/rejected/expired).
**Status**: NEW (replaces `GET /api/campaigns/mine`).

**Request**: None (token-only).

**Response** (200):

```json
[
  {
    "invitation_id": 14,
    "assignment_id": 22,
    "campaign_id": 5,
    "title": "Q1 Trading Signals Promo",
    "brief": "Promote our AI-powered trading signal service. Focus on accuracy and ease of use.",
    "assets": {
      "logo_url": "https://cdn.example.com/logo.png",
      "hashtags": ["#TradingSignals", "#AI"]
    },
    "content_guidance": "Include disclaimer about past performance.",
    "payout_rules": {
      "rate_per_1k_impressions": 0.50,
      "rate_per_like": 0.01,
      "rate_per_repost": 0.05,
      "rate_per_click": 0.10
    },
    "estimated_earnings": {
      "low": 5.00,
      "high": 25.00
    },
    "required_platforms": ["x", "linkedin"],
    "deadline": "2026-04-30T23:59:59Z",
    "expires_at": "2026-03-27T10:00:00Z",
    "invited_at": "2026-03-24T10:00:00Z"
  }
]
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success (may be empty array) |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |

**Notes**:
- The desktop app polls this endpoint every 10 minutes.
- The matching algorithm runs server-side when campaigns are activated. This endpoint only returns already-matched invitations.
- `expires_at` is 3 days after `invited_at`. Expired invitations are not returned.
- `estimated_earnings` is calculated from the user's historical engagement rates and the campaign's payout rules.
- `required_platforms` is extracted from `targeting.required_platforms` for convenience.

---

### POST /api/campaigns/invitations/{invitation_id}/accept

**Auth**: user
**Description**: Accept a campaign invitation. Transitions the assignment from `pending_invitation` to `accepted`.
**Status**: NEW.

**Request**: None (invitation_id in path).

**Response** (200):

```json
{
  "assignment_id": 22,
  "campaign_id": 5,
  "status": "accepted",
  "message": "Campaign accepted. Content generation will begin shortly."
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Invitation accepted |
| 400 | Invitation already accepted/rejected/expired, or user has 5 active campaigns (max limit reached) |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 404 | Invitation not found or does not belong to this user |

**Notes**:
- Users can have a maximum of 5 active campaigns at a time. Attempting to accept a 6th returns 400.
- The invitation must be in `pending_invitation` status and not expired.
- After acceptance, the desktop app should proceed to content generation.

---

### POST /api/campaigns/invitations/{invitation_id}/reject

**Auth**: user
**Description**: Reject a campaign invitation. The user will not be re-invited to this campaign.
**Status**: NEW.

**Request**: None (invitation_id in path).

**Response** (200):

```json
{
  "assignment_id": 22,
  "campaign_id": 5,
  "status": "rejected",
  "message": "Campaign rejected."
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Invitation rejected |
| 400 | Invitation already accepted/rejected/expired |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 404 | Invitation not found or does not belong to this user |

**Notes**:
- Rejection is permanent for this campaign. The slot may be re-offered to another matching user.

---

### GET /api/campaigns/active

**Auth**: user
**Description**: Get the user's active (accepted) campaigns with the latest brief, content guidance, and campaign status. Used by the desktop app to check for campaign updates.
**Status**: NEW.

**Request**: None (token-only).

**Response** (200):

```json
[
  {
    "assignment_id": 22,
    "campaign_id": 5,
    "title": "Q1 Trading Signals Promo",
    "brief": "Promote our AI-powered trading signal service. Focus on accuracy and ease of use.",
    "assets": {
      "logo_url": "https://cdn.example.com/logo.png",
      "hashtags": ["#TradingSignals", "#AI"]
    },
    "content_guidance": "Include disclaimer about past performance.",
    "payout_rules": {
      "rate_per_1k_impressions": 0.50,
      "rate_per_like": 0.01,
      "rate_per_repost": 0.05,
      "rate_per_click": 0.10
    },
    "payout_multiplier": 1.5,
    "assignment_status": "accepted",
    "campaign_status": "active",
    "campaign_updated_at": "2026-03-24T12:00:00Z",
    "requires_re_review": false,
    "start_date": "2026-04-01T00:00:00Z",
    "end_date": "2026-04-30T23:59:59Z"
  }
]
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success (may be empty array) |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |

**Notes**:
- Returns assignments with status in: `accepted`, `content_generated`, `posted`, `metrics_collected`.
- `requires_re_review` is `true` if the campaign was edited after the user generated/approved content but before posting. The desktop app should alert the user to re-review.
- `campaign_updated_at` allows the desktop app to detect changes since last poll.
- The desktop app polls this every 10 minutes alongside invitations.

---

### GET /api/campaigns/assignments/{assignment_id}

**Auth**: user
**Description**: Get a single assignment's full detail, including campaign brief and current status. Used to check if a campaign has been edited since the user last saw it.
**Status**: NEW.

**Request**: None (assignment_id in path).

**Response** (200):

```json
{
  "assignment_id": 22,
  "campaign_id": 5,
  "title": "Q1 Trading Signals Promo",
  "brief": "Promote our AI-powered trading signal service. Focus on accuracy and ease of use.",
  "assets": {
    "logo_url": "https://cdn.example.com/logo.png",
    "hashtags": ["#TradingSignals", "#AI"]
  },
  "content_guidance": "Include disclaimer about past performance.",
  "payout_rules": {
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "payout_multiplier": 1.5,
  "assignment_status": "content_generated",
  "campaign_status": "active",
  "campaign_updated_at": "2026-03-24T12:00:00Z",
  "requires_re_review": true,
  "start_date": "2026-04-01T00:00:00Z",
  "end_date": "2026-04-30T23:59:59Z",
  "posts": [
    {
      "id": 10,
      "platform": "x",
      "post_url": "https://x.com/trader/status/123",
      "status": "live",
      "posted_at": "2026-03-22T14:30:00Z"
    }
  ]
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 404 | Assignment not found or does not belong to this user |

---

### PATCH /api/campaigns/assignments/{assignment_id}

**Auth**: user
**Description**: Update assignment status and/or content mode.
**Status**: Existing -- unchanged.

**Request** (query parameters):

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | New status: `"content_generated"`, `"posted"`, or `"skipped"` |
| `content_mode` | string | No | `"repost"` (1.0x), `"ai_generated"` (1.5x), or `"user_customized"` (2.0x) |

**Example**: `PATCH /api/campaigns/assignments/22?status=posted&content_mode=ai_generated`

**Response** (200):

```json
{
  "status": "updated",
  "assignment_id": 22
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Invalid status value |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 404 | Assignment not found or does not belong to this user |

**Notes**:
- Setting `content_mode` updates the `payout_multiplier`: `repost` = 1.0x, `ai_generated` = 1.5x, `user_customized` = 2.0x.

---

## 4. Post & Metric Endpoints

### POST /api/posts

**Auth**: user
**Description**: Register posted content URLs with the server. Accepts a batch of posts.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "posts": [
    {
      "assignment_id": 22,            // int, required
      "platform": "x",               // string, required (x|linkedin|facebook|reddit|tiktok|instagram)
      "post_url": "https://x.com/trader/status/123",  // string, required
      "content_hash": "a1b2c3d4e5f6...",               // string, required (SHA256)
      "posted_at": "2026-03-21T14:30:00Z"              // datetime, required (ISO 8601)
    }
  ]
}
```

**Response** (200):

```json
{
  "created": [
    {"id": 1, "platform": "x"}
  ],
  "count": 1
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 422 | Validation error in request body |

**Notes**:
- Posts with invalid `assignment_id` values (not found or not owned by the user) are silently skipped.
- The `count` field reflects only the posts that were successfully created.

---

### POST /api/metrics

**Auth**: user
**Description**: Batch submit scraped engagement metrics for previously registered posts. Triggers billing when final metrics are submitted.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "metrics": [
    {
      "post_id": 1,                   // int, required
      "impressions": 12500,           // int, optional (default: 0)
      "likes": 85,                    // int, optional (default: 0)
      "reposts": 12,                  // int, optional (default: 0)
      "comments": 7,                  // int, optional (default: 0)
      "clicks": 34,                   // int, optional (default: 0)
      "scraped_at": "2026-03-22T14:30:00Z",  // datetime, required (ISO 8601)
      "is_final": false               // bool, optional (default: false)
    }
  ]
}
```

**Response** (200):

```json
{
  "accepted": 1,
  "total_submitted": 1,
  "billing": {                        // present only if final metrics triggered billing
    "posts_processed": 3,
    "total_earned": 15.50,
    "total_budget_deducted": 19.38
  }
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a user token, or account suspended/banned |
| 422 | Validation error in request body |

**Notes**:
- Metrics for posts not owned by the user (verified via the assignment chain) are silently skipped.
- Multiple snapshots per post are expected: T+1h, T+6h, T+24h, T+72h.
- `is_final: true` on the T+72h snapshot triggers billing calculation.
- The `billing` field is only present in the response if final metrics were submitted and billing ran successfully.

---

## 5. Company Campaign Endpoints

### POST /api/company/campaigns

**Auth**: company
**Description**: Create a new campaign. Deducts the budget from the company's balance. Now accepts `company_urls` for AI-assisted brief generation and `ai_generated_brief` flag.
**Status**: Modified -- new optional fields.

**Request**:

```json
{
  "title": "Q1 Trading Signals Promo",                    // string, required
  "brief": "Promote our AI-powered trading signal service.",  // string, required
  "assets": {                                              // object, optional (default: {})
    "logo_url": "https://cdn.example.com/logo.png",
    "hashtags": ["#TradingSignals", "#AI"],
    "image_urls": ["https://cdn.example.com/banner.png"]
  },
  "budget_total": 500.00,                                  // float, required (minimum: 50.00)
  "payout_rules": {                                        // PayoutRules, required
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "targeting": {                                           // Targeting, optional (default: no filters)
    "min_followers": {"x": 500, "linkedin": 200},
    "niche_tags": ["trading", "finance"],
    "required_platforms": ["x"],
    "target_regions": ["us", "uk"]
  },
  "content_guidance": "Include disclaimer about past performance.",  // string, optional
  "penalty_rules": {},                                     // object, optional (default: {})
  "start_date": "2026-04-01T00:00:00Z",                   // datetime, required (ISO 8601)
  "end_date": "2026-04-30T23:59:59Z",                     // datetime, required (ISO 8601)
  "company_urls": [                                        // string[], optional -- NEW
    "https://acmetrading.com",
    "https://acmetrading.com/product"
  ],
  "ai_generated_brief": false                              // bool, optional (default: false) -- NEW
}
```

**Response** (200):

```json
{
  "id": 5,
  "company_id": 1,
  "title": "Q1 Trading Signals Promo",
  "brief": "Promote our AI-powered trading signal service.",
  "assets": {"logo_url": "https://cdn.example.com/logo.png"},
  "budget_total": 500.00,
  "budget_remaining": 500.00,
  "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
  "targeting": {"min_followers": {"x": 500}, "niche_tags": ["trading"], "required_platforms": ["x"], "target_regions": ["us", "uk"]},
  "content_guidance": "Include disclaimer about past performance.",
  "status": "draft",
  "screening_status": "pending",
  "start_date": "2026-04-01T00:00:00Z",
  "end_date": "2026-04-30T23:59:59Z",
  "created_at": "2026-03-24T10:30:00Z"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Insufficient company balance, or budget below $50 minimum |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 422 | Validation error |

**Notes**:
- Campaign is created with status `"draft"`. Must be transitioned to `"active"` via PATCH for users to receive invitations.
- The full `budget_total` is immediately deducted from the company's balance.
- `company_urls` are stored for use by the AI wizard. They are scraped asynchronously after campaign creation to enrich the brief.
- `ai_generated_brief` flag indicates whether the brief was AI-generated via the wizard (for analytics only).
- After creation, the server runs automated content screening. If flagged, `screening_status` will be `"flagged"` and the campaign cannot be activated until admin review.
- `targeting.target_regions` is a new field: array of region codes (`us`, `uk`, `eu`, `india`, `latam`, `sea`, `global`).

---

### GET /api/company/campaigns

**Auth**: company
**Description**: List all campaigns belonging to the authenticated company, ordered by creation date (newest first). Now includes invitation statistics.
**Status**: Modified -- response includes invitation stats.

**Request**: None (token-only).

**Response** (200):

```json
[
  {
    "id": 5,
    "company_id": 1,
    "title": "Q1 Trading Signals Promo",
    "brief": "Promote our AI-powered trading signal service.",
    "assets": {},
    "budget_total": 500.00,
    "budget_remaining": 312.50,
    "payout_rules": {"rate_per_1k_impressions": 0.50},
    "targeting": {"min_followers": {}, "niche_tags": [], "required_platforms": [], "target_regions": []},
    "content_guidance": null,
    "status": "active",
    "screening_status": "approved",
    "start_date": "2026-04-01T00:00:00Z",
    "end_date": "2026-04-30T23:59:59Z",
    "created_at": "2026-03-21T10:30:00Z",
    "invitation_stats": {
      "total_invited": 47,
      "accepted": 12,
      "rejected": 8,
      "expired": 15,
      "pending": 12
    }
  }
]
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a company token |

---

### GET /api/company/campaigns/{campaign_id}

**Auth**: company
**Description**: Get a single campaign by ID, with detailed per-user stats and invitation status.
**Status**: Modified -- richer response with per-user performance data.

**Request**: None (campaign_id in path).

**Response** (200):

```json
{
  "id": 5,
  "company_id": 1,
  "title": "Q1 Trading Signals Promo",
  "brief": "Promote our AI-powered trading signal service.",
  "assets": {"logo_url": "https://cdn.example.com/logo.png"},
  "budget_total": 500.00,
  "budget_remaining": 312.50,
  "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
  "targeting": {"min_followers": {"x": 500}, "niche_tags": ["trading"], "required_platforms": ["x"], "target_regions": ["us"]},
  "content_guidance": "Include disclaimer about past performance.",
  "status": "active",
  "screening_status": "approved",
  "start_date": "2026-04-01T00:00:00Z",
  "end_date": "2026-04-30T23:59:59Z",
  "created_at": "2026-03-21T10:30:00Z",
  "invitation_stats": {
    "total_invited": 47,
    "accepted": 12,
    "rejected": 8,
    "expired": 15,
    "pending": 12
  },
  "aggregate_metrics": {
    "total_posts": 28,
    "total_impressions": 117000,
    "total_likes": 900,
    "total_reposts": 133,
    "total_comments": 58,
    "total_clicks": 162,
    "unique_users": 12,
    "budget_spent": 187.50,
    "cost_per_impression": 0.0016,
    "cost_per_engagement": 0.15
  },
  "per_user": [
    {
      "user_display_name": "Trader Pro",
      "user_id": 1,
      "platforms_posted": ["x", "linkedin"],
      "posts": [
        {
          "platform": "x",
          "post_url": "https://x.com/trader/status/123",
          "impressions": 12500,
          "likes": 85,
          "reposts": 12,
          "comments": 7,
          "clicks": 34,
          "status": "live"
        }
      ],
      "total_impressions": 18500,
      "total_engagement": 138,
      "total_earned": 15.25,
      "assignment_status": "posted"
    }
  ],
  "per_platform": [
    {
      "platform": "x",
      "posts": 12,
      "impressions": 85000,
      "likes": 620,
      "reposts": 95,
      "comments": 43,
      "clicks": 128
    },
    {
      "platform": "linkedin",
      "posts": 8,
      "impressions": 32000,
      "likes": 280,
      "reposts": 38,
      "comments": 15,
      "clicks": 34
    }
  ]
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

---

### PATCH /api/company/campaigns/{campaign_id}

**Auth**: company
**Description**: Update a campaign's fields and/or status. Can edit active campaigns with propagation rules.
**Status**: Modified -- new fields `payout_rules`, `end_date`, `budget_total` (increase only for active campaigns). Enforces edit propagation rules.

**Request**:

```json
{
  "title": "Updated Title",                    // string, optional
  "brief": "Updated brief text",               // string, optional
  "assets": {},                                // object, optional
  "content_guidance": "Updated guidance",       // string, optional
  "payout_rules": {                            // PayoutRules, optional -- NEW for active edits
    "rate_per_1k_impressions": 0.75,
    "rate_per_like": 0.02,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "end_date": "2026-05-15T23:59:59Z",         // datetime, optional -- NEW for active edits
  "status": "active"                           // string, optional (transition rules apply)
}
```

**Valid status transitions**:

| From | Allowed |
|------|---------|
| `draft` | `active`, `cancelled` |
| `active` | `paused`, `cancelled`, `completed` |
| `paused` | `active`, `cancelled` |

**Response** (200): Full `CampaignResponse` object (same as GET detail).

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Invalid status transition, or attempting to edit targeting on active campaign, or attempting to reduce budget on active campaign |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

**Notes -- Edit propagation for active campaigns**:
- **Can edit**: `title`, `brief`, `content_guidance`, `assets`, `payout_rules`, `end_date`, `budget_total` (increase only).
- **Cannot edit**: `targeting` (would invalidate existing matches), `budget_total` (decrease -- would break commitments to matched users).
- **Already posted content**: untouched, earnings calculated using the payout rules that were active at time of billing.
- **Approved but not yet posted content**: assignments are flagged as `requires_re_review = true`. Desktop app alerts users to re-review before posting.
- **Not yet generated content**: uses the updated brief/guidance automatically.
- **Payout rate changes**: only affect future posts, not already-billed ones.
- Users pick up changes on next poll cycle (every 10 minutes via `GET /api/campaigns/active`).

---

### DELETE /api/company/campaigns/{campaign_id}

**Auth**: company
**Description**: Delete a campaign. Only allowed for draft or cancelled campaigns. Budget is refunded to company balance for draft campaigns.
**Status**: NEW.

**Request**: None (campaign_id in path).

**Response** (200):

```json
{
  "deleted": true,
  "campaign_id": 5,
  "budget_refunded": 500.00
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Campaign deleted |
| 400 | Campaign is not in `draft` or `cancelled` status |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

**Notes**:
- Draft campaigns get their full `budget_total` refunded to the company balance.
- Cancelled campaigns get their `budget_remaining` refunded.
- Active or paused campaigns cannot be deleted -- cancel them first.

---

### POST /api/company/campaigns/{campaign_id}/clone

**Auth**: company
**Description**: Clone an existing campaign with new dates and budget. Pre-fills all fields from the original.
**Status**: NEW.

**Request**:

```json
{
  "title": "Q2 Trading Signals Promo",         // string, optional (default: "{original_title} (Copy)")
  "budget_total": 750.00,                      // float, optional (default: same as original)
  "start_date": "2026-07-01T00:00:00Z",        // datetime, optional (default: today)
  "end_date": "2026-07-31T23:59:59Z"           // datetime, optional (default: +30 days)
}
```

**Response** (200): Full `CampaignResponse` of the newly created campaign (status: `"draft"`).

**Status codes**:

| Code | When |
|------|------|
| 200 | Clone created |
| 400 | Insufficient balance for the new campaign's budget |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Source campaign not found or does not belong to this company |

**Notes**:
- The cloned campaign copies: `brief`, `assets`, `payout_rules`, `targeting`, `content_guidance`, `penalty_rules`.
- The clone is created in `draft` status regardless of the source campaign's status.
- Budget is deducted from company balance immediately.

---

### GET /api/company/campaigns/{campaign_id}/export

**Auth**: company
**Description**: Download a campaign report as CSV or PDF.
**Status**: NEW.

**Request** (query parameters):

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `format` | string | No | `csv` | Export format: `csv` or `pdf` |
| `date_from` | datetime | No | campaign start | Filter start date (ISO 8601) |
| `date_to` | datetime | No | now | Filter end date (ISO 8601) |

**Example**: `GET /api/company/campaigns/5/export?format=csv`

**Response** (200): File download (`Content-Type: text/csv` or `application/pdf`). `Content-Disposition: attachment; filename="campaign-5-report.csv"`.

CSV columns: `user_display_name, platform, post_url, posted_at, impressions, likes, reposts, comments, clicks, earned, status`

**Status codes**:

| Code | When |
|------|------|
| 200 | File download |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

---

### GET /api/company/campaigns/{campaign_id}/reach-estimate

**Auth**: company
**Description**: Estimate reach for a campaign based on its current targeting criteria. Can also be called with query params to estimate before saving.
**Status**: NEW.

**Request** (query parameters, all optional -- defaults to using the saved campaign targeting):

| Param | Type | Description |
|-------|------|-------------|
| `niche_tags` | string (comma-separated) | Override niche tags |
| `required_platforms` | string (comma-separated) | Override required platforms |
| `target_regions` | string (comma-separated) | Override target regions |
| `min_followers_x` | int | Override min followers for X |
| `min_followers_linkedin` | int | Override min followers for LinkedIn |
| `min_followers_facebook` | int | Override min followers for Facebook |
| `min_followers_reddit` | int | Override min followers for Reddit |

**Response** (200):

```json
{
  "matching_users": 47,
  "estimated_reach": {
    "low": 150000,
    "high": 300000
  },
  "estimated_cost": {
    "low": 150.00,
    "high": 350.00
  },
  "per_platform": {
    "x": {"users": 35, "est_impressions_low": 100000, "est_impressions_high": 200000},
    "linkedin": {"users": 28, "est_impressions_low": 50000, "est_impressions_high": 100000}
  }
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

**Notes**:
- Estimates are based on matching user count, their historical engagement rates, and the campaign's payout rules.
- This updates live as the company changes targeting criteria in the wizard (called via query param overrides before saving).

---

### POST /api/company/campaigns/ai-wizard

**Auth**: company
**Description**: AI generates a full campaign from wizard answers and optionally scraped company URLs. Returns a pre-filled `CampaignCreate` object for review.
**Status**: NEW.

**Request**:

```json
{
  "product_description": "AI-powered trading signal service",  // string, required
  "campaign_goal": "brand_awareness",   // string, required (brand_awareness|product_launch|event_promotion|lead_generation)
  "company_urls": [                     // string[], optional
    "https://acmetrading.com",
    "https://acmetrading.com/product"
  ],
  "target_niches": ["trading", "finance"],  // string[], optional
  "target_regions": ["us", "uk"],           // string[], optional
  "required_platforms": ["x", "linkedin"],  // string[], optional
  "min_followers": {"x": 500},             // object, optional
  "tone": "professional",                   // string, optional (professional|casual|funny|educational|inspirational)
  "must_include": ["#TradingSignals"],      // string[], optional
  "must_avoid": ["guaranteed returns"],     // string[], optional
  "budget_range": {                         // object, optional
    "min": 200,
    "max": 500
  },
  "start_date": "2026-04-01T00:00:00Z",    // datetime, optional
  "end_date": "2026-04-30T23:59:59Z"       // datetime, optional
}
```

**Response** (200):

```json
{
  "generated_campaign": {
    "title": "AI Trading Signals: Trade Smarter, Not Harder",
    "brief": "Promote Acme Trading's AI-powered signal service. Highlight the 87% accuracy rate, ease of use, and free trial. Focus on how it helps everyday traders make better decisions without needing to watch charts all day.",
    "assets": {
      "logo_url": "https://acmetrading.com/logo.png",
      "hashtags": ["#TradingSignals", "#AI", "#SmartTrading"],
      "product_url": "https://acmetrading.com/product"
    },
    "content_guidance": "Tone: professional but accessible. Must include disclaimer: past performance does not guarantee future results. Avoid: guaranteed returns, get-rich-quick language, specific profit claims.",
    "payout_rules": {
      "rate_per_1k_impressions": 0.50,
      "rate_per_like": 0.01,
      "rate_per_repost": 0.05,
      "rate_per_click": 0.10
    },
    "targeting": {
      "min_followers": {"x": 500},
      "niche_tags": ["trading", "finance"],
      "required_platforms": ["x", "linkedin"],
      "target_regions": ["us", "uk"]
    },
    "budget_total": 350.00,
    "start_date": "2026-04-01T00:00:00Z",
    "end_date": "2026-04-30T23:59:59Z"
  },
  "scraped_data": {
    "company_name": "Acme Trading Co",
    "description": "AI-powered trading signals for everyday traders",
    "key_selling_points": ["87% accuracy rate", "Free 14-day trial", "No charting experience needed"],
    "images_found": ["https://acmetrading.com/logo.png", "https://acmetrading.com/banner.png"]
  },
  "reach_estimate": {
    "matching_users": 47,
    "estimated_reach": {"low": 150000, "high": 300000},
    "estimated_cost": {"low": 150.00, "high": 350.00}
  }
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Campaign generated |
| 400 | Missing required fields |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 422 | Validation error |

**Notes**:
- This does NOT create a campaign. It returns a generated draft for the company to review and edit before calling `POST /api/company/campaigns`.
- If `company_urls` are provided, the server scrapes them to extract company info, product details, images, and selling points. This data enriches the AI generation.
- The AI generates: `title`, `brief`, `content_guidance`, suggested `payout_rules`, and `assets`.
- `scraped_data` shows what was extracted from the URLs (for transparency).
- `reach_estimate` is included so the company can see projected results immediately.
- Response time may be 5-15 seconds due to URL scraping + AI generation. Consider a 30-second client timeout.

---

### POST /api/company/campaigns/{campaign_id}/budget-topup

**Auth**: company
**Description**: Increase the budget for an active campaign without creating a new one.
**Status**: NEW.

**Request**:

```json
{
  "amount": 200.00                     // float, required (minimum: 10.00)
}
```

**Response** (200):

```json
{
  "campaign_id": 5,
  "budget_total": 700.00,
  "budget_remaining": 512.50,
  "company_balance": 300.00
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Budget increased |
| 400 | Insufficient company balance, or campaign not in `active` or `paused` status, or amount below minimum |
| 401 | Invalid or expired token |
| 403 | Not a company token |
| 404 | Campaign not found or does not belong to this company |

**Notes**:
- The top-up amount is deducted from the company's balance and added to both `budget_total` and `budget_remaining`.
- Works on `active` and `paused` campaigns.

---

## 6. Company Billing Endpoints

### GET /api/company/billing

**Auth**: company
**Description**: Get the company's billing summary including balance, total spend, and per-campaign budget allocations.
**Status**: Existing -- enhanced response.

**Request**: None (token-only).

**Response** (200):

```json
{
  "balance": 500.00,
  "total_spent": 1250.00,
  "allocations": [
    {
      "campaign_id": 5,
      "campaign_title": "Q1 Trading Signals Promo",
      "budget_total": 500.00,
      "budget_remaining": 312.50,
      "spent": 187.50,
      "status": "active",
      "created_at": "2026-03-21T10:30:00Z"
    }
  ]
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 401 | Invalid or expired token |
| 403 | Not a company token |

---

### POST /api/company/billing/topup

**Auth**: company
**Description**: Add funds to the company's balance. Placeholder for Stripe integration.
**Status**: Existing -- unchanged.

**Request**:

```json
{
  "amount": 500.00                     // float, required (must be > 0)
}
```

**Response** (200):

```json
{
  "balance": 1000.00,
  "amount_added": 500.00
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Amount must be positive |
| 401 | Invalid or expired token |
| 403 | Not a company token |

**Notes**:
- This is a placeholder. In production, this would initiate a Stripe Checkout session and only credit the balance after payment confirmation.

---

## 7. Admin Endpoints

### GET /api/admin/users

**Auth**: admin (currently unprotected -- admin auth pending)
**Description**: List all users, optionally filtered by status.
**Status**: Existing -- unchanged.

**Request** (query parameters):

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | No | Filter: `active`, `suspended`, `banned` |

**Response** (200):

```json
[
  {
    "id": 1,
    "email": "user@example.com",
    "trust_score": 75,
    "mode": "semi_auto",
    "total_earned": 187.25,
    "status": "active",
    "platforms": {"x": {"connected": true}, "linkedin": {"connected": true}},
    "follower_counts": {"x": 1250, "linkedin": 830}
  }
]
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |

---

### POST /api/admin/users/{user_id}/suspend

**Auth**: admin
**Description**: Suspend a user account.
**Status**: Existing -- unchanged.

**Request**: None (user_id in path).

**Response** (200):

```json
{
  "status": "suspended",
  "user_id": 1
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 404 | User not found |

---

### POST /api/admin/users/{user_id}/unsuspend

**Auth**: admin
**Description**: Reactivate a suspended user account.
**Status**: Existing -- unchanged.

**Request**: None (user_id in path).

**Response** (200):

```json
{
  "status": "active",
  "user_id": 1
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | User is not currently suspended |
| 404 | User not found |

---

### GET /api/admin/stats

**Auth**: admin
**Description**: Get system-wide statistics.
**Status**: Existing -- unchanged.

**Request**: None.

**Response** (200):

```json
{
  "users": {"total": 42, "active": 38},
  "campaigns": {"total": 15, "active": 7},
  "posts": {"total": 523},
  "payouts": {"total": 8750.00}
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |

---

### GET /api/admin/flagged-campaigns

**Auth**: admin
**Description**: Get campaigns flagged by automated content screening that require manual review.
**Status**: NEW.

**Request** (query parameters):

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | No | Filter: `pending_review`, `approved`, `rejected`. Default: `pending_review` |

**Response** (200):

```json
[
  {
    "campaign_id": 12,
    "company_id": 3,
    "company_name": "Sketchy Corp",
    "title": "Amazing Returns Guaranteed",
    "brief": "Get 500% returns with our revolutionary trading bot...",
    "screening_flags": [
      {
        "category": "financial_fraud",
        "matched_phrases": ["guaranteed returns", "500% returns"],
        "severity": "high"
      }
    ],
    "screening_status": "flagged",
    "created_at": "2026-03-24T08:00:00Z"
  }
]
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |

---

### POST /api/admin/flagged-campaigns/{campaign_id}/approve

**Auth**: admin
**Description**: Approve a flagged campaign, allowing it to be activated.
**Status**: NEW.

**Request**:

```json
{
  "notes": "Reviewed -- content is borderline but acceptable with disclaimers."  // string, optional
}
```

**Response** (200):

```json
{
  "campaign_id": 12,
  "screening_status": "approved",
  "message": "Campaign approved for activation."
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Campaign is not in `flagged` screening status |
| 404 | Campaign not found |

---

### POST /api/admin/flagged-campaigns/{campaign_id}/reject

**Auth**: admin
**Description**: Reject a flagged campaign. The campaign cannot be activated and the company is notified.
**Status**: NEW.

**Request**:

```json
{
  "reason": "Campaign promotes guaranteed financial returns, which violates content policy."  // string, required
}
```

**Response** (200):

```json
{
  "campaign_id": 12,
  "screening_status": "rejected",
  "message": "Campaign rejected. Company will be notified."
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Success |
| 400 | Campaign is not in `flagged` screening status |
| 404 | Campaign not found |

**Notes**:
- Rejected campaigns are moved to `cancelled` status.
- The company's budget for the campaign is refunded.
- The rejection `reason` is stored and visible to the company.

---

## 8. Content Screening Endpoint

### POST /api/internal/screen-campaign

**Auth**: none (internal only -- should be restricted to server-to-server calls in production)
**Description**: Automated content screening for prohibited categories. Called internally when a campaign is created or its brief/content_guidance is updated.
**Status**: NEW.

**Request**:

```json
{
  "campaign_id": 12,
  "title": "Amazing Returns Guaranteed",
  "brief": "Get 500% returns with our revolutionary trading bot...",
  "content_guidance": "Emphasize the guaranteed returns angle."
}
```

**Response** (200):

```json
{
  "campaign_id": 12,
  "flagged": true,
  "flags": [
    {
      "category": "financial_fraud",
      "matched_phrases": ["guaranteed returns", "500% returns"],
      "severity": "high"
    }
  ],
  "screening_status": "flagged"
}
```

If not flagged:

```json
{
  "campaign_id": 12,
  "flagged": false,
  "flags": [],
  "screening_status": "approved"
}
```

**Status codes**:

| Code | When |
|------|------|
| 200 | Screening complete |
| 404 | Campaign not found |

**Notes**:
- Prohibited categories: adult/sexually explicit, gambling, drugs/controlled substances, weapons, financial fraud/scams/get-rich-quick, hate speech/discrimination.
- Uses keyword matching. Flagged campaigns require admin review via `POST /api/admin/flagged-campaigns/{id}/approve` or `reject`.
- This endpoint is called automatically by the server when `POST /api/company/campaigns` or `PATCH /api/company/campaigns/{id}` modifies the `brief` or `content_guidance`.
- In production, this should be restricted to internal calls only (not exposed to public API).

---

## 9. Company Web Pages (Server-Rendered)

Authentication via `company_token` cookie (JWT). Unauthenticated requests redirect to `/company/login`.

### Existing Pages (updated for v2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/company/login` | Login page with register form |
| POST | `/company/login` | Submit login (email + password). Sets `company_token` cookie. |
| POST | `/company/register` | Submit registration (name + email + password). Sets cookie. |
| GET | `/company/logout` | Clear cookie, redirect to login |
| GET | `/company/` | Campaigns list with aggregate stats. **Updated**: includes invitation stats badges. |
| GET | `/company/campaigns/new` | Create campaign form. **Updated**: AI wizard step-by-step flow. |
| POST | `/company/campaigns/new` | Submit campaign. **Updated**: accepts `company_urls`, wizard data. |
| GET | `/company/campaigns/{id}` | Campaign detail. **Updated**: per-user performance table, invitation status breakdown, budget progress bar. |
| POST | `/company/campaigns/{id}/status` | Change campaign status (form field: `new_status`). |
| GET | `/company/billing` | Billing page with balance and allocations. **Updated**: budget alert indicators. |
| POST | `/company/billing/topup` | Add funds (form field: `amount`). |
| GET | `/company/settings` | Company profile settings. |
| POST | `/company/settings` | Update company name and email. |

### New Pages

| Method | Path | Description |
|--------|------|-------------|
| GET | `/company/campaigns/{id}/edit` | Edit campaign form (pre-filled). Shows which fields are editable based on campaign status. |
| POST | `/company/campaigns/{id}/edit` | Submit campaign edits. |
| POST | `/company/campaigns/{id}/clone` | Clone campaign (form with optional overrides for title, budget, dates). |
| POST | `/company/campaigns/{id}/delete` | Delete campaign (only draft/cancelled). |
| POST | `/company/campaigns/{id}/budget-topup` | Increase campaign budget (form field: `amount`). |
| GET | `/company/campaigns/{id}/export` | Download campaign report (query param: `format=csv` or `format=pdf`). |

---

## 10. Admin Web Pages (Server-Rendered)

Authentication via `admin_token` cookie. Login with admin password (env var `ADMIN_PASSWORD`, default `"admin"`). Unauthenticated requests redirect to `/admin/login`.

### Existing Pages (unchanged)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/login` | Admin login page |
| POST | `/admin/login` | Submit admin password. Sets `admin_token` cookie. |
| GET | `/admin/logout` | Clear cookie, redirect to login |
| GET | `/admin/` | Overview: user/campaign/post/payout counts, platform revenue, recent activity |
| GET | `/admin/users` | User management with optional `?status=` filter. Trust score, mode, platforms, earnings. |
| POST | `/admin/users/{id}/suspend` | Suspend user, redirect to users page |
| POST | `/admin/users/{id}/unsuspend` | Unsuspend user, redirect to users page |
| GET | `/admin/campaigns` | All campaigns with company name, user count, post count |
| GET | `/admin/fraud` | Fraud detection: recent penalties |
| POST | `/admin/fraud/run-check` | Run anomaly/deletion fraud checks, display results inline |
| GET | `/admin/payouts` | Payouts: pending/paid/failed totals, payout history |
| POST | `/admin/payouts/run-billing` | Trigger billing cycle manually |
| POST | `/admin/payouts/run-payout` | Trigger payout cycle via Stripe Connect |

### New Pages

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/review-queue` | Campaign review queue: flagged campaigns from automated screening |
| POST | `/admin/review-queue/{id}/approve` | Approve flagged campaign |
| POST | `/admin/review-queue/{id}/reject` | Reject flagged campaign (form field: `reason`) |

---

## 11. Utility Endpoints

### GET /health

**Auth**: none
**Description**: Health check.
**Status**: Existing -- unchanged.

**Response** (200):

```json
{"status": "ok"}
```

---

### GET /api/version

**Auth**: none
**Description**: Version and auto-update info for the desktop app.
**Status**: Existing -- unchanged.

**Response** (200):

```json
{
  "version": "0.1.0",
  "download_url": "",
  "changelog": "Initial release"
}
```

---

## Schemas Reference

### Enums and Constants

**Assignment Status Values** (lifecycle order):

```
pending_invitation → accepted → content_generated → posted → metrics_collected → paid
                   ↘ rejected
                   ↘ expired (auto, after 3 days)
                   ↘ skipped (user declined to post after accepting)
```

**Campaign Status Values**:

```
draft → active → paused → active (resume)
     ↘ cancelled       ↘ cancelled
                active → completed
                       ↘ cancelled
```

**Campaign Screening Status Values**:

```
pending → approved
        ↘ flagged → approved (admin)
                  ↘ rejected (admin)
```

**User Status Values**: `active`, `suspended`, `banned`

**Content Mode Values**: `repost` (1.0x), `ai_generated` (1.5x), `user_customized` (2.0x)

**Operating Mode Values**: `full_auto`, `semi_auto`, `manual`

**Platform Values**: `x`, `linkedin`, `facebook`, `reddit`, `tiktok`, `instagram`

**Audience Region Values**: `us`, `uk`, `india`, `eu`, `latam`, `sea`, `global`

**Niche Tag Values**: `finance`, `tech`, `beauty`, `fashion`, `fitness`, `gaming`, `food`, `travel`, `education`, `lifestyle`, `business`, `health`, `entertainment`, `crypto`

---

### PayoutRules

```json
{
  "rate_per_1k_impressions": 0.50,    // float, default 0.50
  "rate_per_like": 0.01,              // float, default 0.01
  "rate_per_repost": 0.05,            // float, default 0.05
  "rate_per_click": 0.10              // float, default 0.10
}
```

---

### Targeting

```json
{
  "min_followers": {"x": 500, "linkedin": 200},  // object, default {}
  "niche_tags": ["trading", "finance"],           // string[], default []
  "required_platforms": ["x"],                    // string[], default []
  "target_regions": ["us", "uk"]                  // string[], default [] -- NEW
}
```

---

### ScrapedProfile (per-platform, within `scraped_profiles`)

```json
{
  "display_name": "Trader Pro",                   // string
  "bio": "Quantitative trading | Market analysis",  // string
  "profile_picture_url": "https://...",           // string
  "follower_count": 1250,                         // int
  "following_count": 340,                         // int
  "avg_engagement_rate": 3.2,                     // float (percentage)
  "posting_frequency_per_week": 12.5,             // float
  "recent_post_count": 45,                        // int (last 30-60 days)
  "scraped_at": "2026-03-20T14:00:00Z"           // datetime (ISO 8601)
}
```

---

### CampaignCreate (updated)

```json
{
  "title": "string",                              // required
  "brief": "string",                              // required
  "assets": {},                                   // optional, default {}
  "budget_total": 500.00,                         // required, minimum 50.00
  "payout_rules": { PayoutRules },                // required
  "targeting": { Targeting },                     // optional, default no filters
  "content_guidance": "string",                   // optional
  "penalty_rules": {},                            // optional, default {}
  "start_date": "datetime",                       // required (ISO 8601)
  "end_date": "datetime",                         // required (ISO 8601)
  "company_urls": ["string"],                     // optional -- NEW
  "ai_generated_brief": false                     // optional, default false -- NEW
}
```

---

### CampaignUpdate (updated)

```json
{
  "title": "string",                              // optional
  "brief": "string",                              // optional
  "assets": {},                                   // optional
  "content_guidance": "string",                   // optional
  "payout_rules": { PayoutRules },                // optional -- NEW
  "end_date": "datetime",                         // optional -- NEW
  "status": "string"                              // optional (transition rules apply)
}
```

---

### CampaignResponse (updated)

```json
{
  "id": 1,                                        // int
  "company_id": 1,                                // int
  "title": "string",                              // string
  "brief": "string",                              // string
  "assets": {},                                   // object
  "budget_total": 500.00,                         // float
  "budget_remaining": 312.50,                     // float
  "payout_rules": {},                             // object
  "targeting": {},                                // object
  "content_guidance": "string or null",           // string | null
  "status": "active",                             // string
  "screening_status": "approved",                 // string -- NEW
  "start_date": "datetime",                       // datetime
  "end_date": "datetime",                         // datetime
  "created_at": "datetime",                       // datetime
  "invitation_stats": {                           // object -- NEW (in list/detail views)
    "total_invited": 47,
    "accepted": 12,
    "rejected": 8,
    "expired": 15,
    "pending": 12
  }
}
```

---

### InvitationBrief (NEW -- returned by `GET /api/campaigns/invitations`)

```json
{
  "invitation_id": 14,                            // int (same as assignment_id)
  "assignment_id": 22,                            // int
  "campaign_id": 5,                               // int
  "title": "string",                              // string
  "brief": "string",                              // string
  "assets": {},                                   // object
  "content_guidance": "string or null",           // string | null
  "payout_rules": {},                             // object
  "estimated_earnings": {"low": 5.00, "high": 25.00},  // object
  "required_platforms": ["x"],                    // string[]
  "deadline": "datetime",                         // datetime (campaign end_date)
  "expires_at": "datetime",                       // datetime (invitation expiry, +3 days)
  "invited_at": "datetime"                        // datetime
}
```

---

### ActiveCampaignBrief (NEW -- returned by `GET /api/campaigns/active`)

```json
{
  "assignment_id": 22,                            // int
  "campaign_id": 5,                               // int
  "title": "string",                              // string
  "brief": "string",                              // string
  "assets": {},                                   // object
  "content_guidance": "string or null",           // string | null
  "payout_rules": {},                             // object
  "payout_multiplier": 1.5,                       // float
  "assignment_status": "accepted",                // string
  "campaign_status": "active",                    // string
  "campaign_updated_at": "datetime",              // datetime
  "requires_re_review": false,                    // bool
  "start_date": "datetime",                       // datetime
  "end_date": "datetime"                          // datetime
}
```

---

### UserProfileUpdate (updated)

```json
{
  "platforms": {},                                // optional
  "follower_counts": {},                          // optional
  "niche_tags": ["string"],                       // optional
  "ai_detected_niches": ["string"],               // optional -- NEW
  "audience_region": "us",                        // optional
  "mode": "semi_auto",                            // optional
  "device_fingerprint": "string",                 // optional
  "scraped_profiles": {}                          // optional -- NEW
}
```

---

### UserProfileResponse (updated)

```json
{
  "id": 1,                                        // int
  "email": "string",                              // string
  "platforms": {},                                // object
  "follower_counts": {},                          // object
  "niche_tags": ["string"],                       // string[]
  "ai_detected_niches": ["string"],               // string[] -- NEW
  "audience_region": "us",                        // string
  "trust_score": 75,                              // int
  "mode": "semi_auto",                            // string
  "earnings_balance": 42.50,                      // float
  "total_earned": 187.25,                         // float
  "status": "active",                             // string
  "scraped_profiles": {}                          // object -- NEW
}
```

---

### EarningsSummary (updated)

```json
{
  "total_earned": 187.25,                         // float
  "current_balance": 42.50,                       // float
  "pending": 12.80,                               // float -- NOW REAL
  "per_campaign": [                               // CampaignEarning[] -- NOW REAL
    {
      "campaign_id": 5,
      "campaign_title": "string",
      "posts": 4,
      "impressions": 45200,
      "engagement": 382,
      "earned": 28.50,
      "status": "paid"                            // pending | calculated | paid
    }
  ],
  "per_platform": {                               // object -- NEW
    "x": 125.00,
    "linkedin": 42.25
  },
  "payout_history": [                             // PayoutRecord[] -- NEW
    {
      "id": 3,
      "amount": 50.00,
      "status": "paid",
      "requested_at": "datetime",
      "paid_at": "datetime or null"
    }
  ]
}
```

---

### PostCreate, PostBatchCreate, MetricSubmission, MetricBatchSubmit

Unchanged from v1. See [API_REFERENCE.md](./API_REFERENCE.md) for full details.

---

## Migration Notes (v1 to v2)

### Breaking Changes

1. **`GET /api/campaigns/mine` is replaced by `GET /api/campaigns/invitations`**. The old endpoint created assignments on poll. The new endpoint only returns pre-matched invitations with `pending_invitation` status. Users must explicitly accept or reject.

2. **Assignment status lifecycle changed**. New initial status is `pending_invitation` (was `assigned`). New statuses added: `accepted`, `rejected`, `expired`. The `assigned` status is removed.

3. **`CampaignResponse` has new required fields**: `screening_status`, `invitation_stats`. Clients must handle these or ignore unknown fields.

4. **`UserProfileResponse` has new fields**: `scraped_profiles`, `ai_detected_niches`. These are additive (empty by default) but clients parsing strictly may need updates.

### Non-Breaking Additions

- All new endpoints (`/invitations`, `/active`, `/clone`, `/export`, `/reach-estimate`, `/ai-wizard`, `/budget-topup`, `/payout`, flagged campaign endpoints) are new paths that do not conflict with existing ones.
- New optional fields on `CampaignCreate` (`company_urls`, `ai_generated_brief`) and `CampaignUpdate` (`payout_rules`, `end_date`) are backwards-compatible.
- `Targeting` schema gains optional `target_regions` field (defaults to `[]`).

### Database Schema Changes Required

1. **`users` table**: Add columns `scraped_profiles` (JSON, default `{}`), `ai_detected_niches` (JSON, default `[]`).
2. **`campaigns` table**: Add column `screening_status` (String, default `"pending"`).
3. **`campaign_assignments` table**: Add column `expires_at` (DateTime, nullable), add column `requires_re_review` (Boolean, default `false`). Update `status` enum to include `pending_invitation`, `accepted`, `rejected`, `expired`.
4. **`targeting` JSON schema**: Add `target_regions` key.
