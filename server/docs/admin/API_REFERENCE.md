# Amplifier Admin Dashboard — API Reference

## Authentication

All admin routes require a valid `admin_token` cookie. The cookie is set on successful login and has the value `"valid"`.

### Login
```
POST /admin/login
Content-Type: application/x-www-form-urlencoded

password=<admin_password>

Response: 303 Redirect to /admin/ (on success) or /admin/login?error=... (on failure)
Set-Cookie: admin_token=valid; HttpOnly; SameSite=Lax
```

### Logout
```
GET /admin/logout
Response: 303 Redirect to /admin/login
Deletes: admin_token cookie
```

---

## Pages (GET Routes)

### Overview
```
GET /admin/
```
No parameters. Returns the system dashboard with stats, trends, health indicators, and recent activity.

---

### Users List
```
GET /admin/users?page=1&search=&status=&sort=created_at&order=desc

Parameters:
  page     (int)    Default: 1       Page number
  search   (str)    Default: ""      Email substring match (ILIKE)
  status   (str)    Default: ""      Filter: active | suspended | banned
  sort     (str)    Default: "created_at"  Sort by: created_at | trust_score | total_earned | email
  order    (str)    Default: "desc"  Sort order: asc | desc

Pagination: 25 per page
```

### User Detail
```
GET /admin/users/{user_id}

Path Parameters:
  user_id  (int)    Required    User ID

Returns: User profile, connected platforms, niche tags, and tabbed sections
         (assignments, posts, payouts, penalties — up to 50 each)
```

---

### Companies List
```
GET /admin/companies?page=1&search=&status=&sort=created_at&order=desc

Parameters:
  page     (int)    Default: 1       Page number
  search   (str)    Default: ""      Name OR email substring match (ILIKE)
  status   (str)    Default: ""      Filter: active | suspended
  sort     (str)    Default: "created_at"  Sort by: created_at | balance | name
  order    (str)    Default: "desc"  Sort order: asc | desc

Pagination: 25 per page
```

### Company Detail
```
GET /admin/companies/{company_id}

Path Parameters:
  company_id  (int)    Required    Company ID

Returns: Company profile, stats (total/active campaigns, budget, spent),
         fund management forms, and campaigns table (up to 50)
```

---

### Campaigns List
```
GET /admin/campaigns?page=1&search=&status=&sort=created_at&order=desc

Parameters:
  page     (int)    Default: 1       Page number
  search   (str)    Default: ""      Title substring match (ILIKE)
  status   (str)    Default: ""      Filter: draft | active | paused | completed | cancelled
  sort     (str)    Default: "created_at"  Sort by: created_at | budget_total | budget_remaining | title
  order    (str)    Default: "desc"  Sort order: asc | desc

Pagination: 25 per page
```

### Campaign Detail
```
GET /admin/campaigns/{campaign_id}

Path Parameters:
  campaign_id  (int)    Required    Campaign ID

Returns: Campaign info, budget breakdown, company info, and tabbed sections
         (brief, assigned users, posts with metrics, configuration)
```

---

### Financial Dashboard
```
GET /admin/financial?page=1&status=&search=

Parameters:
  page     (int)    Default: 1       Page number for transaction table
  status   (str)    Default: ""      Payout status filter: pending | paid | failed
  search   (str)    Default: ""      User email substring match

Pagination: 25 per page
```

---

### Fraud & Trust Center
```
GET /admin/fraud?page=1&search=

Parameters:
  page     (int)    Default: 1       Page number for penalties table
  search   (str)    Default: ""      User email substring match

Pagination: 25 per page
```

---

### Analytics
```
GET /admin/analytics
```
No parameters. Returns platform breakdown and top performing posts.

---

### Review Queue
```
GET /admin/review-queue?tab=pending

Parameters:
  tab      (str)    Default: "pending"    Tab: pending | reviewed
```

---

### Settings
```
GET /admin/settings
```
No parameters. Returns read-only system configuration.

---

### Audit Log
```
GET /admin/audit-log?page=1&action=&target_type=

Parameters:
  page         (int)    Default: 1       Page number
  action       (str)    Default: ""      Action type filter (e.g., "user_suspended")
  target_type  (str)    Default: ""      Target type filter: user | company | campaign | penalty | system

Pagination: 30 per page
```

---

## Actions (POST Routes)

All POST routes redirect back to the relevant page on completion (303 redirect). All mutations are audit-logged.

### User Actions

```
POST /admin/users/{user_id}/suspend
  Precondition: user.status == "active"
  Effect: Sets status to "suspended"
  Audit: user_suspended (email)

POST /admin/users/{user_id}/unsuspend
  Precondition: user.status == "suspended"
  Effect: Sets status to "active"
  Audit: user_unsuspended (email)

POST /admin/users/{user_id}/ban
  Precondition: user.status != "banned"
  Effect: Sets status to "banned"
  Audit: user_banned (email)

POST /admin/users/{user_id}/adjust-trust
  Content-Type: application/x-www-form-urlencoded
  Body: new_score=<0-100>
  Effect: Updates trust_score (clamped to 0-100)
  Audit: trust_adjusted (email, old_score, new_score)
  Redirect: /admin/users/{user_id}
```

### Company Actions

