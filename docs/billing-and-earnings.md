# Billing and Earnings

Complete money flow from company funding through user payouts.

**Key source files**:
- `server/app/services/billing.py` -- earnings calculation and billing cycle
- `server/app/services/payments.py` -- Stripe integration for top-ups and payouts
- `server/app/routers/campaigns.py` -- budget activation and top-up API
- `server/app/models/campaign.py`, `user.py`, `payout.py`, `company.py` -- data models
- `scripts/utils/local_db.py` -- local earnings tracking on user's device

---

## Money Flow Overview

```
Company tops up balance (Stripe Checkout)
    |
    v
Company creates campaign (budget_total >= $50, status = "draft")
    |
    v
Company activates campaign
    --> company.balance -= campaign.budget_total
    --> campaign.budget_remaining = campaign.budget_total
    |
    v
Users post content --> metrics are scraped
    |
    v
Billing cycle runs (server-side, every 6 hours)
    --> For each unbilled metric:
        --> calculate_post_earnings_cents() computes in integer cents
        --> Deduct platform cut (20%)
        --> Apply tier CPM multiplier (amplifier tier = 2x)
        --> Cap to remaining budget
        --> Credit user.earnings_balance_cents
        --> Deduct from campaign.budget_remaining
        --> Create Payout record (status = "pending", available_at = now + 7 days)
    |
    v
Hold period (7 days -- EARNING_HOLD_DAYS)
    --> promote_pending_earnings() runs every 10 min
    --> Moves "pending" → "available" once available_at has passed
    --> During hold: void_earnings_for_post() can cancel if fraud detected
    |
    v
Payout cycle (when user requests or on schedule)
    --> Users with available earnings >= $10.00
    --> Stripe Transfer to user's Connect Express account
    --> Payout status: available → processing → paid|failed
```

---

## Integer Cents Storage (v2)

All money columns now use integer cents alongside legacy Numeric(12,2) columns to eliminate float rounding:

| Model | Cents Column | Legacy Column |
|-------|-------------|---------------|
| Company | `balance_cents` | `balance` |
| User | `earnings_balance_cents`, `total_earned_cents` | `earnings_balance`, `total_earned` |
| Payout | `amount_cents` | `amount` |
| Penalty | `amount_cents` | `amount` |

The billing engine calculates in cents via `calculate_post_earnings_cents()` and converts to dollars only for display.

---

## Earning Lifecycle

```
Metric billed → Payout created (status: "pending", available_at: now + 7 days)
                    |
        +-----------+-----------+
        |                       |
    7 days pass             Fraud detected
        |                       |
    "available"             "voided"
        |                   (void_earnings_for_post)
    User requests
    withdrawal
        |
    "processing"
        |
    +---+---+
    |       |
  "paid"  "failed"
```

- **`promote_pending_earnings()`** -- Background task (every 10 min). Queries all payouts where `status = 'pending'` and `available_at <= now`, moves them to `available`.
- **`void_earnings_for_post()`** -- Called during fraud detection (deleted post, fake metrics). Voids all pending payouts for a specific post before the hold period expires.

---

## Reputation Tiers

Users progress through three tiers that affect campaign limits and earnings:

| Tier | Max Campaigns | CPM Multiplier | Spot-Check Rate | Promotion Rule |
|------|---------------|----------------|-----------------|----------------|
| **Seedling** | 3 | 1x | 30% | Default for new users |
| **Grower** | 10 | 1x | 15% | 20+ successful posts |
| **Amplifier** | Unlimited | **2x** | 5% | 100+ successful posts AND trust_score >= 80 |

Auto-promotion is handled by the billing service: after each successful post, `user.successful_post_count` is incremented and tier eligibility is checked.

---

## Step 1: Company Funds Account

Companies top up their balance via Stripe Checkout.

```python
# server/app/services/payments.py
session = stripe.checkout.Session.create(
    payment_method_types=["card"],
    line_items=[{"price_data": {"currency": "usd", ...}, "quantity": 1}],
    mode="payment",
    metadata={"company_id": str(company_id)},
)
```

