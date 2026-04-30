# Amplifier -- API Reference

Base URL: `http://localhost:8000` (local dev) — **production server is LIVE at `https://api.pointcapitalis.com`** (Hostinger KVM VPS, Mumbai, since 2026-04-25). See `docs/HOSTING-DECISION-RECORD.md` for infrastructure details.

## Authentication

All protected endpoints require: `Authorization: Bearer {jwt_token}`

JWT payload: `{sub: user_id, type: "user"|"company", exp: timestamp}`

Company web pages use cookie-based auth: `company_token` cookie with JWT.
Admin pages use: `admin_token` cookie matching `ADMIN_PASSWORD` env var.

---

## Auth Endpoints

| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| POST | `/api/auth/register` | `{email, password}` | `{access_token, token_type}` |
| POST | `/api/auth/login` | `{email, password}` | `{access_token, token_type}` |
| POST | `/api/auth/company/register` | `{name, email, password}` | `{access_token, token_type}` |
| POST | `/api/auth/company/login` | `{email, password}` | `{access_token, token_type}` |

---

## User Endpoints (requires user JWT)

| Method | Endpoint | Purpose | Body/Params |
|--------|----------|---------|-------------|
| GET | `/api/users/me` | Get profile | -- |
| PATCH | `/api/users/me` | Update profile | `{platforms, follower_counts, niche_tags, audience_region, mode, scraped_profiles}` |
| GET | `/api/users/me/earnings` | Earnings summary | -- |
| POST | `/api/users/me/payout` | Request withdrawal (min $10). Returns 400 "Stripe Connect bank account not linked" when `user.stripe_account_id` is null. | `{amount}` |

---

## Campaign Endpoints

### User-facing (requires user JWT)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/campaigns/mine` | Poll for matched campaigns (triggers matching) |
| GET | `/api/campaigns/invitations` | Get pending invitations (auto-expires stale) |
| POST | `/api/campaigns/invitations/{id}/accept` | Accept invitation (tier-based limit: seedling 3, grower 10, amplifier unlimited) |
| POST | `/api/campaigns/invitations/{id}/reject` | Reject invitation |
| GET | `/api/campaigns/active` | Get accepted + active campaigns |
| PATCH | `/api/campaigns/assignments/{id}` | Update assignment status |

### Company-facing (requires company JWT)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/company/campaigns` | Create campaign |
| GET | `/api/company/campaigns` | List company's campaigns |
| GET | `/api/company/campaigns/{id}` | Campaign detail + stats |
| PATCH | `/api/company/campaigns/{id}` | Edit campaign (increments version) |
| DELETE | `/api/company/campaigns/{id}` | Delete draft (refunds budget) |
| POST | `/api/company/campaigns/{id}/budget-topup` | Add budget |
| POST | `/api/company/campaigns/{id}/clone` | Clone campaign as new draft |
| GET | `/api/company/campaigns/{id}/export` | Export campaign report as CSV |
| GET | `/api/company/campaigns/{id}/reach-estimate` | Reach estimate for existing campaign |
| POST | `/api/company/campaigns/ai-wizard` | AI generates full campaign draft from wizard answers |
| POST | `/api/company/campaigns/reach-estimate` | Estimate reach for targeting criteria |

---

## Posts & Metrics (requires user JWT)

| Method | Endpoint | Purpose | Body |
|--------|----------|---------|------|
| POST | `/api/posts` | Register posted URLs (batch) | `[{assignment_id, platform, post_url, content_hash, posted_at}]` |
| POST | `/api/metrics` | Submit scraped metrics (batch, triggers billing) | `[{post_id, impressions, likes, reposts, comments, clicks, scraped_at, is_final}]` |

---

## Admin Endpoints (requires admin cookie)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/admin/users` | List users (filter by status) |
| POST | `/api/admin/users/{id}/suspend` | Suspend user |
| POST | `/api/admin/users/{id}/unsuspend` | Restore user |
| GET | `/api/admin/stats` | System stats |
| GET | `/api/admin/flagged-campaigns` | List flagged campaigns (filter by status) |
| POST | `/api/admin/flagged-campaigns/{id}/approve` | Approve flagged campaign |
| POST | `/api/admin/flagged-campaigns/{id}/reject` | Reject flagged campaign |

---

## Company Web Pages (cookie auth)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/company/login` | Login page |
| POST | `/company/login` | Submit login |
| POST | `/company/register` | Submit registration |
| GET | `/company/` | Campaign list dashboard |
| GET | `/company/campaigns/new` | Campaign wizard (requires $50+ balance) |
| POST | `/company/campaigns/ai-generate` | AI campaign generation (JSON) |
| POST | `/company/campaigns/upload-asset` | Upload image/file to Supabase Storage |
| POST | `/company/campaigns/new` | Submit campaign form |
| GET | `/company/campaigns/{id}` | Campaign detail |
| POST | `/company/campaigns/{id}/status` | Update campaign status |
| POST | `/company/campaigns/{id}/edit` | Edit campaign content |
| POST | `/company/campaigns/{id}/topup` | Top up campaign budget |
| GET | `/company/billing` | Billing page |
| POST | `/company/billing/topup` | Submit balance top-up |
| GET | `/company/billing/success` | Stripe payment success callback |
| GET | `/company/stats` | Statistics page |
| GET | `/company/settings` | Company settings |
| POST | `/company/settings` | Update company settings |
| GET | `/company/logout` | Logout |

---

## Admin Web Pages (cookie auth)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/login` | Admin login |
| POST | `/admin/login` | Submit password |
| GET | `/admin/` | Overview dashboard |
| GET | `/admin/logout` | Logout |
| GET | `/admin/users` | User management |
| POST | `/admin/users/{id}/suspend` | Suspend user |
| POST | `/admin/users/{id}/unsuspend` | Unsuspend user |
| GET | `/admin/campaigns` | Campaign management |
| GET | `/admin/fraud` | Fraud detection dashboard |
| POST | `/admin/fraud/run-check` | Run fraud detection check |
| GET | `/admin/payouts` | Payout management |
| POST | `/admin/payouts/run-billing` | Run billing cycle |
| POST | `/admin/payouts/run-payout` | Run payout cycle |
| POST | `/admin/financial/run-earning-promotion` | Promotes pending earnings to available after 7-day hold period |
| POST | `/admin/financial/run-payout-processing` | Auto-processes payouts via Stripe Connect (marks as paid in test mode) |
| GET | `/admin/platform-stats` | Per-platform statistics |
| GET | `/admin/review-queue` | Flagged campaigns review queue |
| POST | `/admin/review-queue/{id}/approve` | Approve flagged campaign |
| POST | `/admin/review-queue/{id}/reject` | Reject flagged campaign |

---

## Billing Formula

```
gross_earning = (impressions / 1000 * rate_per_1k_impressions)
              + (likes * rate_per_like)
              + (reposts * rate_per_repost)

net_earning = gross_earning * (1 - platform_cut_percent / 100)
```

Default platform cut: 20%. Configurable via `PLATFORM_CUT_PERCENT` env var.
Budget capping: earnings cannot exceed campaign's `budget_remaining`.