```
POST /admin/companies/{company_id}/add-funds
  Content-Type: application/x-www-form-urlencoded
  Body: amount=<float>
  Precondition: amount > 0
  Effect: Increments company.balance by amount
  Audit: company_funds_added (name, amount, new_balance)

POST /admin/companies/{company_id}/deduct-funds
  Content-Type: application/x-www-form-urlencoded
  Body: amount=<float>
  Precondition: amount > 0
  Effect: Decrements company.balance (min 0)
  Audit: company_funds_deducted (name, amount, new_balance)

POST /admin/companies/{company_id}/suspend
  Precondition: company.status == "active"
  Effect: Sets status to "suspended" + pauses all active campaigns
  Audit: company_suspended (name, campaigns_paused)

POST /admin/companies/{company_id}/unsuspend
  Precondition: company.status == "suspended"
  Effect: Sets status to "active"
  Audit: company_unsuspended (name)
```

### Campaign Actions

```
POST /admin/campaigns/{campaign_id}/pause
  Precondition: campaign.status == "active"
  Effect: Sets status to "paused"
  Audit: campaign_paused (title)

POST /admin/campaigns/{campaign_id}/resume
  Precondition: campaign.status == "paused"
  Effect: Sets status to "active"
  Audit: campaign_resumed (title)

POST /admin/campaigns/{campaign_id}/cancel
  Precondition: campaign.status in ("active", "paused", "draft")
  Effect: Sets status to "cancelled"
          Refunds budget_remaining to company.balance
          Sets campaign.budget_remaining = 0
  Audit: campaign_cancelled (title, refunded)
```

### Financial Actions

```
POST /admin/financial/run-billing
  Effect: Calls run_billing_cycle(db) from app.services.billing
          Processes posts with final metrics → creates Payout records
  Audit: billing_cycle_run (posts_processed, total_earned, total_budget_deducted)
  Response: Re-renders financial page with success message

POST /admin/financial/run-payout
  Effect: Calls run_payout_cycle(db) from app.services.payments
          Processes pending payouts via Stripe (or test mode)
  Audit: payout_cycle_run (users_paid, total_paid, failures)
  Response: Re-renders financial page with success message
```

### Trust & Fraud Actions

```
POST /admin/fraud/run-check
  Effect: Calls run_trust_check(db) from app.services.trust
          Detects metrics anomalies and deletion fraud
  Audit: trust_check_run (anomalies count, deletions count)
  Response: Re-renders fraud page with check results

POST /admin/fraud/penalties/{penalty_id}/approve-appeal
  Precondition: penalty.appealed == True AND appeal_result IS NULL
  Effect: Sets appeal_result = "upheld"
          Restores 10 trust points to user (clamped to 100)
  Audit: appeal_approved (user_id, reason)

POST /admin/fraud/penalties/{penalty_id}/deny-appeal
  Precondition: penalty.appealed == True AND appeal_result IS NULL
  Effect: Sets appeal_result = "denied"
  Audit: appeal_denied (user_id, reason)
```

### Review Queue Actions

```
POST /admin/review-queue/{campaign_id}/approve
  Precondition: campaign.screening_status == "flagged"
  Effect: Updates ContentScreeningLog (reviewed_by_admin = True, review_result = "approved")
          Sets campaign.screening_status = "approved"
  Audit: review_approved (title)

POST /admin/review-queue/{campaign_id}/reject
  Content-Type: application/x-www-form-urlencoded
  Body: notes=<rejection reason>  (default: "Rejected by admin")
  Precondition: campaign.screening_status == "flagged"
  Effect: Updates ContentScreeningLog (reviewed, result = "rejected", notes)
          Sets campaign.screening_status = "rejected", status = "cancelled"
          Refunds budget_remaining to company.balance
  Audit: review_rejected (title, notes)
```

---

## Audit Log Actions Reference

| Action | Target Type | Details Fields |
|--------|-------------|----------------|
| `user_suspended` | user | email |
| `user_unsuspended` | user | email |
| `user_banned` | user | email |
| `trust_adjusted` | user | email, old_score, new_score |
| `company_funds_added` | company | name, amount, new_balance |
| `company_funds_deducted` | company | name, amount, new_balance |
| `company_suspended` | company | name, campaigns_paused |
| `company_unsuspended` | company | name |
| `campaign_paused` | campaign | title |
| `campaign_resumed` | campaign | title |
| `campaign_cancelled` | campaign | title, refunded |
| `review_approved` | campaign | title |
| `review_rejected` | campaign | title, notes |
| `appeal_approved` | penalty | user_id, reason |
| `appeal_denied` | penalty | user_id, reason |
| `billing_cycle_run` | system | posts_processed, total_earned, total_budget_deducted |
| `payout_cycle_run` | system | users_paid, total_paid, failures |
| `trust_check_run` | system | anomalies, deletions |

---

## Database Schema (Admin-Specific Tables)

### audit_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| action | VARCHAR(50) | Action identifier |
| target_type | VARCHAR(30) | Entity type |
| target_id | INTEGER | Entity ID (0 for system actions) |
| details | JSON | Context dict |
| admin_ip | VARCHAR(45) | Nullable |
| created_at | DATETIME(tz) | Server default: now() |

### content_screening_logs
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| campaign_id | INTEGER FK UNIQUE | References campaigns(id) |
| flagged | BOOLEAN | Default: false |
| flagged_keywords | JSON | Default: [] |
| screening_categories | JSON | Default: [] |
| reviewed_by_admin | BOOLEAN | Default: false |
| review_result | VARCHAR(20) | Nullable. approved or rejected |
| review_notes | TEXT | Nullable |
| created_at | DATETIME(tz) | Server default: now() |

### companies (modified)
| Column | Type | Notes |
|--------|------|-------|
| status | VARCHAR(20) | Default: "active". Values: active, suspended |
