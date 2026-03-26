# Amplifier — Future Features

Deferred features that are designed but not yet implemented. The backend/model support exists — just needs UI and tracking integration.

## Per-Click Payout Rate

**Status**: Backend ready, UI removed
**Why deferred**: Can't track link clicks. Metric scraping reads public engagement counts (impressions, likes, reposts, comments) via Playwright. Click data requires platform analytics API access or UTM link tracking.

**What exists**:
- `Campaign.payout_rules["rate_per_click"]` field in the model (defaults to $0.10)
- Billing calculation includes clicks: `clicks * rate_per_click`
- Form parameter `rate_per_click` accepted on campaign create/edit

**To enable**:
1. Generate UTM-tracked short links for each campaign + creator combo
2. Host a redirect service (or use Bitly/short.io API) to count clicks
3. Report click counts in metric scraping
4. Re-add "Per Click ($)" field to campaign wizard Step 4