After successful payment, `company.balance` is incremented by the paid amount.

---

## Step 2: Campaign Budget Activation

Campaigns are created as drafts without deducting balance. Budget is deducted only on activation.

| Rule | Value |
|------|-------|
| Minimum campaign budget | $50.00 |
| Balance check | On activation: `company.balance >= campaign.budget_total` |
| Budget deduction | `company.balance -= campaign.budget_total` |
| Initial remaining | `campaign.budget_remaining = campaign.budget_total` |
| Refund on cancel | Draft campaigns: `company.balance += campaign.budget_total`. Active campaigns: `company.balance += campaign.budget_remaining` |

---

## Step 3: Payout Rules (Set by Company)

Each campaign defines its own payout rates in the `payout_rules` JSON field:

```json
{
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
}
```

All four rates are optional (default to `0` if missing).

---

## Step 4: Earnings Calculation

The billing engine in `server/app/services/billing.py` calculates earnings per metric submission.

### Formula

```
raw_earning = (impressions / 1000 * rate_per_1k_impressions)
            + (likes * rate_per_like)
            + (reposts * rate_per_repost)
            + (clicks * rate_per_click)

platform_cut = platform_cut_percent / 100.0     # default: 0.20

user_earning = raw_earning * (1 - platform_cut)
```

### Example

Given a post with 5,000 impressions, 120 likes, 15 reposts, 30 clicks and rates of $0.50/1k impressions, $0.01/like, $0.05/repost, $0.10/click:

```
raw_earning = (5000/1000 * 0.50) + (120 * 0.01) + (15 * 0.05) + (30 * 0.10)
            = 2.50 + 1.20 + 0.75 + 3.00
            = $7.45

user_earning = 7.45 * (1 - 0.20) = $5.96
```

The platform (Amplifier) keeps 20% ($1.49). The user gets $5.96.

### Budget Cost vs User Earning

The full cost to the campaign budget is the raw earning (before platform cut):

```
budget_cost = user_earning / (1 - platform_cut_percent / 100)
```

This means the company pays the full `$7.45`, of which `$5.96` goes to the user and `$1.49` goes to Amplifier.

### Tier CPM Multiplier

Users in the **amplifier** tier earn 2x CPM on all campaigns. The multiplier is applied during `calculate_post_earnings_cents()`:

```
tier_multiplier = 2.0 if user.tier == "amplifier" else 1.0
earning_cents = int(raw_earning_dollars * 100 * tier_multiplier)
```

The `payout_multiplier` field on campaign assignments is **not used** in v2 billing (kept for backward compatibility).

---

## Step 5: Budget Exhaustion

### Capping to Remaining Budget

If a billing calculation would exceed the remaining budget:

```python
if budget_cost > campaign.budget_remaining:
    budget_cost = campaign.budget_remaining
    user_earning = budget_cost * (1 - platform_cut_percent / 100)
```

### Exhaustion Actions

When `campaign.budget_remaining < $1.00`, the `budget_exhaustion_action` determines what happens:

| Action | Behavior |
|--------|----------|
| `auto_pause` | Campaign status set to `"paused"`. Company can top up budget and campaign auto-resumes. |
| `auto_complete` | Campaign status set to `"completed"`. Campaign ends permanently. |

Default is `auto_pause` (set during campaign creation).

### 80% Budget Alert

When `budget_remaining < 20% of budget_total`, the `budget_alert_sent` flag is set to `True`. This triggers a notification to the company that their budget is running low.

### Budget Top-Up

Companies can add funds to an active or paused campaign:

```python
campaign.budget_remaining += top_up_amount
campaign.budget_total += top_up_amount
```

If the campaign was paused due to budget exhaustion (`auto_pause`), it auto-resumes to `"active"`. The budget alert resets if remaining reaches >= 20% of the new total.

---

## Step 6: Deduplication

Each metric submission has a unique `metric.id`. The billing cycle tracks which metrics have already been billed:

```python
# Collect all metric IDs already referenced in existing payouts
billed_metric_ids = set()
for payout in existing_payouts:
    if "metric_id" in payout.breakdown:
        billed_metric_ids.add(payout.breakdown["metric_id"])

# Skip already-billed metrics
if metric.id in billed_metric_ids:
    continue
```

