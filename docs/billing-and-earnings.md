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
        --> Calculate raw earning from payout rates
        --> Deduct platform cut (20%)
        --> Cap to remaining budget
        --> Credit user.earnings_balance
        --> Deduct from campaign.budget_remaining
        --> Create Payout record
    |
    v
Payout cycle (when user requests or on schedule)
    --> Users with earnings_balance >= $10.00
    --> Stripe Transfer to user's Connect Express account
    --> earnings_balance reset to $0
```

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

### Payout Multiplier

The `payout_multiplier` field exists on campaign assignments for backward compatibility but is **not used** in v2 billing. Earnings are calculated purely from raw metrics and rates.

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
| `amount` | User earning (after platform cut) |
| `period_start` | When the post was published |
| `period_end` | When the billing cycle ran |
| `status` | `"pending"` (then `"processing"` -> `"paid"` or `"failed"`) |
| `breakdown` | JSON: `{metric_id, post_id, platform, impressions, likes, reposts, clicks, platform_cut_pct}` |

---

## Step 8: User Payout

### Balance Accumulation

Each billing cycle credits the user:

```python
user.earnings_balance += user_earning   # Available for withdrawal
user.total_earned += user_earning       # Lifetime total (never decreases)
```

### Payout Cycle

The payout cycle (`run_payout_cycle`) processes all eligible users:

| Rule | Value |
|------|-------|
| Minimum threshold | `$10.00` (configurable via `MIN_PAYOUT_THRESHOLD` in server `.env`) |
| Eligibility | `user.earnings_balance >= threshold` AND `user.status == "active"` |
| Method | Stripe Connect Express transfer |
| After payout | `user.earnings_balance = 0.0` |

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

## Server Configuration

Billing-related settings in `server/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_CUT_PERCENT` | `20` | Percentage Amplifier takes from each earning (0-100) |
| `MIN_PAYOUT_THRESHOLD` | `10.00` | Minimum USD balance required to trigger a payout |
| `STRIPE_SECRET_KEY` | (empty) | Stripe API secret key. Payments disabled if not set |