This prevents double-billing when the billing cycle runs multiple times or when the same metrics are submitted again.

---

## Step 7: Payout Records

Each billed metric creates a `Payout` record:

| Field | Value |
|-------|-------|
| `user_id` | The user who made the post |
| `campaign_id` | The campaign the post was for |
| `amount` | User earning in dollars (after platform cut) -- legacy |
| `amount_cents` | User earning in integer cents (after platform cut) -- v2 |
| `period_start` | When the post was published |
| `period_end` | When the billing cycle ran |
| `status` | `"pending"` -> `"available"` -> `"processing"` -> `"paid"` or `"failed"` (or `"voided"` during hold) |
| `available_at` | `created_at + EARNING_HOLD_DAYS` (7 days). When this earning becomes withdrawable. |
| `breakdown` | JSON: `{metric_id, post_id, platform, impressions, likes, reposts, clicks, platform_cut_pct}` |

---

## Step 8: User Payout

### Balance Accumulation

Each billing cycle credits the user (in cents for precision):

```python
user.earnings_balance_cents += earning_cents   # Held during 7-day period, then available
user.total_earned_cents += earning_cents        # Lifetime total (never decreases)
```

Legacy float columns (`earnings_balance`, `total_earned`) are updated in parallel for backward compatibility.

### Payout Cycle

The payout cycle (`run_payout_cycle`) processes all eligible users:

| Rule | Value |
|------|-------|
| Minimum threshold | `$10.00` (configurable via `MIN_PAYOUT_THRESHOLD` in server `.env`) |
| Eligibility | User has `available` payouts totaling >= threshold AND `user.status == "active"` |
| Method | Stripe Connect Express transfer |
| After payout | Available payouts moved to `processing` then `paid` |

Stripe integration requires:
1. User creates a Stripe Connect Express account via `create_user_stripe_account()`
2. User completes Stripe onboarding flow
3. Payouts are sent via `stripe.Transfer.create()` to the user's connected account

---

## Local Earnings Tracking (User App)

The user's device tracks earnings locally in the `local_earning` table (see `scripts/utils/local_db.py`).

### `get_earnings_summary()`

Returns aggregated earnings:

```python
{
    "total_earned": 125.50,   # SUM of all local_earning.amount
    "pending": 45.00,         # SUM where status = 'pending'
    "paid": 80.50,            # SUM where status = 'paid'
}
```

### `get_campaign_earnings()`

Returns per-campaign earnings with campaign titles, ordered by most recent update.

---

## User Joining Fee (Planned)

> **Status**: Under consideration -- not yet implemented. Details to be finalized before user onboarding goes live.

Planning to charge amplifiers (users) a **$200-$250 fee** to join the platform. This may be **annual** rather than one-time.

This is **on top of** the existing revenue streams:
- 20% platform cut on all earnings
- Free and paid tiers

### Open Questions

- Exact amount: $200 or $250?
- Billing cadence: one-time or annual?
- How does it interact with the existing free/paid tier system? Does paying the fee unlock a tier, or is it a separate access gate?
- Refund/cancellation policy?

---

## Server Configuration

Billing-related settings in `server/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_CUT_PERCENT` | `20` | Percentage Amplifier takes from each earning (0-100) |
| `MIN_PAYOUT_THRESHOLD` | `10.00` | Minimum USD balance required to trigger a payout |
| `STRIPE_SECRET_KEY` | (empty) | Stripe API secret key. Payments disabled if not set |

---

## Data Security

Sensitive financial data is encrypted at rest using AES-256-GCM:
- **Server-side** (`server/app/utils/crypto.py`): encrypts Stripe keys and other secrets stored in the database
- **Client-side** (`scripts/utils/crypto.py`): encrypts API keys using a machine-derived key. The `_SENSITIVE_KEYS` set in `local_db.py` (`gemini_api_key`, `mistral_api_key`, `groq_api_key`) are auto-encrypted on save and decrypted on read.
