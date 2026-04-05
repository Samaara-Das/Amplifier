# Amplifier — Remaining Work (Complete Task Specification)

**Date**: April 4, 2026
**Status**: 27 of 80 tasks done. 53 remaining.
**Current state**: Core loop built but unverified. v2/v3 upgrade sprint completed (JSON posting engine, financial safety, AI abstraction, image generation, reputation tiers). No automated tests. No real payments. URL capture broken on 3/4 platforms.

---

## How This Document Is Organized

5 tiers, from "must work before anyone uses this" to "growth features."

- **Tier 1**: Core loop verification — the code exists, never tested E2E
- **Tier 2**: Product gaps — things the SLC spec requires that are missing or broken
- **Tier 3**: Data integrity, testing, documentation
- **Tier 4**: Confirmed feature builds from FUTURE.md
- **Tier 5**: UX polish, admin verification, compliance
- **Launch tasks**: Stripe integration, Mac support, packaging, landing page

Each task includes its task-master ID, priority, dependencies, and full description.

---

## Tier 1: Core Loop Must Work

The money loop: company pays → user posts → metrics scraped → billing runs → user earns. Every task here verifies one link in this chain. Nothing else matters until these all pass end-to-end.

---

### Task #28 — Fix URL Capture + Verify Scheduled Posting
**Status**: In-progress (paused since Session 23)
**Priority**: High
**Depends on**: #27 (done)

#### What it is
Posting works on all 4 platforms but URL capture fails on 3 of 4. Without a real post URL, metric scraping cannot revisit the post and billing cannot run. This task fixes URL capture and then verifies the full posting pipeline in both semi-auto and full-auto modes.

#### Current state
- **Posting engine**: `scripts/post.py` line 316 `post_to_platform()` is the unified entry point. It calls `post_via_script()` (line 179) which loads JSON scripts from `config/scripts/` and runs them through `scripts/engine/script_executor.py` `ScriptExecutor.execute()` (line 63). Falls back to legacy hardcoded functions via `_LEGACY_PLATFORM_POSTERS`.
- **URL capture**: `_handle_extract_url()` in `script_executor.py` (line 307-325) tries to find a target element's `href`, falls back to `page.url`. The scripts define extract_url steps:
  - **X** (`config/scripts/x_post.json` line 133-144): Navigates to profile, finds `article[data-testid='tweet'] a[href*='/status/']`. Works 3/3.
  - **LinkedIn** (`config/scripts/linkedin_post.json` line 99-110): Waits 30s for `a:has-text('View post')` in a success dialog. Fails — dialog may not appear for text-only posts.
  - **Facebook** (`config/scripts/facebook_post.json` line 117-120): Uses `page.url` after navigating to `facebook.com/me`. Returns profile URL, not post URL.
  - **Reddit** (`config/scripts/reddit_post.json` line 123-126): Uses `page.url` after a 10s wait. Fails because redirect to `/submitted/?created=` is not detected.
- **Scheduling**: `scripts/utils/post_scheduler.py` `get_due_posts()` (line 331) returns queued posts where `scheduled_at <= now`. `execute_scheduled_post()` (line 374) runs the post, creates a `local_post` record via `add_post()`, and handles URL-less posts with status `posted_no_url`.
- **Background agent**: `scripts/background_agent.py` `execute_due_posts()` (line 329) checks every 60s, marks posts as `posting` to prevent duplicates, syncs to server via `report_posts()`.
- **Session 23 test results**: 0 delivery failures across all 4 platforms. Problem is exclusively URL capture.

#### What to implement

**1. Fix LinkedIn URL capture** — Edit `config/scripts/linkedin_post.json`:
- After the existing `extract_url_dialog` step (line 99), add a fallback step: navigate to `https://www.linkedin.com/in/me/recent-activity/all/`, wait 3s, then extract `href` from `a[href*="/feed/update/"]` (first match = most recent post).
- Make the original dialog step non-critical (add `"optional": true` field to `ScriptStep` model in `scripts/engine/script_parser.py` and skip non-critical failures in `script_executor.py` `_run_step_with_recovery()`).

**2. Fix Facebook URL capture** — Edit `config/scripts/facebook_post.json`:
- After posting, navigate to `https://www.facebook.com/me`, wait 3s, look for the first `a[href*="/posts/"]` or `a[href*="/permalink/"]` link in the feed. These contain the actual post permalink.
- Fallback: use `https://www.facebook.com/me` (current behavior) since Facebook consistently blocks post URL extraction.

**3. Fix Reddit URL capture** — Edit `config/scripts/reddit_post.json`:
- Replace the bare `wait` + `extract_url` steps (lines 117-126) with: a `wait_and_verify` step that polls `page.url` for up to 15s looking for `/comments/` in the URL. Reddit redirects from `/submit` to `/r/{subreddit}/comments/{id}/` on success.
- Add fallback: navigate to `https://www.reddit.com/user/{reddit_username}/submitted/`, wait 2s, extract `href` from the first `a[href*="/comments/"]`.

**4. Support optional steps in ScriptExecutor**:
- Add `optional: bool = False` field to `ScriptStep` in `scripts/engine/script_parser.py` (around line 30-50 where the dataclass is defined).
- In `script_executor.py` `execute()` method (line 63-88), when a step fails and `step.optional is True`, log a warning but continue instead of returning `ExecutionResult(success=False)`.

**5. Verify both posting modes**:
- Semi-auto: Generate content via background agent, review drafts on dashboard at `localhost:5222/campaigns/{id}`, approve, verify post appears on platform and URL is captured.
- Full-auto: Set mode to `full_auto` in settings, verify `generate_daily_content()` in `background_agent.py` (line 293) auto-approves and schedules, and posts execute without intervention.

#### How it connects
- `post_url` flows into `local_post.post_url` → synced to server `Post.post_url` via `report_posts()` in `server_client.py` (line 203)
- `metric_scraper.py` `get_posts_for_scraping()` filters `WHERE lp.post_url IS NOT NULL` (local_db.py line 452) — no URL = no metrics = no billing
- `post_schedule.status` values (`posted`, `posted_no_url`, `failed`) drive the Posts tab UI and retry logic

#### Verification criteria
1. Run `python scripts/user_app.py`, create a test campaign, generate content, approve a draft, and let it post to X. Expect: `local_post.post_url` contains `https://x.com/{user}/status/{id}`. Check: `SELECT post_url FROM local_post ORDER BY id DESC LIMIT 1`.
2. Repeat for LinkedIn. Expect: URL contains `/feed/update/` or `/in/me/recent-activity/`.
3. Repeat for Reddit. Expect: URL contains `/comments/`.
4. Repeat for Facebook. Expect: URL contains `/posts/` or `/permalink/` or at minimum `facebook.com/me`.
5. Set mode to `full_auto`. Wait for `CONTENT_GEN_INTERVAL` (120s) + `LOOP_INTERVAL` (60s). Expect: drafts auto-approved (`agent_draft.approved = 1`), posts scheduled (`post_schedule` rows with status `queued`), and posts executed (status `posted`).
6. Verify `posted_no_url` fallback: Temporarily break a URL selector. Expect: post still marked as sent, status is `posted_no_url`, not `failed`.

---

### Task #29 — Explain + Verify: Metric Scraping
**Status**: Pending
**Priority**: High
**Depends on**: #28

#### What it is
After posting, the system must revisit each post at scheduled intervals to scrape engagement data (impressions, likes, reposts, comments). These metrics are the billing input — wrong or missing metrics mean wrong or zero payouts.

#### Current state
- **Scraping schedule**: `_should_scrape()` in `scripts/utils/metric_scraper.py` (line 322-374) implements cumulative tiers: T+1h (scrape 0), T+6h (scrape 1), T+24h (scrape 2), T+72h (scrape 3, `is_final=True`). After 72h, optional recurring scrapes every 24h (not final).
- **Per-platform scrapers** (all in `metric_scraper.py`):
  - `_scrape_x()` (line 55-87): Finds `[role="group"] [aria-label]` elements, parses "view", "like", "repost", "repl"/"comment" from aria-labels.
  - `_scrape_linkedin()` (line 90-141): CSS selectors (`.social-details-social-counts__reactions-count`) with regex body text fallback for impressions, reactions, comments, reposts.
  - `_scrape_facebook()` (line 144-186): `[aria-label*="reaction"]` for likes, body text regex for comments/shares/views.
  - `_scrape_reddit()` (line 189-231): `shreddit-post` element attributes (`score`, `comment-count`), body text regex for views.
- **API fallback**: `scrape_all_posts()` (line 377) tries `MetricCollector` first (from `utils/metric_collector.py` — X and Reddit via official APIs), falls back to Playwright scrapers.
- **Storage**: `add_metric()` in `local_db.py` (line 491) inserts into `local_metric` table with `scraped_at`, `is_final` flag.
- **Server sync**: `sync_metrics_to_server()` (line 508-534) reads `get_unreported_metrics()` (joins `local_metric` with `local_post` where `reported=0 AND server_post_id IS NOT NULL`), sends batch to server via `report_metrics()` in `server_client.py` (line 218), marks as reported.
- **Background agent**: `run_metric_scraping()` in `background_agent.py` (line 431-445) calls `scrape_all_posts()` then `sync_metrics_to_server()` every 60s (the `_should_scrape` function handles actual scheduling).

#### What to implement
1. **Test each platform scraper** against a real posted URL. For each, manually open the post in a browser and compare visible engagement numbers to what the scraper returns.
2. **Verify the tier schedule**: Post to X (fast URL capture), wait 65+ minutes, run `python scripts/utils/metric_scraper.py`. Expect: exactly 1 metric row in `local_metric` for that post, with `is_final=0`.
3. **Verify server sync**: Check that `sync_metrics_to_server()` successfully sends metrics. Inspect server logs or query the server's `metrics` table.
4. **Fix any broken selectors**: If a platform scraper returns all zeros for a post that visibly has engagement, update the selectors in the corresponding `_scrape_{platform}()` function.

#### How it connects
- `local_metric` rows flow to server `Metric` model via `report_metrics()` API call (`POST /api/metrics`)
- Server-side `billing.py` `run_billing_cycle()` reads `Metric` rows joined with `Post`, `CampaignAssignment`, and `Campaign` to calculate earnings
- `is_final=True` (T+72h scrape) is the billing source of truth — earlier scrapes are informational
- `get_posts_for_scraping()` in `local_db.py` (line 442) requires `post_url IS NOT NULL`, so Task #28 must pass first

#### Verification criteria
1. Post to X. After 65+ minutes, run `python scripts/utils/metric_scraper.py`. Expect: `SELECT * FROM local_metric WHERE post_id = {id}` returns 1 row with non-zero `impressions` or `likes`.
2. Post to LinkedIn. Run scraper after T+1h. Expect: non-zero `likes` or `impressions` in metric row.
3. Run `sync_metrics_to_server()`. Expect: `reported=1` for the synced metrics. Server response: `{"accepted": N}` where N > 0.
4. Simulate T+72h: Manually insert a `local_post` with `posted_at` 73 hours ago, ensure existing_scrape_count is 3. Run scraper. Expect: new metric row with `is_final=1`.
5. Verify dedup: Run scraper twice in quick succession. Expect: no duplicate metric rows (second run should return "No posts due for scraping at this time").

---

### Task #30 — Explain + Verify: Billing
**Status**: Pending
**Priority**: High
**Depends on**: #29

#### What it is
The billing engine converts scraped metrics into user earnings. It reads payout rules from the campaign, applies per-metric rates, deducts platform cut, caps to remaining budget, creates Payout records with a 7-day hold period, and handles tier-based CPM multipliers.

#### Current state
- **Earnings calculation**: `calculate_post_earnings_cents()` in `server/app/services/billing.py` (line 66-91). Reads `campaign.payout_rules` JSONB field (`rate_per_1k_impressions`, `rate_per_like`, `rate_per_repost`, `rate_per_click`), converts rates to cents, computes raw earnings, applies `platform_cut_percent` (from `server/app/core/config.py` settings).
- **Billing cycle**: `run_billing_cycle()` (line 104-246). Joins `Metric` + `Post` + `CampaignAssignment` + `Campaign`. Dedup: tracks billed metric IDs via `Payout.breakdown["metric_id"]`. Caps to `campaign.budget_remaining`. Creates `Payout` record with `status="pending"` and `available_at = now + 7 days`. Updates `user.earnings_balance_cents`, `user.total_earned_cents`, and legacy float fields. Auto-pauses or completes campaign when `budget_remaining < $1.00` (line 185-191). Sends 80% budget alert (line 194-196). Increments `user.successful_post_count` and calls `_check_tier_promotion()` (line 228-229).
- **Tier promotion**: `_check_tier_promotion()` (line 42-57). Seedling -> Grower at 20 posts. Grower -> Amplifier at 100 posts + trust >= 80.
- **CPM multiplier**: `get_cpm_multiplier()` (line 60-63). Amplifier tier gets 2.0x, others get 1.0x. NOTE: `get_cpm_multiplier()` exists but is NOT called anywhere in `run_billing_cycle()` — the multiplier is not actually applied during billing. This is a bug.
- **Hold period**: `promote_pending_earnings()` (line 249-273). Moves `Payout.status` from `pending` to `available` when `available_at <= now`.
- **Fraud voiding**: `void_earnings_for_post()` (line 276-299+). Voids pending payouts matching a post_id, returns funds to campaign budget.
- **Payout model**: `server/app/models/payout.py` — `EARNING_HOLD_DAYS = 7`, status lifecycle: pending -> available -> processing -> paid | voided | failed.

#### What to implement
1. **Fix CPM multiplier bug**: In `run_billing_cycle()` around line 152, after computing `earning_cents`, multiply by `get_cpm_multiplier(user)`. Currently the multiplier function exists but is never called during billing.
2. **Trigger billing from metric sync**: Currently `run_billing_cycle()` is not called automatically. Add a call to it after metrics are synced to the server. Options: (a) server-side cron endpoint, or (b) have the metric reporting API endpoint trigger billing for affected campaigns.
3. **Verify budget cap works**: Create a campaign with a small budget ($5). Post and submit metrics that would exceed $5. Confirm `budget_remaining` goes to 0 and campaign status changes.
4. **Verify hold period**: Create a payout, confirm `status="pending"`, confirm `available_at` is 7 days in the future. Call `promote_pending_earnings()` with a mocked time > 7 days later. Confirm status changes to `available`.

#### How it connects
- Input: Server `Metric` model (from metric sync) + `Campaign.payout_rules` + `Campaign.budget_remaining`
- Output: `Payout` records (user earnings), `User.earnings_balance_cents` updates, `Campaign.budget_remaining` deduction
- Downstream: `promote_pending_earnings()` moves pending -> available. `process_pending_payouts()` in `payments.py` sends money via Stripe.
- User app reads earnings via `GET /api/users/me/earnings` -> displays on `/earnings` page

#### Verification criteria
1. Create a campaign with `payout_rules: {"rate_per_1k_impressions": 2.00, "rate_per_like": 0.05}`. Submit a metric with 1000 impressions, 10 likes. Expect: earning = (1000 * 200 / 1000) + (10 * 5) = 250 cents raw. After 20% cut: 200 cents ($2.00). Query: `SELECT amount_cents FROM payouts ORDER BY id DESC LIMIT 1` = 200.
2. Submit the same metric ID again. Expect: no new Payout created (dedup by `breakdown.metric_id`).
3. Set `campaign.budget_remaining = 1.00`. Submit a metric that would earn $3.00. Expect: earning capped to $0.80 (budget * (100 - 20) / 100). Campaign status changes to `paused` or `completed`.
4. Promote a user to amplifier tier. Submit a metric. Expect: earnings multiplied by 2x (once the CPM multiplier bug is fixed).
5. Run `promote_pending_earnings()` on a payout created > 7 days ago. Expect: `status` changes from `pending` to `available`.

---

### Task #31 — Explain + Verify: Earnings Display
**Status**: Pending
**Priority**: Medium
**Depends on**: #30

#### What it is
The user-facing earnings page must accurately display total earned, available balance, pending balance, per-campaign breakdown, and payout history. The withdrawal flow must create correct payout records.

#### Current state
- **Server endpoint**: `GET /api/users/me/earnings` in `server/app/routers/campaigns.py` (or user routes) — returns `{total_earned, current_balance, pending, per_campaign, per_platform, payout_history}`.
- **User app route**: `user_app.py` line 1247 `/earnings` calls `get_earnings()` from `server_client.py` (line 233). Renders `scripts/templates/user/earnings.html`.
- **Local earnings**: `get_earnings_summary()` in `local_db.py` (line 532-546) queries `local_earning` table — sums by status (pending/paid). This is the LOCAL earnings cache.
- **Withdrawal**: `user_app.py` line 1278 `/earnings/withdraw` POST calls `request_payout(amount)` from `server_client.py` (line 239) — sends `POST /api/users/me/payout`.
- **Dashboard cards**: `user_app.py` line 131 `dashboard()` calls `get_earnings_summary()` for `total_earned` displayed on the main dashboard.
- **Known gap**: The local `local_earning` table and the server's `Payout` table may not be in sync. The local earnings summary reads from `local_earning`, but actual billing happens server-side. If `local_earning` is not populated by the billing cycle, the local dashboard shows $0 even when server-side earnings exist.

#### What to implement
1. **Verify server earnings endpoint** returns correct data. Cross-reference `total_earned` from the API with `SUM(amount_cents)` from the server's `payouts` table.
2. **Sync server earnings to local**: After polling the server earnings API, update `local_earning` table so the local dashboard matches. Currently there is no sync mechanism from server Payout records back to `local_earning`.
3. **Verify withdrawal flow**: Request a $10 withdrawal. Confirm the server creates a Payout record with `status="processing"` and the user's `earnings_balance` is decremented.
4. **Verify per-campaign breakdown**: If the user has posts in 2 campaigns, the earnings page must show separate totals per campaign.

#### How it connects
- Reads from: Server `Payout` model (via API), `User.earnings_balance_cents`, `User.total_earned_cents`
- Displays on: `/earnings` page in user app, dashboard summary card
- Withdrawal creates: New `Payout` record on server with `status="processing"` -> picked up by `process_pending_payouts()` in `payments.py`

#### Verification criteria
1. Create a campaign, post content, submit metrics, run billing. Visit `localhost:5222/earnings`. Expect: `total_earned` > 0, matches the billing calculation from Task #30.
2. Verify `pending` balance shows payouts still in 7-day hold. Verify `current_balance` shows only available (post-hold) earnings.
3. Click withdraw $10 (when balance >= $10). Expect: server returns success, balance decremented by $10. Refresh page — balance reflects the withdrawal.
4. Verify dashboard card at `localhost:5222/` shows the same `total_earned` as the earnings page.

---

### Task #32 — Explain + Verify: Stripe Company Top-up
**Status**: Pending
**Priority**: Medium
**Depends on**: #15 (done)

#### What it is
Companies must be able to add funds to their campaign budget via Stripe Checkout. Without a funded balance, campaigns cannot run.

#### Current state
- **Checkout creation**: `create_company_checkout()` in `server/app/services/payments.py` (line 40-69). Creates a `stripe.checkout.Session` with `payment_method_types=["card"]`, `mode="payment"`, success/cancel URLs pointing to `/company/billing/success` and `/company/billing?cancelled=1`. Company ID stored in `session.metadata`.
- **Verification**: `verify_checkout_session()` (line 72-95). Retrieves the Stripe session by ID, checks `payment_status == "paid"`, returns `{company_id, amount_cents, payment_status}`.
- **Stripe initialization**: `_get_stripe()` (line 25-37). Lazy-loads `stripe` module, reads `STRIPE_SECRET_KEY` from settings/env. Returns `None` if not set (test mode).
- **Company billing page**: Rendered by router in `server/app/routers/company/billing.py`. Shows current balance, top-up form, transaction history.
- **Test mode**: When `STRIPE_SECRET_KEY` is not set, the billing page should offer instant balance credit for development testing. Currently the checkout function returns `None` when Stripe is not configured — the billing page needs to handle this by providing a manual credit form.
- **Balance field**: `Company.balance_cents` in `server/app/models/company.py`. Campaign activation deducts from this balance.

#### Stripe account
Father's company already has a working Stripe account — use that for Amplifier. No need to create a new one.

#### What to implement
1. **Verify Stripe test mode**: Set `STRIPE_SECRET_KEY` to a Stripe test key (`sk_test_...`) from the existing Stripe account. Create a checkout session. Complete payment with Stripe test card `4242424242424242`. Verify `verify_checkout_session()` returns correct `amount_cents`.
2. **Verify balance credit**: After successful checkout, `company.balance_cents` must increase. Check that the billing success handler in the company router actually calls `verify_checkout_session()` and updates the company model.
3. **Verify dev fallback**: Without Stripe key, the billing page should still allow adding test funds. If this doesn't exist, add a simple form that directly credits `company.balance_cents` when `_get_stripe()` returns `None`.

#### How it connects
- Input: Company pays via Stripe Checkout
- Output: `Company.balance_cents` increases
- Downstream: When a company activates a campaign, budget is deducted from `Company.balance_cents` to set `Campaign.budget_total` and `Campaign.budget_remaining`
- User earnings ultimately come from this budget via the billing cycle

#### Verification criteria
1. Set `STRIPE_SECRET_KEY=sk_test_...` in server `.env`. Navigate to `localhost:8000/company/billing`. Click "Add Funds", enter $50. Expect: Stripe Checkout page opens. Complete with test card `4242 4242 4242 4242`, any future expiry, any CVC. Expect: redirected to success page, balance shows +$50.00.
2. Query: `SELECT balance_cents FROM companies WHERE id = {company_id}` = 5000.
3. Remove `STRIPE_SECRET_KEY`. Navigate to billing page. Expect: either a manual credit form or a clear message that payments are disabled in dev mode — not a crash.
4. Create a campaign with budget $25. Expect: `company.balance_cents` decremented by 2500.

---

### Task #33 — Explain + Verify: Campaign Detail Page (Company)
**Status**: Pending
**Priority**: Medium
**Depends on**: #19 (done)

#### What it is
The company campaign detail page shows campaign performance: stats cards, per-platform breakdown, invited/accepted/rejected creators, budget usage, and post performance. Companies need this to understand ROI.

#### Current state
- **Router**: `server/app/routers/company/campaigns.py` line 386, `campaign_detail_page()`. Renders `server/app/templates/company/campaign_detail.html`.
- **Template**: Shows campaign metadata (title, brief, status, dates), budget cards (total, remaining, spent), creator table (users assigned to campaign), invitation funnel (invited/accepted/rejected/expired counts from denormalized `Campaign.invitation_count`, `accepted_count`, `rejected_count`, `expired_count`).
- **Campaign model**: `server/app/models/campaign.py` — has `budget_total`, `budget_remaining`, `payout_rules` (JSONB), `targeting` (JSONB), `content_guidance`, `assets` (JSONB with `image_urls`, `links`, `hashtags`, `brand_guidelines`), `screening_status`, `campaign_version`.
- **Missing from Campaign model**: `campaign_goal`, `tone`, `preferred_formats`, `campaign_type`, `disclaimer_text`. The wizard accepts some of these but they are not persisted.
- **Assets editing**: Campaign edit form may not support uploading/changing images and files. The `assets` JSONB stores URLs but the edit form likely only shows text fields.

#### What to implement
1. **Verify stats accuracy**: Compare the numbers shown on the detail page with direct database queries. Budget remaining should match `campaign.budget_remaining`. Creator count should match `SELECT COUNT(*) FROM campaign_assignments WHERE campaign_id = X`.
2. **Verify invitation funnel**: The denormalized counters (`invitation_count`, `accepted_count`, etc.) should match actual counts from the `campaign_assignments` table grouped by status.
3. **Add asset upload to edit form**: If the campaign edit form does not support changing `assets.image_urls`, add a file upload input that uploads images via `server/app/services/storage.py` and updates the `assets` JSONB.
4. **Verify post performance section**: If the page shows per-post metrics, verify they match the `metrics` table for posts in this campaign.

#### How it connects
- Reads from: `Campaign`, `CampaignAssignment`, `Post`, `Metric`, `User` models
- Companies use this page to monitor ROI and decide whether to pause/extend campaigns
- Budget numbers feed from `billing.py` deductions; invitation counts feed from `server/app/routers/invitations.py`

#### Verification criteria
1. Create a campaign, invite 3 users (or let matching run), have 1 accept. Navigate to `localhost:8000/company/campaigns/{id}`. Expect: invitation_count=3, accepted_count=1, budget_remaining matches initial budget (no posts yet).
2. Have the accepted user post and submit metrics. Run billing. Refresh campaign detail. Expect: budget_remaining decreased, at least 1 post shown with metrics.
3. Upload an image via the edit form (if implemented). Expect: `campaign.assets["image_urls"]` updated. Image visible on the detail page.
4. Pause the campaign. Expect: status changes to "paused", shown on detail page.

---

## Tier 2: Product Gaps

Features and fixes that any real user will hit in the first session. These are v1 requirements.

---

### Task #66 — Detect X (Twitter) Account Lockout
**Priority**: High
**Dependencies**: None

#### What it is
When Playwright opens X for posting or scraping, X may lock the account (shows "Your account got locked" page). Amplifier must detect this, skip X operations, notify the user, and mark X as locked.

#### Current state
- **Posting**: `post_to_platform()` in `scripts/post.py` (line 316) calls `post_via_script()` which launches a persistent browser context via `_launch_context()` (line 128). After navigating to X, there is NO check for lockout pages. If locked, the script will timeout trying to find the compose button and report a generic `SELECTOR_FAILED` error.
- **Scraping**: `_scrape_x()` in `metric_scraper.py` (line 55) also does not check for lockout. It will return all-zero metrics.
- **Session health**: `check_session()` in `session_health.py` (line 119) checks auth selectors (`SideNav_NewTweet_Button`, `AppTabBar_Profile_Link`, `primaryColumn`) and login indicators (`loginButton`, `input[name="text"]`). A lockout page has NEITHER — so the function returns `yellow` (uncertain), not `red`.
- **This was identified during Session 23 testing** when X locked a test account during Playwright automation.

#### What to implement
1. **Add lockout detection function** in `scripts/utils/session_health.py`:
   ```python
   LOCKOUT_INDICATORS = {
       "x": [
           'h1:has-text("Your account got locked")',
           'h1:has-text("Account suspended")',
           'a[href*="appeal"]',
       ],
   }
   ```
   Add a `check_lockout(page, platform)` function that checks these selectors. Returns `True` if lockout is detected.

2. **Add lockout check to posting** — In `scripts/post.py` `post_via_script()` (line 179), after launching the browser context and before executing the script, navigate to `https://x.com/home` and call `check_lockout()`. If locked, return `None` and log a specific error.

3. **Add lockout check to scraping** — In `metric_scraper.py` `scrape_all_posts()` (line 377), before scraping X posts, do a lockout check. If locked, skip all X scraping.

4. **Send desktop notification** — Use `scripts/utils/tray.py` `send_notification()` to alert: "Your X account is locked. Open X in your browser to unlock it."

5. **Persist lockout state** — Store `session_health` setting with `"x": {"status": "locked", ...}` in `local_db` settings. The session health check cycle (`check_sessions()` in `background_agent.py` line 448) already runs every 30 minutes — it will re-check and clear the lock when resolved.

#### How it connects
- Posting pipeline in `post_scheduler.py` `execute_scheduled_post()` should check lockout state before attempting X posts
- Dashboard platform health indicators (shown at `localhost:5222/`) read from session health settings — lockout should show as red with "Locked" label
- Metric scraper should skip locked platforms entirely

#### Verification criteria
1. Manually open X in Playwright with a locked account (or mock the lockout page). Run `check_lockout(page, "x")`. Expect: returns `True`.
2. With X marked as locked, trigger a scheduled X post. Expect: post is NOT attempted, error message mentions "locked", post status set to `failed` with `error_code = "AUTH_EXPIRED"`.
3. Check session health while X is locked. Expect: `{"x": {"status": "red", "details": "Account locked"}}`.
4. Unlock X in real browser, wait for next health check cycle (30 min or trigger manually). Expect: X status changes back to `green`.

---

### Task #67 — Improve Session Health Check Reliability
**Priority**: Medium
**Dependencies**: None

#### What it is
`session_health.py` returns `yellow` (uncertain) for platforms that are actually logged in. Auth selectors need updating and the check needs retry logic.

#### Current state
- **Auth selectors** in `session_health.py` (line 36-59):
  - X: `SideNav_NewTweet_Button`, `AppTabBar_Profile_Link`, `primaryColumn`
  - LinkedIn: `div.feed-identity-module`, `button.share-box-feed-entry__trigger`, `img.global-nav__me-photo`, `.feed-shared-update-v2`
  - Facebook: `[aria-label="Create a post"]`, `[aria-label="Your profile"]`, `div[role="feed"]`
  - Reddit: `[data-testid="create-post"]`, `button[aria-label="Open chat"]`, `faceplate-tracker[noun="user_menu"]`
- **Check logic** (line 119-180): Navigates to `home_url` from `platforms.json`, waits 3s, iterates auth selectors (any match = green), iterates login indicators (any match = red), otherwise yellow.
- **No retry logic**: A single check can fail due to slow page load, popup overlays, or transient network issues. One failure = yellow notification even if the session is fine.
- **No posting-success signal**: The strongest proof a session is healthy is a successful post. But `check_session()` does not consider recent posting success.

#### What to implement
1. **Add retry logic** — In `check_session()` (line 119), retry up to 2 times if status is `yellow`. Add a 2-second wait between retries. Only return `yellow` after all retries fail.
2. **Use posting success as green signal** — In `check_session()`, before launching the browser, check `local_post` table for a successful post on this platform within the last 24 hours. If found, return `green` immediately (skip the browser check).
   ```python
   from utils.local_db import _get_db
   conn = _get_db()
   recent = conn.execute(
       "SELECT id FROM local_post WHERE platform = ? AND posted_at > datetime('now', '-24 hours') AND status = 'posted'",
       (platform,)
   ).fetchone()
   conn.close()
   if recent:
       return {"platform": platform, "status": "green", "details": "Recent successful post"}
   ```
3. **Update stale selectors** — Test each platform's auth selectors in a real browser. Replace any that no longer match. LinkedIn and X change their DOM frequently.
4. **Increase page settle time** — Change `page.wait_for_timeout(3000)` (line 152) to 5000ms for more reliable detection.

#### How it connects
- Session health results shown on user dashboard at `localhost:5222/` (platform cards with green/yellow/red indicators)
- Background agent `check_sessions()` in `background_agent.py` (line 448) runs every 30 minutes
- `session_health.py` results stored in `local_db` settings under key `"session_health"`
- Posting pipeline could use health status to skip platforms with `red` sessions

#### Verification criteria
1. Log in to LinkedIn in Playwright profile. Run session health check. Expect: `"linkedin": {"status": "green"}`, not `yellow`.
2. Simulate a slow load: reduce `PAGE_LOAD_TIMEOUT_MS` to 5000. Expect: retry kicks in and still returns `green` on second attempt.
3. Post successfully to Reddit. Within 24h, run session health check. Expect: `green` returned immediately (from posting success signal, no browser launch needed).
4. Log out of X in the browser profile. Run session health check. Expect: `"x": {"status": "red", "details": ...}` with login indicator detected.

---

### FTC Disclosure — Auto-Append Advertising Disclaimers
**Priority**: High
**Dependencies**: None

#### What it is
US FTC requires paid promotional content to include disclosure (`#ad`, `#sponsored`, or similar). Every campaign post must automatically include a disclaimer. Without this, Amplifier users risk FTC enforcement actions.

#### Current state
- **Content generator**: `CONTENT_PROMPT` in `scripts/utils/content_generator.py` (line 28-74) does NOT mention disclaimers or FTC requirements. Generated content has no advertising disclosure.
- **Campaign model**: `server/app/models/campaign.py` has no `disclaimer_text` field. The wizard does not ask for a disclaimer.
- **Local campaign storage**: `local_campaign` table in `local_db.py` (line 28-44) has no `disclaimer_text` column.
- **Posting pipeline**: `scripts/post.py` and the JSON script engine do not append any text to the content before posting.

#### What to implement
1. **Add `disclaimer_text` to Campaign model** — In `server/app/models/campaign.py`, add:
   ```python
   disclaimer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
   ```
   Default to `None`. Add it to the campaign creation schema and wizard form.

2. **Add `disclaimer_text` to local_campaign** — In `local_db.py` `init_db()`, add column:
   ```sql
   ALTER TABLE local_campaign ADD COLUMN disclaimer_text TEXT
   ```
   Update `upsert_campaign()` to store this field.

3. **Append disclaimer in content generator** — In `scripts/utils/content_generator.py`, after generating content via AiManager, append the disclaimer to each platform's text:
   ```python
   disclaimer = campaign_data.get("disclaimer_text") or "#ad"
   for platform in content:
       if platform == "image_prompt":
           continue
       text = content[platform]
       if isinstance(text, dict):  # Reddit format
           text["body"] = text["body"] + f"\n\n{disclaimer}"
       else:
           text = text + f"\n\n{disclaimer}"
       content[platform] = text
   ```
   Place this in `ContentGenerator.generate()` after parsing the AI response.

4. **Platform-specific formatting**: X adds disclaimer as the last line (within 280 char limit — reduce available chars by disclaimer length). LinkedIn at bottom. Reddit in body footer. Facebook as last line.

5. **Default disclaimer**: If company does not provide `disclaimer_text`, default to `#ad`.

#### How it connects
- `disclaimer_text` flows: Campaign model -> server API -> `poll_campaigns()` -> `upsert_campaign()` in local_db -> `generate_daily_content()` in background_agent -> content_generator
- Content generator appends before storing in `agent_draft.draft_text`
- Posted content on platforms includes the disclaimer

#### Verification criteria
1. Create a campaign on server with `disclaimer_text = "Sponsored by TestCo #ad"`. Poll it on the user app. Expect: `local_campaign.disclaimer_text = "Sponsored by TestCo #ad"`.
2. Generate content for this campaign. Expect: every platform draft in `agent_draft.draft_text` ends with `\n\nSponsored by TestCo #ad`.
3. Create a campaign with no `disclaimer_text`. Generate content. Expect: drafts end with `\n\n#ad` (the default).
4. Generate an X draft. Expect: total length including disclaimer <= 280 characters.

---

### Task #70 — Fix Draft Notification Count
**Priority**: Medium
**Dependencies**: None

#### What it is
The pending drafts notification badge shows inflated counts because it includes stale drafts from previous days.

#### Current state
- **`get_pending_drafts()`** in `local_db.py` (line 947-960): Queries `agent_draft WHERE approved = 0` with no date filter. Returns ALL unapproved drafts ever generated, regardless of age.
- **Usage**: Called in user_app.py to populate notification badges and the campaigns page draft count.
- **Observed bug**: Badge showed 54 pending drafts when only 12 were generated today. The other 42 were stale drafts from previous days that were never approved or rejected.

#### What to implement
1. **Add date filter to `get_pending_drafts()`** — In `local_db.py` line 947, modify the query to include a `created_at` filter:
   ```python
   def get_pending_drafts(campaign_id: int = None, hours: int = 24) -> list[dict]:
       conn = _get_db()
       cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
       if campaign_id:
           rows = conn.execute(
               "SELECT * FROM agent_draft WHERE approved = 0 AND campaign_id = ? AND created_at >= ? ORDER BY created_at DESC",
               (campaign_id, cutoff),
           ).fetchall()
       else:
           rows = conn.execute(
               "SELECT * FROM agent_draft WHERE approved = 0 AND created_at >= ? ORDER BY created_at DESC",
               (cutoff,),
           ).fetchall()
       conn.close()
       return [dict(r) for r in rows]
   ```
2. **Auto-expire old drafts**: Add a cleanup function that marks drafts older than 48 hours as rejected (`approved = -1`) so they stop appearing in queries. Call it from `background_agent.py` main loop.

3. **Refresh badge on page load**: Ensure the navigation template fetches the draft count via an API call or template variable on each page load, not only on background poll.

#### How it connects
- `get_pending_drafts()` is called by user_app.py campaign routes and the navigation template
- Draft count affects the notification badge visible on every page
- Old rejected/expired drafts should not clutter the review queue

#### Verification criteria
1. Generate 4 drafts today, leave 10 drafts from yesterday unapproved. Call `get_pending_drafts()`. Expect: returns 4 (today only), not 14.
2. Navigate to `localhost:5222/campaigns`. Expect: badge shows 4, not 14.
3. Wait 48+ hours (or manually set `created_at` to 3 days ago). Run cleanup. Expect: old drafts marked as `approved = -1`.

---

### Task #71 — Password Reset Flow
**Priority**: High
**Dependencies**: None

#### What it is
No way to reset a forgotten password. Users are permanently locked out. Must add a reset flow on the server and expose it in the user app.

#### Current state
- **Auth endpoints**: `server/app/routers/auth.py` has `POST /register` (line 14) and `POST /login` (line 32). No reset endpoints.
- **Password hashing**: `server/app/core/security.py` has `hash_password()` and `verify_password()`.
- **User model**: `server/app/models/user.py` has `password_hash` (line 14). No `reset_token` or `reset_token_expires` fields.
- **User app login**: `user_app.py` line 88 `/login` page. No "forgot password" link.

#### What to implement
1. **Add reset token fields to User model** — In `server/app/models/user.py`:
   ```python
   reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
   reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
   ```

2. **Add `POST /api/auth/forgot-password`** — In `server/app/routers/auth.py`:
   - Accept `{"email": "..."}`.
   - Look up user by email. If not found, return 200 anyway (prevent email enumeration).
   - Generate a random token (`secrets.token_urlsafe(32)`), hash it, store in `user.reset_token` with `reset_token_expires = now + 1 hour`.
   - For MVP: return the token in the response (no email sending). Production: send email via SendGrid/SES.

3. **Add `POST /api/auth/reset-password`** — In `server/app/routers/auth.py`:
   - Accept `{"token": "...", "new_password": "..."}`.
   - Find user where `reset_token` matches the hash of the provided token and `reset_token_expires > now`.
   - Update `password_hash`, clear `reset_token` and `reset_token_expires`.
   - Return success.

4. **Add UI in user app** — In `scripts/templates/user/login.html`, add a "Forgot password?" link. New page `/forgot-password` with email input. New page `/reset-password?token=...` with new password input.

#### How it connects
- Server auth endpoints only — no impact on billing, posting, or metrics
- User app adds new routes in `user_app.py` and new templates in `scripts/templates/user/`

#### Verification criteria
1. Call `POST /api/auth/forgot-password` with a registered email. Expect: 200 response with a token.
2. Call `POST /api/auth/reset-password` with the token and new password. Expect: 200 success.
3. Log in with the new password. Expect: success.
4. Log in with the old password. Expect: failure.
5. Try to use the same reset token again. Expect: failure (token consumed).
6. Generate a token, wait 61 minutes (or mock time). Try to use it. Expect: failure (expired).

---

### Task #72 — CSRF Protection
**Priority**: High
**Dependencies**: None

#### What it is
All POST forms in the Flask user app have no CSRF tokens. Any malicious website can submit forms on behalf of a logged-in user.

#### Current state
- **User app**: `scripts/user_app.py` uses Flask with `app.secret_key = os.urandom(24)` (line 39). No CSRF middleware.
- **POST routes**: `/login` (line 88), `/logout` (line 116), `/earnings/withdraw` (line 1278), `/settings` (line 1294), all campaign actions (approve/reject drafts, accept/reject invitations). None validate CSRF tokens.
- **Templates**: All `<form>` elements in `scripts/templates/user/` submit without a hidden CSRF field.

#### What to implement
1. **Install Flask-WTF** — Add `flask-wtf` to `requirements.txt`.
2. **Initialize CSRFProtect** — In `user_app.py` after creating the Flask app:
   ```python
   from flask_wtf.csrf import CSRFProtect
   csrf = CSRFProtect(app)
   ```
3. **Add hidden token to all forms** — In every `<form>` in `scripts/templates/user/`, add:
   ```html
   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
   ```
4. **Exempt API endpoints** — If any endpoints are called by AJAX or external clients, exempt them:
   ```python
   @csrf.exempt
   @app.route("/api/...", methods=["POST"])
   ```
5. **Test all forms still work** — Every POST action should still succeed with the token present.

#### How it connects
- Affects only the Flask user app (`user_app.py`) and its templates
- Does not affect the FastAPI server (FastAPI handles CSRF differently via SameSite cookies and JWT auth)
- All existing POST routes must continue to work with the added token

#### Verification criteria
1. Start the user app. Navigate to `/settings`. Submit the form normally. Expect: success (CSRF token included automatically).
2. Use `curl` to POST to `/settings` without a CSRF token. Expect: 400 or 403 error (CSRF validation failed).
3. Use `curl` to POST to `/settings` with an invalid CSRF token. Expect: 400 or 403 error.
4. Test all POST forms: login, logout, settings, withdraw, approve draft, reject draft, accept invitation, reject invitation. All must work with the CSRF token.

---

### Task #73 — Encrypt Stored Credentials
**Priority**: High
**Dependencies**: None

#### What it is
API keys in the local SQLite are encrypted, but the server auth token in `config/server_auth.json` is stored in plaintext. Anyone with file access can steal the JWT.

#### Current state
- **API key encryption**: `local_db.py` `_SENSITIVE_KEYS = {"gemini_api_key", "mistral_api_key", "groq_api_key"}` (line 227). `set_setting()` (line 244) calls `encrypt_if_needed()` from `scripts/utils/crypto.py`. `get_setting()` (line 230) calls `decrypt_safe()`.
- **Crypto module**: `scripts/utils/crypto.py` uses AES-256-GCM with a machine-derived key (`_derive_key()` line 18 — PBKDF2 from `os.getlogin()@platform.node()`). `encrypt()` returns `"iv_hex:ciphertext_hex"`.
- **Auth token storage**: `server_client.py` `_save_auth()` (line 30) writes `{"access_token": "...", "email": "..."}` as plaintext JSON to `config/server_auth.json`. `_load_auth()` (line 23) reads it.
- **Auth token usage**: `_get_headers()` (line 36) reads the plaintext token for every API call.

#### What to implement
1. **Encrypt auth token on save** — In `server_client.py` `_save_auth()`:
   ```python
   from utils.crypto import encrypt
   data_to_save = dict(data)
   if "access_token" in data_to_save:
       data_to_save["access_token"] = encrypt(data_to_save["access_token"])
   ```
2. **Decrypt auth token on read** — In `server_client.py` `_load_auth()`:
   ```python
   from utils.crypto import decrypt_safe
   data = json.load(f)
   if "access_token" in data and ":" in data.get("access_token", ""):
       data["access_token"] = decrypt_safe(data["access_token"])
   return data
   ```
   The `":"` check distinguishes encrypted values (`iv_hex:ciphertext_hex`) from plaintext JWTs.
3. **Handle migration**: First time after upgrade, `_load_auth()` will find a plaintext token (no `":"`). It should work as-is. On next `_save_auth()`, it will encrypt. No explicit migration needed.

#### How it connects
- `_load_auth()` is called by `_get_headers()` which is used by every API call in `server_client.py`
- `is_logged_in()` checks `auth.get("access_token")` — must still work after decryption
- `user_app.py` `_base_context()` calls `_load_auth()` to get the user email — must still work

#### Verification criteria
1. Log in via `localhost:5222/login`. Open `config/server_auth.json`. Expect: `access_token` value looks like `hexstring:hexstring`, NOT a JWT (`eyJ...`).
2. Navigate to `localhost:5222/`. Expect: dashboard loads successfully (token decrypted and used for API calls).
3. Delete `config/server_auth.json`. Log in again. Expect: new encrypted token saved.
4. Copy `config/server_auth.json` to another machine. Try to run the app. Expect: decryption fails (different machine key). User must re-login.

---

### Task #74 — Rate Limiting, API Key Validation, Campaign Search
**Priority**: High
**Dependencies**: None

#### What it is
Three small but important gaps: login brute force protection, API key validation before save, and campaign list search/filter.

#### Current state
- **No rate limiting**: `server/app/routers/auth.py` `register_user()` (line 14) and `login_user()` (line 32) have no rate limiting. An attacker can try unlimited password guesses.
- **API key save**: `user_app.py` `/settings` POST (line 1294) saves API keys via `set_setting()` without validating them. A typo in the Gemini key will cause silent content generation failures.
- **Campaign list**: `user_app.py` campaigns page shows all campaigns. No search by title or filter by status.

#### What to implement

**1. Server-side rate limiting** — Add `slowapi` to server `requirements.txt`:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
```
In `server/app/main.py`, add `app.state.limiter = limiter`. In `auth.py`:
```python
@router.post("/login")
@limiter.limit("5/minute")
async def login_user(request: Request, ...):
```
Apply to `/register`, `/login`, `/company/register`, `/company/login`.

**2. API key validation** — In `user_app.py` `/settings` POST handler (around line 1312), before calling `set_setting()`, validate each key:
```python
def _validate_gemini_key(key: str) -> bool:
    try:
        import httpx
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": "test"}]}]},
            timeout=10,
        )
        return resp.status_code in (200, 429)  # 429 = rate limited but key is valid
    except Exception:
        return False
```
Show flash error if invalid: "Gemini API key is invalid. Please check and try again."

**3. Campaign search/filter** — In `user_app.py` campaigns route, accept query params `?q=search_term&status=assigned`. Filter the `get_campaigns()` result before rendering. Add a search input and status dropdown to the campaigns template.

#### How it connects
- Rate limiting protects server auth endpoints — no impact on other systems
- API key validation prevents broken content generation pipeline
- Campaign search improves usability but has no backend dependencies

#### Verification criteria
1. Try 6 rapid login attempts with wrong password. Expect: 429 Too Many Requests on the 6th attempt.
2. Enter an invalid Gemini API key in settings. Expect: flash error "Gemini API key is invalid", key NOT saved.
3. Enter a valid Gemini API key. Expect: saved successfully, content generation works.
4. With 10 campaigns in the list, search for "TestCo". Expect: only campaigns with "TestCo" in the title are shown.
5. Filter by status "assigned". Expect: only assigned campaigns shown.

---

### Task #75 — Improve Content Draft UX
**Priority**: High
**Dependencies**: None

#### What it is
The draft review interface is missing critical context that users need to make good approval decisions.

#### Current state
- **Draft review**: `user_app.py` campaign detail route renders drafts from `agent_draft` table. Shows `draft_text` per platform. No campaign guidance shown alongside.
- **Draft model**: `agent_draft` table in `local_db.py` (line 156-169) has: `campaign_id`, `platform`, `draft_text`, `image_path`, `pillar_type`, `quality_score`, `iteration`, `approved`, `posted`.
- **No versioning**: If a user edits a draft, the original AI text is overwritten. No way to revert.
- **No character counts**: Templates do not show remaining character count per platform.
- **Reddit JSON handling**: Reddit drafts are stored as JSON strings (`{"title": "...", "body": "..."}`). Template rendering may fail with `json.loads()` errors if the format is unexpected.
- **Image preview**: `agent_draft.image_path` stores a local file path. The template may not serve this as an `<img>` tag.

#### What to implement
1. **Show content_guidance alongside draft** — In the campaign detail template (`scripts/templates/user/campaign_detail.html`), fetch `local_campaign.content_guidance` and display it in a sidebar or collapsible panel next to the draft text.

2. **Add draft versioning** — Add `original_text` column to `agent_draft` table:
   ```sql
   ALTER TABLE agent_draft ADD COLUMN original_text TEXT
   ```
   When creating a draft in `add_draft()`, also set `original_text = draft_text`. When user edits, only `draft_text` changes. Add a "Revert to original" button that restores `draft_text = original_text`.

3. **Add character counts** — In the draft review template, add JavaScript that counts characters and shows `X / 280` for X, `X / 3000` for LinkedIn, etc. Show red warning when over limit:
   ```javascript
   const LIMITS = {x: 280, linkedin: 3000, facebook: 63206, reddit_title: 300, reddit_body: 40000};
   ```

4. **Fix Reddit JSON handling** — Wrap `json.loads()` calls for Reddit drafts in try/except in both the template and the user_app route. If parsing fails, show the raw text.

5. **Image preview** — Add a Flask route that serves images from the local filesystem:
   ```python
   @app.route("/draft-image/<int:draft_id>")
   def draft_image(draft_id):
       draft = get_draft(draft_id)
       if draft and draft.get("image_path") and Path(draft["image_path"]).exists():
           return send_file(draft["image_path"])
       abort(404)
   ```
   In the template: `<img src="/draft-image/{{ draft.id }}" />` (only if `image_path` is set).

#### How it connects
- Draft review is the approval gate between content generation and posting
- `content_guidance` comes from the campaign (server -> local_db during polling)
- Image preview helps users judge if the AI-generated image matches the content
- Character counts prevent posts from being truncated or rejected by platforms

#### Verification criteria
1. Open campaign detail with a pending draft. Expect: content_guidance text visible alongside the draft.
2. Edit a draft text. Click "Revert to original". Expect: text restores to AI-generated version.
3. Type into the X draft field beyond 280 characters. Expect: character counter turns red, shows "285 / 280".
4. View a campaign with a Reddit draft that has valid JSON. Expect: title and body shown separately, not raw JSON.
5. View a draft with an `image_path`. Expect: image rendered inline below the draft text.

---

### Task #76 — Fix Invitation UX Gaps
**Priority**: High
**Dependencies**: None

#### What it is
The campaign invitation interface has usability gaps: no countdown timers, no clear expired state, no decline reason capture, and onboarding allows 0 niches (which breaks matching).

#### Current state
- **Invitation display**: `user_app.py` campaigns route fetches invitations via `get_invitations()` from `server_client.py` (line 146). Returns list with `expires_at` as ISO timestamp string.
- **Expiry handling**: Templates show raw `expires_at` timestamp. No countdown. No visual distinction between active and expired invitations.
- **Decline flow**: `reject_invitation()` in `server_client.py` (line 162) calls `POST /api/campaigns/invitations/{id}/reject` with no body. No decline reason sent.
- **Onboarding niches**: `user_app.py` onboarding route collects niches via a form. No validation that at least 1 niche is selected. Server-side matching in `matching.py` uses `user.niche_tags` for scoring — empty tags = poor or zero matches.

#### What to implement
1. **Countdown timers** — In the invitation template, use JavaScript to compute time remaining from `expires_at`:
   ```javascript
   function formatCountdown(expiresAt) {
       const diff = new Date(expiresAt) - new Date();
       if (diff <= 0) return "EXPIRED";
       const hours = Math.floor(diff / 3600000);
       const mins = Math.floor((diff % 3600000) / 60000);
       return `${hours}h ${mins}m remaining`;
   }
   ```
   Update every minute via `setInterval`.

2. **Expired badge** — In the template, check if `expires_at < now`. If expired: show a red "EXPIRED" badge, gray out the invitation card, disable accept/reject buttons.

3. **Decline reason** — Add an optional text input when rejecting. Modify `reject_invitation()` in `server_client.py` to send `{"reason": "..."}` in the POST body. Server endpoint in `server/app/routers/invitations.py` should accept and store the reason on the `CampaignAssignment` record (add `decline_reason` column to `CampaignAssignment` model).

4. **Require at least 1 niche** — In `user_app.py` onboarding POST handler, validate:
   ```python
   if not niches or len(niches) == 0:
       flash("Please select at least one niche for campaign matching.", "error")
       return redirect(url_for("onboarding_page"))
   ```
   Also add `required` attribute to the niche selection in the onboarding template.

#### How it connects
- Invitation UX is the gateway to campaign acceptance — confusing UI = low acceptance rate
- Decline reasons feed back to companies (visible on campaign detail page) to help them improve targeting
- Niche tags are critical input to `matching.py` `_build_scoring_prompt()` — empty tags = AI scoring has no user context
- `CampaignAssignment` model in `server/app/models/assignment.py` needs `decline_reason` column

#### Verification criteria
1. View an invitation expiring in 2 hours. Expect: countdown shows "2h 0m remaining" and updates in real-time.
2. View an invitation that expired 1 hour ago. Expect: red "EXPIRED" badge, buttons disabled, card grayed out.
3. Reject an invitation with reason "Not relevant to my audience". Expect: reason stored on server. Company can see it on campaign detail page.
4. Go through onboarding, select 0 niches, submit. Expect: error message, not allowed to proceed.
5. Go through onboarding, select 2 niches. Expect: niches saved to server profile, matching returns campaigns relevant to those niches.

---

## Tier 3: Data Integrity & Testing

---

### Task #60 — Ensure Metrics Accuracy for Billing
**Priority**: High
**Dependencies**: #29

#### What it is
Metrics drive billing. Inaccurate metrics = inaccurate payouts = lost trust from both users and companies. This task adds validation, anomaly detection, and audit logging to the metric pipeline.

#### Current state
- **Scraping**: `metric_scraper.py` per-platform functions (lines 55-286) return `{"impressions": N, "likes": N, "reposts": N, "comments": N}`. No validation that values are reasonable.
- **Storage**: `add_metric()` in `local_db.py` (line 491) stores raw values without sanity checks.
- **Server sync**: `report_metrics()` in `server_client.py` (line 218) sends to `POST /api/metrics`. Server accepts without validation.
- **No audit trail**: No log of what the scraper saw vs what was stored. If a scraper bug inflates numbers, there is no way to detect it after the fact.
- **No anomaly detection**: A post going from 10 impressions to 10,000 between scrapes is not flagged.
- **API collection**: `MetricCollector` in `utils/metric_collector.py` uses official X and Reddit APIs (more accurate than scraping). But it is only used if API credentials are configured.
- **Edge cases not handled**: Deleted posts (scraper navigates to 404), private accounts (scraper sees login page), rate-limited scraping (platform blocks repeated visits).

#### What to implement
1. **Add sanity checks to `add_metric()`** — In `local_db.py`, before inserting, check:
   ```python
   # Flag if any single metric value exceeds 10x the previous scrape
   prev = conn.execute(
       "SELECT impressions, likes, reposts, comments FROM local_metric WHERE post_id = ? ORDER BY id DESC LIMIT 1",
       (post_id,)
   ).fetchone()
   if prev:
       for field in ["impressions", "likes", "reposts", "comments"]:
           old_val = prev[field] or 0
           new_val = locals()[field]
           if old_val > 0 and new_val > old_val * 10:
               logger.warning("ANOMALY: post %d %s jumped from %d to %d (10x+)", post_id, field, old_val, new_val)
   ```
   Store anomalies in a new `metric_anomaly` column or separate table. Do NOT block the insert — flag for review.

2. **Handle deleted posts** — In each `_scrape_{platform}()` function, detect 404 or "This post is unavailable" text. If detected, mark the `local_post.status = "deleted"` and skip further scraping.

3. **Handle rate limiting** — If a scraper gets a 429 response or sees a CAPTCHA page, log it and skip. Do not store zero metrics for a rate-limited scrape (would look like engagement dropped to zero).

4. **Add audit logging** — Log each scrape attempt with: post_id, platform, raw HTML snippet (first 500 chars of the engagement area), parsed values, source (API vs Playwright). Store in a `scrape_log` table or append to `local_metric` as a JSON column.

5. **Cross-validate API vs scrape** — For X and Reddit (where both API and Playwright scrapers exist), periodically compare results. If they diverge by more than 20%, flag the discrepancy.

#### How it connects
- Anomaly flags can feed into `server/app/services/trust.py` for fraud detection
- Deleted post detection should trigger `void_earnings_for_post()` in `billing.py` if post is deleted within the hold period
- Rate-limited scrapes should trigger a backoff in `scrape_all_posts()` (increase wait between scrapes for that platform)

#### Verification criteria
1. Insert a metric with 100 impressions for a post. Insert another with 5000 impressions. Expect: anomaly warning logged ("jumped from 100 to 5000").
2. Scrape a deleted X post (manually delete a test post). Expect: `local_post.status` updated to `"deleted"`, no metric row with all zeros stored.
3. Simulate rate limiting (block the scraper's requests). Expect: no zero-metric row stored, log message about rate limiting.
4. Check `scrape_log` or metric audit data after a normal scrape. Expect: raw scrape data preserved with timestamp and source.

---

### Task #53 — Update SLC Spec
**Priority**: High
**Dependencies**: None

#### What it is
The SLC.md specification document is significantly outdated. It predates the JSON posting engine, image generation, earning hold periods, reputation tiers, and AES encryption. It must be rewritten to match what Amplifier actually does today.

#### Current state
- **SLC.md** dated March 25, 2026. Does not mention: JSON script engine (`scripts/engine/`), AI abstraction layer (`scripts/ai/`), ImageManager with 5 providers, integer-cents billing, 7-day earning hold, reputation tiers (seedling/grower/amplifier), AES-256-GCM encryption, background agent, post_schedule table, metric_collector hybrid API/Playwright approach, campaign_version field, notification system.
- **CLAUDE.md** is more current (updated regularly) but is developer-focused, not a specification.

#### What to implement
1. **Read every source file** listed in CLAUDE.md's Architecture section. For each subsystem, document: what it does, how it works, what its inputs/outputs are, what its current limitations are.
2. **Rewrite SLC.md** with these sections:
   - Product overview (what Amplifier is, who uses it, how money flows)
   - Company side (dashboard, campaign creation, wizard, billing, budget management)
   - User side (onboarding, dashboard, campaign lifecycle, content generation, posting, metrics, earnings)
   - Server (API endpoints, models, services)
   - Technical architecture (posting engine, AI abstraction, image pipeline, billing, trust)
   - Current limitations (URL capture issues, no tests, platforms disabled, manual processes)
3. **Verify accuracy**: Every claim in the spec must be verifiable by running the code or reading the source.

#### How it connects
- SLC.md is the single source of truth for what Amplifier does
- Task #54 (write tests) depends on this — tests verify the behavior described in the spec
- New developers or users should be able to understand the system from this document alone

#### Verification criteria
1. Read the updated SLC.md. For every feature mentioned, find the corresponding source file and function. Expect: every feature described actually exists in the codebase.
2. Search for features in the codebase that are NOT mentioned in SLC.md. Expect: none — the spec should be complete.
3. Show the spec to someone unfamiliar with the project. They should be able to describe the system's architecture and data flow from reading only SLC.md.

---

### Task #54 — Write Tests for All Verified Features
**Priority**: High
**Dependencies**: #53

#### What it is
No automated test suite exists. All verification is manual. This task creates a test suite that covers the critical path: billing, content generation, posting, metric scraping, and user/company workflows.

#### Current state
- **No test files**: No `tests/` directory, no `pytest.ini`, no `conftest.py`.
- **No CI**: No GitHub Actions workflow, no pre-commit hooks.
- **Manual verification only**: Session 23 tested posting manually against real platforms.

#### What to implement
1. **Create test infrastructure**:
   - `tests/conftest.py` with fixtures: test SQLite database, test FastAPI client (using `httpx.AsyncClient` + `app`), mock Playwright browser.
   - `pytest.ini` or `pyproject.toml` with test configuration.
   - Add `pytest`, `pytest-asyncio`, `httpx` to dev requirements.

2. **Server-side tests** (`tests/server/`):
   - `test_billing.py`: Test `calculate_post_earnings_cents()` with known inputs. Test dedup (same metric ID not billed twice). Test budget cap. Test tier CPM multiplier. Test hold period promotion. Test void.
   - `test_auth.py`: Test register, login, wrong password, duplicate email.
   - `test_campaigns.py`: Test campaign CRUD. Test matching hard filters. Test invitation accept/reject.
   - `test_payments.py`: Test checkout creation (mock Stripe). Test balance credit.

3. **Client-side tests** (`tests/client/`):
   - `test_content_generator.py`: Test `_parse_json_response()` with valid/invalid inputs. Test prompt building with campaign data.
   - `test_local_db.py`: Test `init_db()`, `upsert_campaign()`, `add_post()`, `add_metric()`, `get_earnings_summary()`.
   - `test_metric_scraper.py`: Test `_should_scrape()` with various time offsets and scrape counts. Test `_parse_number()`, `_parse_abbreviated()`.
   - `test_post_scheduler.py`: Test `get_due_posts()` with mocked time. Test `execute_scheduled_post()` with mock Playwright.

4. **Integration tests** (`tests/integration/`):
   - `test_money_loop.py`: End-to-end: create company + campaign + user, simulate matching, post creation, metric submission, billing cycle, earnings display. All with mocked external services.

#### How it connects
- Tests lock down the behavior verified in Tasks #28-33
- CI (when added) runs tests on every push
- Tests are the regression safety net for all future changes

#### Verification criteria
1. Run `pytest tests/`. Expect: all tests pass, 0 failures.
2. Intentionally break `calculate_post_earnings_cents()` (e.g., remove platform cut). Run `pytest tests/server/test_billing.py`. Expect: test failure with clear message about expected vs actual earnings.
3. Run `pytest tests/client/test_metric_scraper.py`. Expect: `_should_scrape()` tests cover all tier boundaries (T+0.5h=no, T+1.5h=yes scrape 0, T+7h=yes scrape 1, T+25h=yes scrape 2, T+73h=yes scrape 3 is_final=True).
4. Run `pytest tests/integration/test_money_loop.py`. Expect: full loop passes — campaign created, matched, post recorded, metric submitted, billing creates payout, earnings balance updated.

---

## Launch Tasks

These are prerequisites for real users and real money. No task-master IDs — these are new work items.

---

### Launch: Stripe Integration (Both Directions)

#### What it is
Stripe must work in both directions: companies pay in (Checkout), users get paid out (Connect). Currently the company side has basic Checkout code but no Stripe key is set in production. The user payout side has a placeholder — `stripe_account_id` is hardcoded to `None` in `process_pending_payouts()`.

#### Current state
- **Company top-up**: `create_company_checkout()` in `payments.py` (line 40) creates a Stripe Checkout session. `verify_checkout_session()` (line 72) verifies payment. These work with a test key but no production key is set on Vercel.
- **User payout**: `process_pending_payouts()` in `payments.py` (line 202) iterates payouts with `status="processing"`. Line 238-239: `stripe_account_id = None # placeholder until user Stripe onboarding`. Since it is `None`, the code falls through to test mode (line 266-273) and marks payouts as `paid` without actually sending money.
- **User Stripe account**: `create_user_stripe_account()` (line 98-126) creates a Stripe Connect Express account and returns an onboarding URL. But the resulting `account.id` is never stored on the User model.
- **User model**: `server/app/models/user.py` has no `stripe_account_id` field.
- **Vercel env**: `STRIPE_SECRET_KEY` and related env vars are not set in production.

#### What to implement
1. **Add `stripe_account_id` to User model** — In `server/app/models/user.py`:
   ```python
   stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
   ```
   Run migration (or add column via Supabase CLI).

2. **Store Stripe account ID after onboarding** — After `create_user_stripe_account()` succeeds, save `account.id` to `user.stripe_account_id`.

3. **Add Stripe onboarding to user app** — New route `/settings/connect-stripe` that:
   - Calls the server to create a Stripe Connect account
   - Redirects user to the Stripe onboarding URL
   - On return, stores the `stripe_account_id` via a server API call

4. **Fix `process_pending_payouts()` to use real Stripe** — Replace line 239:
   ```python
   stripe_account_id = user.stripe_account_id
   ```

5. **Set Stripe keys in Vercel** — Use `printf` to set env vars:
   ```bash
   printf "sk_live_..." | vercel env add STRIPE_SECRET_KEY production --cwd server
   printf "pk_live_..." | vercel env add STRIPE_PUBLISHABLE_KEY production --cwd server
   ```

6. **Add webhook endpoint** — `POST /api/webhooks/stripe` to handle:
   - `checkout.session.completed` — credit company balance
   - `transfer.paid` — confirm user payout
   - `account.updated` — track user Stripe account status
   Verify webhook signature using `stripe.Webhook.construct_event()`.

#### How it connects
- Company top-up: Stripe Checkout -> webhook -> `Company.balance_cents` update
- User payout: `promote_pending_earnings()` -> `run_payout_cycle()` -> `process_pending_payouts()` -> Stripe Transfer -> `Payout.status = "paid"`
- Webhook is the reliable confirmation mechanism (replaces redirect-based verification)

#### Verification criteria
1. With Stripe test key: Company tops up $100. Expect: `Company.balance_cents` increases by 10000 after webhook fires.
2. User connects Stripe Express account. Expect: `User.stripe_account_id` is set to `acct_...`.
3. User has $15 in available balance. System runs payout cycle. Expect: Stripe Transfer created to user's Connect account. `Payout.status = "paid"`, `breakdown.processor_ref = "tr_..."`.
4. User has no Stripe account connected. System runs payout cycle. Expect: payout NOT processed, status remains `"processing"`, log message says "No Stripe account".

---

### Launch: PyInstaller Packaging

#### What it is
The user app must be distributable as a standalone Windows executable. Users should not need Python installed.

#### Current state
- **PyInstaller spec**: `amplifier.spec` exists at the project root (build specification for PyInstaller).
- **App entry point**: `scripts/app_entry.py` — packaged app entry point.
- **Installer**: `installer.iss` — Inno Setup script for creating a Windows installer.
- **Dependencies**: Playwright requires a Chromium binary. PIL/Pillow for image processing. Cryptography for AES. All must be bundled.
- **Unknown state**: It is unclear if the current spec successfully builds. The user app has grown significantly since the spec was written.

#### What to implement
1. **Update `amplifier.spec`** — Ensure all new modules are included:
   - `scripts/ai/` (all providers)
   - `scripts/engine/` (script executor, parser, etc.)
   - `scripts/utils/` (all utility modules including new ones: `metric_collector.py`, `session_health.py`, `post_scheduler.py`, `content_generator.py`, `crypto.py`)
   - `config/scripts/` (JSON posting scripts — must be bundled as data files)
   - `scripts/templates/` and `scripts/static/` (Flask templates)

2. **Test the build**:
   ```bash
   pyinstaller amplifier.spec
   ```
   Run the resulting executable. Verify: Flask app starts on port 5222, background agent starts, Playwright can launch a browser, content generation works with API keys.

3. **Handle Playwright binary** — Playwright's Chromium must be bundled or downloaded on first run. Options:
   - Bundle it in the installer (large but reliable)
   - Run `playwright install chromium` on first launch (requires internet)

4. **Update `installer.iss`** — Include all new files, set up Start Menu shortcut, auto-start option.

5. **Test the installer** — Run `iscc installer.iss` to create the installer. Install on a clean Windows machine (no Python). Verify the app runs.

#### How it connects
- This is the distribution mechanism for end users
- Without this, users must install Python + pip + playwright + all dependencies manually
- The installer creates the entry point that launches `user_app.py` + `background_agent.py`

#### Verification criteria
1. Run `pyinstaller amplifier.spec`. Expect: build succeeds with no errors, output in `dist/`.
2. Run the executable on a machine without Python. Expect: Flask app starts, browser opens to `localhost:5222`.
3. Log in, connect a platform, accept a campaign, generate content. Expect: all features work identically to the development environment.
4. Run Inno Setup. Expect: installer .exe created. Install on a clean Windows 11 VM. App runs from Start Menu.

---

### Launch: Mac Support

#### What it is
Amplifier is currently Windows-only. Mac support expands the user base significantly. The core Python code is cross-platform, but several components are Windows-specific.

#### Current state
- **Windows-specific components**:
  - `scripts/setup_scheduler.ps1` — PowerShell script for Windows Task Scheduler (not used by the campaign platform path, but exists)
  - `scripts/generate.ps1` — PowerShell content generator (replaced by `content_generator.py` for campaigns, but still used for personal posting)
  - `amplifier.spec` and `installer.iss` — Windows-only packaging
  - `scripts/utils/crypto.py` `_derive_key()` uses `os.getlogin()` which works on Mac but `platform.node()` returns different formats
  - Image post-processing in `scripts/ai/image_postprocess.py` uses Windows fonts (specified by name, may not exist on Mac)
- **Cross-platform components**: All Python code, Flask app, Playwright (cross-platform), JSON posting scripts, SQLite database.

#### What to implement
1. **Audit all Windows-specific code** — Search for: `os.getlogin()`, `platform.node()`, Windows font names, PowerShell calls, Windows Task Scheduler references, Windows-specific paths (`C:\`, `\` separators).

2. **Fix crypto key derivation** — Ensure `_derive_key()` produces consistent results on Mac. `os.getlogin()` works on Mac. `platform.node()` returns hostname on both platforms. Should be fine, but test.

3. **Fix image post-processing fonts** — In `scripts/ai/image_postprocess.py`, replace Windows font names with cross-platform fonts or bundled font files:
   ```python
   import platform
   if platform.system() == "Darwin":
       font_path = "/System/Library/Fonts/Helvetica.ttc"
   else:
       font_path = "arial.ttf"  # Windows
   ```

4. **Create Mac packaging** — Options:
   - **py2app** — Mac equivalent of PyInstaller. Create a `setup.py` with py2app configuration.
   - **PyInstaller on Mac** — PyInstaller works on Mac too. Create a `amplifier_mac.spec`.
   - Bundle Playwright Chromium for Mac (`playwright install chromium` on the Mac build machine).

5. **Test on Mac** — Run the full pipeline: login, onboarding, content generation, posting (at least 1 platform), metric scraping, earnings display.

#### How it connects
- Expands addressable user base from Windows-only to Windows + Mac
- No server changes needed — server is platform-agnostic
- User app (Flask + Playwright) is inherently cross-platform, just needs packaging

#### Verification criteria
1. Clone repo on a Mac. Run `pip install -r requirements.txt && playwright install chromium`. Run `python scripts/user_app.py`. Expect: app starts on `localhost:5222`.
2. Connect a platform via `login_setup.py`. Expect: persistent profile created in `profiles/`.
3. Generate content, approve a draft, post to a platform. Expect: post succeeds, URL captured.
4. Build with PyInstaller on Mac. Run the resulting `.app` or executable. Expect: same behavior as development mode.
5. Verify `_derive_key()` produces the same result across sessions on the same Mac (encryption/decryption round-trips correctly).

---

### Launch: Landing Page

#### What it is
A public-facing website explaining Amplifier to potential users and companies. Must convert visitors into sign-ups.

#### Current state
- **No landing page exists**. The deployed server at `server-five-omega-23.vercel.app` shows only the login pages.
- **Company login**: `/company/login` — functional but no onboarding flow from cold traffic.
- **User sign-up**: Users must download the desktop app and register through it. No web-based sign-up flow.

#### What to implement
1. **Create a static landing page** — Single HTML page (or simple Next.js/Astro site) deployed to Vercel:
   - Hero section: "Earn money posting about products you love" (user value prop) + "Get real people to post about your product" (company value prop)
   - How it works: 3-step flow for users (Sign up → Get matched → Post & earn) and companies (Create campaign → Set budget → Track results)
   - Pricing: Free tier for users. Company pricing (pay per engagement, minimum budget)
   - CTAs: "Download Amplifier" (users), "Create Campaign" (companies — links to `/company/login`)
   - Social proof section (placeholder for now)

2. **Deploy to Vercel** — Either as a separate project or as a route on the existing server (`/` serves landing page, `/company/` and `/admin/` serve dashboards).

3. **SEO basics** — Title, meta description, OG tags for social sharing.

4. **Download link** — Host the Windows installer on GitHub Releases or S3. Link from landing page.

#### How it connects
- Landing page is the top of the funnel for both user and company acquisition
- Links to `/company/login` for company sign-up
- Links to installer download for user sign-up
- Must be updated when Mac support ships (add Mac download link)

#### Verification criteria
1. Navigate to the landing page URL. Expect: page loads in < 2 seconds, all sections render correctly.
2. Click "Create Campaign". Expect: redirected to `/company/login` page.
3. Click "Download Amplifier". Expect: installer download starts.
4. Check page on mobile. Expect: responsive layout, all content readable.
5. Check OG tags: share the URL on X or LinkedIn. Expect: preview card with title, description, and image.

---


## Tier 4: Confirmed Feature Builds

These are from FUTURE.md. The code architecture supports them but they're not built yet. Each requires new code, not just verification.

---

### Tasks #51 + #59 — AI-Powered Profile Scraping

**Priority**: High
**Dependencies**: None

#### What it is

Replace the current CSS-selector-based profile scrapers with Gemini Vision API extraction. Instead of brittle selectors that break when platforms change their DOM, take a screenshot (or extract page text) and let AI parse the structured data. Two complementary approaches: Task #51 uses Gemini Vision on screenshots (zero selectors); Task #59 evaluates AI browser agents (browser-use, AgentQL, Skyvern) for human-like navigation.

#### Current state

`scripts/utils/profile_scraper.py` (1,645 lines) contains 4 platform-specific scrapers:

- `scrape_x_profile()` (line ~152) — navigates to `x.com/home`, clicks `AppTabBar_Profile_Link`, extracts display name via `[data-testid="UserName"]`, bio via `[data-testid="UserDescription"]`, followers via `a[href$="/verified_followers"]`, posts via `article[data-testid="tweet"]`, engagement via `[role="group"]` aria-labels
- `scrape_linkedin_profile()` — navigates to LinkedIn profile URL, scrapes display name, bio, follower/following counts, recent posts, extended profile data (About, Experience, Education, profile viewers, post impressions) via CSS selectors
- `scrape_facebook_profile()` — navigates to `facebook.com/me`, scrapes bio, friends/followers, recent posts via platform-specific selectors
- `scrape_reddit_profile()` — navigates to `reddit.com/user/{username}`, scrapes via `shreddit-post` shadow DOM components, extracts karma, posts, subreddits

Each scraper follows the same pattern:
1. `_launch_context(pw, platform)` opens persistent Playwright browser profile (line ~62)
2. Navigate to profile page
3. Extract data via ~30-50 CSS selectors per platform
4. Store result in `local_db.scraped_profile` table via `upsert_scraped_profile()`
5. Sync to server `User.scraped_profiles` JSONB column via `server_client.py`

Helper functions `_parse_number()` (line 99), `_safe_text()` (line 127), `_safe_attr()` (line 138) provide extraction utilities.

The scraped data feeds two downstream systems:
- **Matching** (`server/app/services/matching.py`): `_build_scoring_prompt()` (line 134) reads `user.scraped_profiles` to build the AI scoring prompt with bio, posts, engagement, extended profile data
- **Content gen** (`scripts/utils/content_generator.py`): does NOT currently use profile data, but the 4-phase agent (Task #52) will use it for style-aware content

#### What to implement

**Step 1 — Create AI scraping module** (`scripts/utils/ai_profile_scraper.py`, NEW):

```python
# Core function signature
async def ai_scrape_profile(platform: str, page: Page) -> dict:
    """Screenshot the profile page, send to Gemini Vision, return structured data."""
    # 1. Take full-page screenshot
    screenshot_bytes = await page.screenshot(full_page=True)
    # 2. Send to Gemini Vision API with structured extraction prompt
    # 3. Parse JSON response
    # 4. Validate and normalize (ensure follower_count is int, etc.)
    # Return same schema as current scrapers: {platform, display_name, bio,
    #   follower_count, following_count, profile_pic_url, recent_posts[],
    #   engagement_rate, posting_frequency, profile_data{}}
```

**Step 2 — Define extraction prompt** (in `ai_profile_scraper.py`):

The Gemini Vision prompt must request the exact JSON schema that `_build_scoring_prompt()` in `matching.py` expects:

```python
PROFILE_EXTRACTION_PROMPT = """Extract the following data from this social media profile screenshot.
Return ONLY valid JSON:
{
  "display_name": "string",
  "bio": "string or null",
  "follower_count": integer,
  "following_count": integer,
  "recent_posts": [
    {"text": "string", "likes": int, "comments": int, "reposts": int,
     "views": int, "posted_at": "string or null", "subreddit": "string or null"}
  ],
  "posting_frequency": float (posts per day estimate),
  "profile_data": {
    "about": "string or null",
    "experience": [{"title": "str", "company": "str"}] or null,
    "karma": int or null,
    "reddit_age": "string or null"
  },
  "ai_detected_niches": ["string"],
  "content_quality": "low|medium|high",
  "audience_demographics_estimate": {"age_range": "str", "interests": ["str"]}
}
"""
```

**Step 3 — Integrate with existing flow** in `profile_scraper.py`:

Modify each `scrape_<platform>_profile()` function to try AI extraction first, fall back to CSS selectors:

```python
async def scrape_x_profile(playwright) -> dict:
    context = await _launch_context(playwright, "x")
    page = context.pages[0] if context.pages else await context.new_page()
    # Navigate to profile (existing code)
    await page.goto(profile_url, ...)
    await page.wait_for_timeout(3000)

    # NEW: Try AI extraction first
    try:
        from utils.ai_profile_scraper import ai_scrape_profile
        result = await ai_scrape_profile("x", page)
        if result and result.get("follower_count", 0) > 0:
            return result
    except Exception as e:
        logger.warning("AI scraping failed for X, falling back to selectors: %s", e)

    # EXISTING: CSS selector fallback (unchanged)
    ...
```

**Step 4 — Sync new fields to server**:

`User.scraped_profiles` (JSONB) already stores per-platform dicts, and `User.ai_detected_niches` (JSONB) already stores AI-classified niches. No server model changes needed. The new fields (`content_quality`, `audience_demographics_estimate`) are stored inside the existing `scraped_profiles` JSONB and are available to `_build_scoring_prompt()` without schema migration.

**Step 5 — Update `_build_scoring_prompt()`** in `server/app/services/matching.py` (line 134):

Add the new AI-extracted fields to the prompt if present:

```python
# After existing profile_data section, add:
if data.get("content_quality"):
    section += f"\nAI-assessed content quality: {data['content_quality']}"
if data.get("audience_demographics_estimate"):
    demo = data["audience_demographics_estimate"]
    section += f"\nEstimated audience: {demo}"
```

**Step 6 — Use Gemini Vision API** via the existing `scripts/ai/manager.py` AiManager or directly via `google.genai`:

```python
from google import genai
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=[
        {"text": PROFILE_EXTRACTION_PROMPT},
        {"inline_data": {"mime_type": "image/png", "data": base64_screenshot}}
    ]
)
```

Cost: Gemini 2.0 Flash free tier. ~4 API calls per full scrape (one per platform). Negligible cost.

#### How it connects

1. **Matching** (`server/app/services/matching.py`): `_build_scoring_prompt()` reads `user.scraped_profiles`. AI scraping produces richer data (niches, content quality, audience demographics) which directly improves AI scoring accuracy. No code changes needed in matching beyond optionally surfacing new fields in the prompt.
2. **Content gen** (future Task #52): The 4-phase content agent's Research Phase will use profile data to understand the user's posting style and audience, enabling style-aware content. This task's output is a prerequisite input.
3. **User app** (`scripts/user_app.py`): Settings page shows scraped profile data. Richer AI extraction means better display.
4. **Background agent** (`scripts/background_agent.py`): Profile refresh task (7-day interval) calls the scrapers. No changes needed — it calls the same `scrape_all_profiles()` entry point.

#### Verification criteria

1. Run `scrape_x_profile()` with AI extraction enabled. Result must include `display_name`, `follower_count > 0`, at least 1 `recent_post` with engagement metrics. Compare against manual inspection of the profile page.
2. Disconnect API key (unset `GEMINI_API_KEY`). Scraper must fall back to CSS selectors and still return data.
3. Sync scraped data to server. Call `GET /api/users/me` and verify `scraped_profiles.x.ai_detected_niches` contains at least 1 niche.
4. Create a campaign targeting niche "finance". AI scraping detects user posts about stocks. Matching score should be > 60 (good fit).
5. Run scraping for all 4 platforms (X, LinkedIn, Facebook, Reddit). Each must return valid structured data or gracefully fall back.

---

### Tasks #52 + #63 — 4-Phase AI Content Agent

**Priority**: High (Critical -- core value proposition)
**Dependencies**: Task #54 (tests for existing features)

#### What it is

Replace the single-prompt `ContentGenerator` with a 4-phase AI agent pipeline: Research (weekly) -> Strategy (per campaign, weekly) -> Creation (daily) -> Review (per draft). The strategy phase uses campaign goal and tone to determine content format (thread, poll, carousel, text, image) per platform. Currently, all campaigns get the same generic prompt regardless of goal.

#### Current state

**Content generation** (`scripts/utils/content_generator.py`):
- `ContentGenerator.generate()` (line 236) formats a single `CONTENT_PROMPT` (line 28) with `{title}`, `{brief}`, `{content_guidance}`, `{assets}`, `{platforms}`. Returns JSON with keys: `x`, `linkedin`, `facebook`, `reddit`, `image_prompt`.
- `ContentGenerator.research_and_generate()` (line 284) adds a URL scraping step: extracts URLs from `campaign.assets`, calls `_scrape_url_deep()` via webcrawler CLI, builds a research brief, injects into assets, then calls `generate()`.
- The prompt does NOT reference `campaign_goal` or `tone` — these fields do not exist on the Campaign model.
- Output is always the same structure: one text per platform + one `image_prompt`. No thread, poll, carousel, or video support.

**Campaign wizard** (`server/app/services/campaign_wizard.py`):
- `run_campaign_wizard()` (line 291) accepts `campaign_goal` parameter (line 294) and uses it in the Gemini prompt (line 386: `CAMPAIGN GOAL: {campaign_goal}`).
- Also accepts `tone` parameter (line 312) but it is labeled "Legacy (kept for backward compat, ignored)".
- The wizard generates `title`, `brief`, `content_guidance`, `payout_rules`, `suggested_budget`. The `campaign_goal` and `tone` are used during generation but NOT returned as separate fields and NOT persisted on the Campaign model.

**Campaign model** (`server/app/models/campaign.py`):
- Has: `title`, `brief`, `assets`, `budget_total`, `budget_remaining`, `payout_rules`, `targeting`, `content_guidance`, `penalty_rules`, `status`, `screening_status`, `company_urls`, `ai_generated_brief`, `budget_exhaustion_action`, `budget_alert_sent`, `campaign_version`, invitation counters, `max_users`
- MISSING: `campaign_goal`, `tone`, `preferred_formats`, `campaign_type`

**Campaign create endpoint** (`server/app/routers/campaigns.py`, line 32):
- `CampaignCreate` schema (`server/app/schemas/campaign.py`, line 20) does NOT include `campaign_goal` or `tone`
- The `create_campaign()` function (line 32) copies fields from schema to model. No `campaign_goal` field to copy.

**Local DB** (`scripts/utils/local_db.py`):
- `agent_research` table (line 147): `campaign_id`, `research_type`, `content`, `source_url` — exists but unused
- `agent_draft` table (line 156): `campaign_id`, `platform`, `draft_text`, `image_path`, `pillar_type`, `quality_score`, `iteration`, `approved`, `posted`
- `agent_content_insights` table (line 171): `platform`, `pillar_type`, `hook_type`, `avg_engagement_rate`, `sample_count`, `best_performing_text` — exists, has `upsert_content_insight()` (line ~1017) and `get_content_insights()` (line ~1032)

**Background agent** (`scripts/background_agent.py`):
- Content gen task runs every 120 seconds. Currently calls `ContentGenerator.research_and_generate()` or `ContentGenerator.generate()`.
- Downloads product images via `_download_campaign_product_images()` (line 34), rotates daily via `_pick_daily_image()` (line 87).

#### What to implement

**Step 1 — Add fields to Campaign model** (`server/app/models/campaign.py`):

```python
# Add after content_guidance field (line 29):
campaign_goal: Mapped[str] = mapped_column(String(30), default="brand_awareness")
# brand_awareness | leads | virality | engagement

tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
# professional | casual | edgy | educational | humorous | inspirational

preferred_formats: Mapped[dict] = mapped_column(JSONB, default=dict)
# {"x": ["text", "thread", "image"], "linkedin": ["text", "carousel", "poll"], ...}
```

**Step 2 — Update schemas** (`server/app/schemas/campaign.py`):

Add to `CampaignCreate` (line 20):
```python
campaign_goal: str = "brand_awareness"
tone: str | None = None
preferred_formats: dict = {}
```

Add to `CampaignResponse` (line 42):
```python
campaign_goal: str = "brand_awareness"
tone: str | None = None
preferred_formats: dict = {}
```

Add to `CampaignBrief` (line 70):
```python
campaign_goal: str = "brand_awareness"
tone: str | None = None
preferred_formats: dict = {}
```

**Step 3 — Update create endpoint** (`server/app/routers/campaigns.py`, line 44):

```python
campaign = Campaign(
    ...
    campaign_goal=data.campaign_goal,
    tone=data.tone,
    preferred_formats=data.preferred_formats,
    ...
)
```

**Step 4 — Update wizard to return and persist these fields** (`server/app/services/campaign_wizard.py`):

The wizard already accepts `campaign_goal` (line 294). Update the return dict (line 450) to include it:
```python
result = {
    **generated,
    "campaign_goal": campaign_goal,
    "tone": tone,
    "reach_estimate": reach,
    "scraped_data": scraped_data,
}
```

**Step 5 — Update CampaignBrief in matching** (`server/app/services/matching.py`):

In `_get_existing_assignments()` (line 401) and `get_matched_campaigns()` (line 543), add the new fields:
```python
CampaignBrief(
    ...
    campaign_goal=campaign.campaign_goal,
    tone=campaign.tone,
    preferred_formats=campaign.preferred_formats,
)
```

**Step 6 — Build the 4-phase ContentAgent** (`scripts/utils/content_agent.py`, NEW):

```python
class ContentAgent:
    """4-phase AI content generation pipeline."""

    def __init__(self):
        self._manager = _get_ai_manager()
        self._image_manager = _get_image_manager()

    # ── Phase 1: Research (weekly per campaign) ──

    async def research(self, campaign: dict) -> dict:
        """Deep-dive into campaign product, competitors, trends.
        - Scrape company URLs (existing _scrape_url_deep)
        - Analyze campaign images via Gemini Vision
        - Competitor scan: search for niche + product type posts
        - Trend scan: what's trending in this niche
        - Store results in agent_research table
        Returns: research_context dict
        """

    # ── Phase 2: Strategy (per campaign, refreshed weekly) ──

    async def strategize(self, campaign: dict, research: dict) -> dict:
        """Determine content plan based on campaign_goal + tone.
        LEADS -> CTAs, product links, conversion hooks
        VIRALITY -> emotional triggers, shareability, threads/carousels
        BRAND_AWARENESS -> lifestyle content, consistent presence
        ENGAGEMENT -> questions, polls, discussion starters

        Returns: {
            "platforms": {
                "x": {"format": "thread", "frequency": "daily", "tone": "edgy"},
                "linkedin": {"format": "carousel", "frequency": "3x/week", "tone": "professional"},
                ...
            },
            "posting_times": [...],
            "content_angles": [...],
        }
        """

    # ── Phase 3: Creation (daily) ──

    async def create(self, campaign: dict, strategy: dict,
                     research: dict, insights: list[dict] = None) -> list[dict]:
        """Generate platform-native content following the strategy.
        - Format-specific output (thread = list of tweets, poll = question + options)
        - Use research context for specifics
        - Use insights for performance-based optimization
        Returns: list of {platform, format, content, image_prompt}
        """

    # ── Phase 4: Review ──

    async def review(self, drafts: list[dict], mode: str) -> list[dict]:
        """Semi-auto: store drafts, notify user. Full-auto: auto-approve."""
```

**Step 7 — Strategy-goal mapping** (inside `content_agent.py`):

```python
GOAL_STRATEGY = {
    "leads": {
        "x": {"formats": ["text", "thread"], "cta": "link_in_bio", "frequency": "2x/day"},
        "linkedin": {"formats": ["text", "article"], "cta": "comment_link", "frequency": "daily"},
        "facebook": {"formats": ["text", "image"], "cta": "link_post", "frequency": "daily"},
        "reddit": {"formats": ["text"], "cta": "subtle_mention", "frequency": "3x/week"},
    },
    "virality": {
        "x": {"formats": ["thread", "image", "poll"], "cta": "retweet", "frequency": "3x/day"},
        "linkedin": {"formats": ["carousel", "poll"], "cta": "share", "frequency": "daily"},
        "facebook": {"formats": ["image", "poll", "album"], "cta": "share", "frequency": "2x/day"},
        "reddit": {"formats": ["image", "text"], "cta": "upvote", "frequency": "daily"},
    },
    "brand_awareness": {
        "x": {"formats": ["text", "image"], "cta": "natural_mention", "frequency": "daily"},
        "linkedin": {"formats": ["text", "image"], "cta": "natural_mention", "frequency": "3x/week"},
        "facebook": {"formats": ["text", "image"], "cta": "natural_mention", "frequency": "3x/week"},
        "reddit": {"formats": ["text"], "cta": "genuine_review", "frequency": "2x/week"},
    },
    "engagement": {
        "x": {"formats": ["poll", "text"], "cta": "reply", "frequency": "2x/day"},
        "linkedin": {"formats": ["poll", "text"], "cta": "comment", "frequency": "daily"},
        "facebook": {"formats": ["poll", "text"], "cta": "comment", "frequency": "daily"},
        "reddit": {"formats": ["text"], "cta": "discussion", "frequency": "3x/week"},
    },
}
```

**Step 8 — Update background agent** (`scripts/background_agent.py`):

Replace the content gen task's call from `ContentGenerator.generate()` to `ContentAgent.create()` with strategy lookup:

```python
from utils.content_agent import ContentAgent

agent = ContentAgent()

# Weekly: run research + strategy
research = await agent.research(campaign_data)
strategy = await agent.strategize(campaign_data, research)
# Cache strategy in agent_research table

# Daily: create content using cached strategy
insights = get_content_insights(platform)
drafts = await agent.create(campaign_data, strategy, research, insights)
```

**Step 9 — Update local_campaign table** (`scripts/utils/local_db.py`):

Add columns to `local_campaign` for the new fields:
```sql
ALTER TABLE local_campaign ADD COLUMN campaign_goal TEXT DEFAULT 'brand_awareness';
ALTER TABLE local_campaign ADD COLUMN tone TEXT;
ALTER TABLE local_campaign ADD COLUMN preferred_formats TEXT DEFAULT '{}';
```

#### How it connects

1. **Campaign creation flow**: Company wizard generates `campaign_goal` and `tone` (already accepted) -> these are now persisted on Campaign model -> flow to CampaignBrief during matching -> user app receives them -> content agent uses them for strategy.
2. **Matching** (`server/app/services/matching.py`): `CampaignBrief` now includes `campaign_goal`, `tone`, `preferred_formats`. The user app uses these to configure the content agent. Matching itself is unaffected.
3. **Content gen**: `ContentGenerator` (old single-prompt) is replaced by `ContentAgent` (4-phase). The `CONTENT_PROMPT` in `content_generator.py` becomes the creation prompt in phase 3, now parameterized by strategy output.
4. **Image gen** (`scripts/ai/image_manager.py`): Strategy phase determines when images are needed (virality campaigns always get images; brand_awareness may use text-only). Image prompt is now strategy-informed.
5. **Posting** (`scripts/post.py`): New content formats (threads, polls, carousels) require new JSON scripts in `config/scripts/` (covered in Task #64). Until then, the agent's strategy must only output formats the posting engine supports (text, image+text).
6. **Self-learning** (Task #61): Strategy phase reads `agent_content_insights` to optimize format/hook selection. The 4-phase agent is the foundation that Task #61 builds on.
7. **Local DB**: `agent_research` table (already exists, currently unused) stores research results. `agent_draft` table stores phase 3 output. `agent_content_insights` feeds phase 2 strategy.

#### Verification criteria

1. Create a campaign with `campaign_goal="virality"`, `tone="edgy"`. Verify these fields persist on the Campaign model: `SELECT campaign_goal, tone FROM campaigns WHERE id=X`.
2. User accepts campaign. Background agent runs content gen. Strategy phase output must show `format: "thread"` for X and `format: "poll"` or `format: "carousel"` for LinkedIn (not plain text for everything).
3. Create a campaign with `campaign_goal="leads"`. Content gen must produce text with product links and CTAs on every platform. No threads or polls (those don't convert for leads).
4. Change a campaign's `campaign_goal` from `brand_awareness` to `virality`. Next content gen cycle must produce different format output. Verify strategy cache is invalidated.
5. Run with `GEMINI_API_KEY` unset. Content agent must fall back to the existing single-prompt `ContentGenerator.generate()` and produce valid output.
6. Verify `agent_research` table has entries after research phase runs for a campaign. Research must include scraped URL content.

---

### Task #58 — AI Campaign Quality Gate

**Priority**: Medium
**Dependencies**: None

#### What it is

AI checks campaign completeness and quality before a company can activate it. Campaigns scoring below 85% get specific feedback ("Add more product details", "Your brief is too vague") and cannot be activated. This prevents low-quality campaigns from reaching users, which protects user trust and content quality.

#### Current state

Campaign activation in `server/app/routers/campaigns.py` (line ~120, the status change to "active") has no quality check. Any campaign with `status="draft"` can be activated if `budget_remaining > 0` and `screening_status == "approved"`.

Content screening (`server/app/models/content_screening.py`) checks for flagged keywords and categories but does NOT evaluate campaign quality (brief completeness, payout rate fairness, targeting specificity).

The campaign wizard (`server/app/services/campaign_wizard.py`) generates high-quality briefs, but companies can manually create campaigns with minimal content via `POST /api/company/campaigns`.

#### What to implement

**Step 1 — Create quality scoring service** (`server/app/services/campaign_quality.py`, NEW):

```python
QUALITY_RUBRIC = {
    "brief_length": {"weight": 20, "min_chars": 200, "good_chars": 500},
    "content_guidance_present": {"weight": 15},
    "payout_rates_reasonable": {"weight": 15},
    "targeting_specified": {"weight": 10},
    "assets_provided": {"weight": 10},
    "title_descriptive": {"weight": 10, "min_chars": 10, "max_chars": 100},
    "dates_valid": {"weight": 10},
    "budget_sufficient": {"weight": 10},
}

async def score_campaign_quality(campaign: Campaign) -> dict:
    """Score campaign quality against rubric. Returns:
    {
        "score": 0-100,
        "passed": bool (score >= 85),
        "feedback": ["Brief is too short — add more product details", ...],
        "breakdown": {"brief_length": 15, "content_guidance_present": 15, ...}
    }
    """

async def ai_quality_review(campaign: Campaign) -> dict:
    """Use Gemini to evaluate campaign quality beyond mechanical checks.
    Checks: Is the brief clear enough for a creator? Are payout rates
    competitive for this niche? Is the content guidance actionable?
    """
```

**Step 2 — Gate activation endpoint** (`server/app/routers/campaigns.py`):

In the campaign status update logic, before allowing `status="active"`:

```python
if new_status == "active":
    from app.services.campaign_quality import score_campaign_quality
    quality = await score_campaign_quality(campaign)
    if not quality["passed"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Campaign quality too low to activate",
                "score": quality["score"],
                "feedback": quality["feedback"],
            }
        )
```

**Step 3 — Add quality score display to company dashboard**:

In `server/app/templates/company/campaign_detail.html`, add a quality score card that shows the breakdown and feedback. Call a new endpoint `GET /company/campaigns/{id}/quality` that returns the scoring result.

**Step 4 — Add quality check to wizard flow**:

After the wizard generates a brief, run `score_campaign_quality()` on the draft and return feedback alongside the generated content so the company can fix issues before creating.

#### How it connects

1. **Campaign activation**: Blocks activation if quality < 85%. Companies must improve their brief/guidance before going live.
2. **Content gen** (Task #52): Higher quality campaigns produce better AI content. The quality gate ensures the content agent has enough information to work with.
3. **User trust**: Users see better campaigns, accept more, post better content, earn more. This improves the entire marketplace quality.
4. **Admin review** (`server/app/routers/admin/review.py`): Quality score can be shown in the admin review queue alongside screening status.
5. **Company wizard**: The wizard already generates high-quality briefs. The gate mainly catches manually-created campaigns with minimal content.

#### Verification criteria

1. Create a campaign with `brief="Buy our product"` (10 chars), no `content_guidance`, no `assets`. Attempt to activate. Must fail with score < 85 and feedback including "Brief is too short."
2. Create a campaign via the AI wizard (full brief generated). Attempt to activate. Must pass with score >= 85.
3. Create a campaign with good brief but `payout_rules.rate_per_1k_impressions = 0.001` (extremely low). Quality gate must flag "Payout rates appear too low for this niche."
4. Company dashboard campaign detail page shows quality score breakdown with actionable feedback for each failed criterion.
5. Fix the issues flagged by the quality gate (lengthen brief, add guidance, adjust rates). Re-attempt activation. Must succeed.

---

### Task #61 — Self-Learning Content Generation

**Priority**: Medium
**Dependencies**: Task #54 (tests)

#### What it is

Build a feedback loop where the content generation AI learns from post performance data. Track which hooks, formats, posting times, and content styles get high engagement, then feed that data back into the Strategy Phase (Task #52) to generate better content over time.

#### Current state

**`agent_content_insights` table** (in `scripts/utils/local_db.py`, line 171):
- Schema: `platform`, `pillar_type`, `hook_type`, `avg_engagement_rate`, `sample_count`, `best_performing_text`
- Write function: `upsert_content_insight()` (line ~1017) — inserts or updates on `(platform, pillar_type, hook_type)` conflict
- Read function: `get_content_insights()` (line ~1032) — returns all insights, optionally filtered by platform, ordered by `avg_engagement_rate DESC`
- **Currently unused** — no code writes to this table or reads from it during content generation.

**Metric scraping** (`scripts/utils/metric_scraper.py`):
- Scrapes engagement at T+1h, T+6h, T+24h, T+72h. Stores in `local_metric` table.
- `is_final=1` flag set at T+72h (billing source of truth).
- Metrics include: impressions, likes, reposts, comments, clicks.

**`agent_draft` table** (`scripts/utils/local_db.py`, line 156):
- Stores generated content: `campaign_id`, `platform`, `draft_text`, `image_path`, `pillar_type`, `quality_score`, `iteration`, `approved`, `posted`
- The `pillar_type` field exists but is not populated by the current content generator.

#### What to implement

**Step 1 — Build performance tracker** (`scripts/utils/content_performance.py`, NEW):

```python
async def analyze_post_performance(post_id: int) -> dict:
    """After T+72h metrics arrive, analyze what made this post work or fail.
    - Extract hook (first sentence of draft_text)
    - Classify hook type (question, story, contrarian, stat, social_proof)
    - Classify format (text_only, image_text, thread, poll)
    - Record platform, posting time, engagement rate
    - Return analysis dict
    """

async def update_insights_from_metrics():
    """Batch job: find all posts with is_final=1 metrics that haven't been
    analyzed. For each, run analyze_post_performance() and upsert into
    agent_content_insights table.
    Called by background_agent.py after metric scraping.
    """
```

**Step 2 — Classify hooks and formats** (in `content_performance.py`):

```python
HOOK_PATTERNS = {
    "question": r"^(did you|have you|what if|why do|how do|ever wonder)",
    "story": r"^(i used to|last week|yesterday|a friend of mine|so i was)",
    "contrarian": r"^(unpopular opinion|hot take|everyone says|most people think)",
    "stat": r"^(\d+%|\d+ out of|\$\d+|according to)",
    "social_proof": r"^(everyone's|my feed is|thousands of|the reason)",
}
# AI classification via Gemini for hooks that don't match regex patterns
```

**Step 3 — Feed insights into Strategy Phase** (Task #52's `content_agent.py`):

```python
async def strategize(self, campaign: dict, research: dict) -> dict:
    # Load performance insights
    from utils.local_db import get_content_insights
    insights = get_content_insights()  # all platforms

    # Build performance context for strategy prompt
    perf_context = ""
    for insight in insights:
        if insight["sample_count"] >= 3:  # minimum sample size
            perf_context += (
                f"- {insight['platform']}/{insight['hook_type']}: "
                f"avg engagement {insight['avg_engagement_rate']:.1%} "
                f"({insight['sample_count']} posts)\n"
            )

    # Include in strategy prompt:
    # "Based on past performance data, these hook types work best: ..."
    # "Avoid these formats on {platform} — engagement below average: ..."
```

**Step 4 — Add to background agent cycle** (`scripts/background_agent.py`):

After metric scraping completes, trigger insight analysis:

```python
# In the metric scraping task:
from utils.content_performance import update_insights_from_metrics
await update_insights_from_metrics()
```

**Step 5 — Add experiment tracking** to `agent_draft` table:

```sql
ALTER TABLE agent_draft ADD COLUMN hook_type TEXT;
ALTER TABLE agent_draft ADD COLUMN content_format TEXT DEFAULT 'text';
```

The content agent tags each draft with its hook type and format at creation time, enabling direct performance tracking.

#### How it connects

1. **Metric scraping** (`scripts/utils/metric_scraper.py`): Produces the raw engagement data. After T+72h (final) metrics arrive, the performance tracker runs. If metric scraping is broken (Task #29-30), self-learning cannot function.
2. **Content agent** (Task #52): The Strategy Phase consumes insights to optimize hook/format selection. Without the 4-phase agent, there is no strategy phase to consume insights — this task depends on Task #52's architecture.
3. **Local DB** (`scripts/utils/local_db.py`): `agent_content_insights` table is the bridge. Metric scraper writes raw data -> performance tracker classifies and upserts insights -> content agent reads insights.
4. **Background agent** (`scripts/background_agent.py`): Orchestrates the feedback loop timing. After metrics scrape -> analyze performance -> cache insights -> next content gen reads insights.

#### Verification criteria

1. Post content to X. Wait for T+72h metric scrape (or manually insert final metrics in `local_metric`). Run `update_insights_from_metrics()`. Verify `agent_content_insights` has a new row with the correct `hook_type`, `platform`, and `avg_engagement_rate`.
2. Generate content for the same campaign after insights exist. The generated content must use a hook type that has above-average performance (not random). Verify by checking the `hook_type` tag on the new `agent_draft`.
3. Insert 5 posts with "question" hooks averaging 3% engagement and 5 posts with "story" hooks averaging 8% engagement. Next content gen for this platform must favor "story" hooks. Verify at least 3 of 5 generated drafts use story hooks.
4. Platform with zero insights: content gen must still work (no crash), using default strategy from `GOAL_STRATEGY` mapping.
5. Insights with `sample_count < 3` must NOT influence strategy (insufficient data).

---

### Task #62 — Free and Paid User Tiers

**Priority**: High
**Dependencies**: None

#### What it is

Add subscription-based pricing tiers for users (amplifiers) that are orthogonal to the existing reputation tiers (seedling/grower/amplifier). Reputation tiers are earned by posting history and trust. Subscription tiers are paid monthly and unlock premium features. A user can be a "seedling" reputation with a "paid" subscription, or an "amplifier" reputation on the "free" tier.

#### Current state

**Reputation tiers** (`server/app/services/billing.py`, line 27):
```python
TIER_CONFIG = {
    "seedling": {"max_campaigns": 3, "spot_check_pct": 30, "cpm_multiplier": 1.0,
                 "auto_post_allowed": False},
    "grower":   {"max_campaigns": 10, "spot_check_pct": 10, "cpm_multiplier": 1.0,
                 "auto_post_allowed": True},
    "amplifier": {"max_campaigns": 999, "spot_check_pct": 5, "cpm_multiplier": 2.0,
                  "auto_post_allowed": True},
}
```

These control: max concurrent campaigns, spot-check frequency, CPM multiplier, auto-post permission. Promotion is automatic based on `successful_post_count` and `trust_score` via `_check_tier_promotion()` (line 42).

**User model** (`server/app/models/user.py`):
- Has `tier` (reputation tier: seedling/grower/amplifier)
- MISSING: `subscription_tier` (free/paid), `stripe_customer_id`, `subscription_status`

**Payments** (`server/app/services/payments.py`):
- Stripe Checkout exists for company balance top-ups
- Stripe Connect exists for user payouts
- No Stripe subscription billing exists

#### What to implement

**Step 1 — Define subscription tier config** (add to `server/app/services/billing.py`):

```python
SUBSCRIPTION_TIERS = {
    "free": {
        "max_campaigns_override": None,  # uses reputation tier limit
        "image_gen_enabled": False,
        "advanced_analytics": False,
        "priority_matching": False,
        "max_posts_per_day": 4,
        "metric_scrape_interval": "standard",  # T+1h/6h/24h/72h
        "price_cents_monthly": 0,
    },
    "pro": {
        "max_campaigns_override": 20,  # overrides reputation tier if higher
        "image_gen_enabled": True,
        "advanced_analytics": True,
        "priority_matching": True,
        "max_posts_per_day": 20,
        "metric_scrape_interval": "fast",  # T+30m/3h/12h/48h
        "price_cents_monthly": 1999,  # $19.99/mo
    },
}
```

**Step 2 — Add fields to User model** (`server/app/models/user.py`):

```python
subscription_tier: Mapped[str] = mapped_column(String(20), default="free")
# free | pro

stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
# Stripe customer ID for subscription billing

subscription_status: Mapped[str] = mapped_column(String(20), default="none")
# none | active | past_due | canceled

subscription_expires_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

**Step 3 — Create subscription endpoints** (`server/app/routers/subscriptions.py`, NEW):

```python
@router.post("/api/users/subscribe")
async def create_subscription(user=Depends(get_current_user), db=...):
    """Create Stripe Checkout session for Pro subscription."""
    # Create Stripe customer if not exists
    # Create Checkout session with mode="subscription"
    # Return checkout URL

@router.post("/api/webhooks/stripe-subscription")
async def stripe_subscription_webhook(request: Request, db=...):
    """Handle subscription lifecycle events."""
    # checkout.session.completed -> activate subscription
    # invoice.payment_failed -> set past_due
    # customer.subscription.deleted -> set canceled

@router.post("/api/users/cancel-subscription")
async def cancel_subscription(user=Depends(get_current_user), db=...):
    """Cancel Pro subscription at period end."""
```

**Step 4 — Add feature gates** throughout the codebase:

In `scripts/background_agent.py` (posting frequency check):
```python
from utils.server_client import get_profile
profile = get_profile()
sub_tier = profile.get("subscription_tier", "free")
max_posts = 20 if sub_tier == "pro" else 4
# Check daily post count before scheduling more
```

In `scripts/utils/content_generator.py` (image generation):
```python
# Before calling generate_image():
if subscription_tier == "free":
    logger.info("Image generation requires Pro subscription, skipping")
    return None
```

In `server/app/services/matching.py` (priority matching):
```python
# In get_matched_campaigns(), boost score for Pro users
if getattr(user, "subscription_tier", "free") == "pro":
    final_score *= 1.2  # 20% boost in matching priority
```

**Step 5 — Add subscription UI to user app** (`scripts/user_app.py`):

Add `/settings/subscription` route showing current tier, upgrade/downgrade buttons, billing history. Link to Stripe Checkout for upgrade.

**Step 6 — Update campaign limit logic** in `server/app/services/billing.py`:

```python
def get_effective_max_campaigns(user) -> int:
    """Max campaigns = max(reputation_tier_limit, subscription_tier_override)."""
    rep_tier = get_tier_config(user.tier)["max_campaigns"]
    sub_config = SUBSCRIPTION_TIERS.get(user.subscription_tier, SUBSCRIPTION_TIERS["free"])
    sub_override = sub_config.get("max_campaigns_override")
    if sub_override is not None:
        return max(rep_tier, sub_override)
    return rep_tier
```

#### How it connects

1. **Matching** (`server/app/services/matching.py`): Pro users get 20% matching score boost, appearing higher in campaign invitation lists. Companies see their campaigns filled faster by engaged, paying users. The `get_matched_campaigns()` function (line 419) must call `get_effective_max_campaigns()` instead of reading `tier_config["max_campaigns"]` directly.
2. **Billing** (`server/app/services/billing.py`): Campaign limits become `max(reputation_limit, subscription_limit)`. The `get_tier_config()` function and `TIER_CONFIG` dict are unchanged, but callers that check `max_campaigns` must also check subscription tier.
3. **Content gen**: Image generation gated behind Pro. `ContentGenerator.generate_image()` (line 370) must check subscription tier before calling `ImageManager`.
4. **Background agent**: Posting frequency capped based on subscription tier. Daily limit enforced in the posting task.
5. **Payments** (`server/app/services/payments.py`): New subscription webhook handler alongside existing Checkout handler. Separate Stripe products for subscription vs balance top-up.
6. **User app**: Settings page shows subscription status. Earnings page shows "Upgrade to Pro for 20% priority matching" upsell.

#### Verification criteria

1. New user registers. `subscription_tier` defaults to "free". Max campaigns follows reputation tier (seedling=3).
2. User subscribes to Pro via Stripe Checkout. After webhook fires, `subscription_tier="pro"`, `subscription_status="active"`. Max campaigns becomes 20.
3. Free user tries to generate image. Image generation is skipped (not an error, just no image). Pro user generates image successfully.
4. Free user at daily post limit (4). Background agent must skip further posting until next day. Pro user can post up to 20/day.
5. Pro user appears higher in matching results than an equivalent free user for the same campaign (score boosted by 20%).
6. Pro user cancels subscription. `subscription_status="canceled"`. Features remain until `subscription_expires_at`. After expiry, reverts to free tier limits.
7. Stripe subscription webhook `invoice.payment_failed` sets `subscription_status="past_due"`. Features still work for a grace period.

---

### Task #64 — All Content Formats Across 6 Platforms

**Priority**: High
**Dependencies**: Task #63 (4-phase content agent) — DONE

> **CRITICAL NOTE (added 2026-04-05):** Before implementing, research the MOST USED content formats on each platform (X, LinkedIn, Facebook, Reddit, Instagram, TikTok) **as of 2026**. Don't just implement what's technically possible — **prioritize formats by actual usage and engagement.** For example: X threads get 2-3x more engagement than single tweets, LinkedIn carousels (PDF) get highest organic reach, Instagram Reels dominate over static posts. Build the formats people actually use and that drive the most engagement, not an exhaustive list of everything each platform supports. Use Brave Search or web research to verify current format performance data before writing any code.

#### What it is

Expand posting support from basic text + single image per platform to all native content formats: X threads, LinkedIn carousels/polls, Facebook photo albums, Reddit link posts, Instagram carousels/reels, TikTok slideshows. Re-enable Instagram and TikTok. Create new JSON scripts per format and update the content agent to produce format-specific output.

#### Current state

**JSON posting scripts** in `config/scripts/`:
- `x_post.json` — text + optional single image
- `linkedin_post.json` — text + optional single image
- `facebook_post.json` — text + optional single image
- `reddit_post.json` — title + body text + optional image

**Script executor** (`scripts/engine/script_executor.py`): 13 action types: `navigate`, `click`, `type`, `wait`, `upload_file`, `dispatch_event`, `keyboard`, `screenshot`, `scroll`, `assert`, `set_variable`, `conditional`, `extract`.

**Content generator** (`scripts/utils/content_generator.py`): `CONTENT_PROMPT` (line 28) outputs one text string per platform. No thread (list of tweets), poll (question + options), or carousel (list of slides) support.

**Platform config** (`config/platforms.json`): TikTok and Instagram have `"enabled": false`.

#### What to implement

**Step 1 — Define format schemas** (in `scripts/utils/content_agent.py` or new `scripts/utils/content_formats.py`, NEW):

```python
FORMAT_SCHEMAS = {
    "text": {"content": "str"},
    "image_text": {"content": "str", "image_prompt": "str"},
    "thread": {"tweets": ["str"], "image_prompts": ["str or null"]},  # X threads
    "poll": {"question": "str", "options": ["str"], "duration_days": "int"},
    "carousel": {"slides": [{"text": "str", "image_prompt": "str"}]},
    "link_post": {"title": "str", "url": "str"},  # Reddit
    "album": {"caption": "str", "image_prompts": ["str"]},  # Facebook
    "video": {"caption": "str", "video_prompt": "str"},  # TikTok, Reels
}
```

**Step 2 — Create new JSON scripts** in `config/scripts/`:

- `x_thread.json` (NEW): Navigate to compose -> type first tweet -> click "+" to add to thread -> type subsequent tweets -> post all
- `linkedin_poll.json` (NEW): Navigate to compose -> click "Create a poll" -> fill question + options -> set duration -> post
- `linkedin_carousel.json` (NEW): Navigate to compose -> click "Add a document" -> upload PDF -> add title -> post
- `facebook_poll.json` (NEW): Navigate to compose -> click "Poll" -> fill question + options -> post
- `reddit_link.json` (NEW): Navigate to submit -> select "Link" tab -> fill title + URL -> post
- `instagram_post.json` (UPDATE existing, re-enable): Upload image -> caption -> share
- `instagram_carousel.json` (NEW): Upload multiple images -> caption -> share
- `tiktok_post.json` (UPDATE existing, re-enable): Upload video -> caption -> post

**Step 3 — Add new action types to ScriptExecutor** (`scripts/engine/script_executor.py`) if needed:

- `upload_multiple_files`: for carousels/albums that require multi-file upload
- `wait_for_upload`: wait until upload progress bar completes (for video)

**Step 4 — Update content agent** (Task #52's `content_agent.py`):

The Strategy Phase determines format per platform. The Creation Phase must produce format-specific JSON:

```python
# For a thread:
{"platform": "x", "format": "thread", "content": {
    "tweets": ["First tweet (hook)", "Second tweet (detail)", "Third tweet (CTA)"],
    "image_prompts": ["image for first tweet", null, null]
}}

# For a poll:
{"platform": "linkedin", "format": "poll", "content": {
    "question": "What's your biggest challenge with X?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "duration_days": 3
}}
```

**Step 5 — Update posting orchestrator** (`scripts/post.py`):

`post_to_platform()` currently loads a single script per platform. Update to select script based on format:

```python
def _get_script_path(platform: str, content_format: str) -> Path:
    """Select the correct JSON script based on platform + format."""
    script_name = f"{platform}_{content_format}.json"
    path = ROOT / "config" / "scripts" / script_name
    if path.exists():
        return path
    # Fallback to basic post script
    return ROOT / "config" / "scripts" / f"{platform}_post.json"
```

**Step 6 — Re-enable Instagram and TikTok** in `config/platforms.json`:

Set `"enabled": true` for both platforms. Update their login setup flows in `scripts/login_setup.py`.

#### How it connects

1. **Content agent** (Task #52): Strategy Phase determines format. Creation Phase produces format-specific content. This task implements the posting side — the agent side is Task #52.
2. **Posting engine** (`scripts/engine/script_executor.py`): New scripts use existing action types where possible. May need 1-2 new action types for multi-file upload.
3. **Draft review UI** (`scripts/templates/user/campaign_detail.html`): Must display format-specific previews (thread as sequence, poll as question + options). Currently shows plain text.
4. **Content preview** (Task #65): Visual mockups depend on knowing the content format. This task must be done before #65 can show format-specific previews.
5. **Image gen** (`scripts/ai/image_manager.py`): Threads and carousels may need multiple images per post. `generate_image()` must support batch calls.
6. **Local DB**: `agent_draft.content_format` (new column from Task #61) indicates the format. `post_schedule` must also track format so the posting engine loads the right script.

#### Verification criteria

1. Generate content for X with `campaign_goal="virality"`. Content agent produces a thread (3-5 tweets). Post via `x_thread.json` script. Verify thread appears on X as linked tweets.
2. Generate content for LinkedIn with `campaign_goal="engagement"`. Content agent produces a poll. Post via `linkedin_poll.json` script. Verify poll appears on LinkedIn with all options.
3. Generate content for Reddit. Content agent can produce a link post (`reddit_link.json`). Verify link post appears on Reddit with title + URL.
4. Re-enable Instagram in `config/platforms.json`. Run `login_setup.py instagram`. Post a single image + caption. Verify it appears on Instagram.
5. Attempt to post a thread format on a platform that only supports text (e.g., Reddit). Must gracefully fall back to text-only format, not crash.
6. All 6 platforms (X, LinkedIn, Facebook, Reddit, Instagram, TikTok) must have at least one working posting script.

---

### Task #65 — Platform-Specific Content Preview in Review UI

**Priority**: Low
**Dependencies**: Task #63 (4-phase content agent)

#### What it is

Show draft content as visual mockups of how it will appear on each platform (X tweet card, LinkedIn post card, Reddit post layout, etc.) instead of plain text in the review UI. This is a UX improvement that helps users evaluate content quality before approving.

#### Current state

The draft review appears in the user app's campaign detail page (`scripts/templates/user/campaign_detail.html`). Drafts are shown as plain text in a generic card layout. There are no platform-specific visual mockups. Character counts exist per platform but are shown as numbers, not as visual fill indicators.

The current template renders draft text directly:
```html
<div class="draft-text">{{ draft.draft_text }}</div>
```

No CSS styling mimics any platform's visual appearance.

#### What to implement

**Step 1 — Create CSS mockup templates** (`scripts/static/css/platform-previews.css`, NEW):

Create CSS classes that mimic each platform's visual style:
- `.preview-x`: Dark/light mode tweet card with avatar circle, name/handle, timestamp, engagement buttons (reply, retweet, like, views)
- `.preview-linkedin`: White card with profile photo, name/headline, post text with "...see more" truncation, reaction bar
- `.preview-facebook`: White card with profile photo, name, timestamp, text, like/comment/share buttons
- `.preview-reddit`: Reddit post card with vote arrows, subreddit header, title, body text, comment count

**Step 2 — Create preview partial templates** (`scripts/templates/user/partials/`, NEW directory):

- `_preview_x.html`: X tweet mockup template
- `_preview_linkedin.html`: LinkedIn post mockup template
- `_preview_facebook.html`: Facebook post mockup template
- `_preview_reddit.html`: Reddit post mockup template
- `_preview_x_thread.html`: X thread mockup (sequence of connected tweets)
- `_preview_linkedin_poll.html`: LinkedIn poll mockup (question + option bars)

Each template receives the draft content and renders it inside the platform-specific visual frame.

**Step 3 — Add character count visual indicators**:

Show a colored progress bar per platform:
- Green: within limit
- Yellow: approaching limit (>80%)
- Red: over limit

Platform limits: X (280), LinkedIn (3,000), Facebook (63,206), Reddit title (300), Reddit body (40,000).

**Step 4 — Add image preview alongside text**:

If `draft.image_path` exists, show the generated image next to the text mockup, positioned as it would appear on the actual platform.

**Step 5 — Update campaign detail template** (`scripts/templates/user/campaign_detail.html`):

Replace the plain text draft display with platform-specific preview rendering:

```html
{% if draft.platform == 'x' %}
    {% include 'user/partials/_preview_x.html' %}
{% elif draft.platform == 'linkedin' %}
    {% include 'user/partials/_preview_linkedin.html' %}
...
{% endif %}
```

**Step 6 — Support format-specific previews** (depends on Task #64):

Thread preview: show each tweet in sequence with connector lines. Poll preview: show question with option bars. Carousel preview: show slide navigation dots.

#### How it connects

1. **Draft review flow**: Users see realistic previews instead of plain text. Better approval decisions. More edits before posting. Higher content quality.
2. **Content formats** (Task #64): Format-specific previews (thread, poll, carousel) depend on the new formats being implemented.
3. **User app** (`scripts/user_app.py`): No route changes needed. The template changes are purely visual.
4. **Image gen** (`scripts/ai/image_manager.py`): Generated images are displayed in the preview frame. Image path comes from `agent_draft.image_path`.

#### Verification criteria

1. Generate a draft for X. Review UI shows a tweet-card mockup with avatar, text, and engagement button placeholders. Not plain text.
2. Draft text exceeding 280 chars for X shows a red character count bar and truncation indicator.
3. Generated image appears alongside the text in the correct position for each platform (X: below text, LinkedIn: below text, Reddit: thumbnail).
4. Reddit draft shows title and body in separate sections matching Reddit's visual layout (vote arrows, subreddit, title bold, body regular).
5. Thread draft (Task #64) shows each tweet in sequence with visual connectors.
6. Preview renders correctly on both desktop (1280px) and tablet (768px) widths.

---

### Task #68 — Repost Campaign Type

**Priority**: High
**Dependencies**: None

#### What it is

Add a new campaign type where companies provide pre-written posts per platform instead of AI-generating content. This gives companies exact control over messaging. Users accept the campaign, receive the pre-written content, and post it directly (with optional minor edits in semi-auto mode). No content generation, no research, no strategy phase.

#### Current state

**Campaign model** (`server/app/models/campaign.py`): Has no `campaign_type` field. All campaigns are implicitly AI-generated.

**CampaignAssignment model** (`server/app/models/assignment.py`): Has `content_mode` field (line 18): `ai_generated | user_customized | repost`. The "repost" value already exists in the enum but is never set.

**Content generation** (`scripts/utils/content_generator.py`): Always runs AI generation. No path to skip it and use pre-written content.

**Campaign wizard** (`server/app/services/campaign_wizard.py`): Only generates AI briefs. No UI for companies to input per-platform post text directly.

#### What to implement

**Step 1 — Add `campaign_type` to Campaign model** (`server/app/models/campaign.py`):

```python
campaign_type: Mapped[str] = mapped_column(String(20), default="ai_generated")
# ai_generated | repost
```

**Step 2 — Create `campaign_posts` table** (`server/app/models/campaign_post.py`, NEW):

```python
class CampaignPost(Base):
    __tablename__ = "campaign_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    # x | linkedin | facebook | reddit | tiktok | instagram
    content: Mapped[str] = mapped_column(Text)
    # For reddit: JSON {"title": "...", "body": "..."}
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_order: Mapped[int] = mapped_column(Integer, default=1)
    # Order in the content calendar (1 = first post, 2 = second, etc.)
    scheduled_offset_hours: Mapped[int] = mapped_column(Integer, default=0)
    # Hours after campaign start to post this (0 = immediately)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

**Step 3 — Add models to registry** (`server/app/models/__init__.py`):

```python
from app.models.campaign_post import CampaignPost
```

**Step 4 — Add repost campaign creation UI** in company dashboard:

In `server/app/templates/company/campaign_create.html`, add a campaign type toggle. When "Repost" is selected, show per-platform text editors instead of the AI wizard:

```html
<div id="repost-editor">
    <h3>Platform Content</h3>
    <div class="platform-tab" data-platform="x">
        <label>X (Twitter) — 280 chars max</label>
        <textarea name="repost_x" maxlength="280"></textarea>
    </div>
    <!-- Similar for linkedin, facebook, reddit -->
</div>
```

**Step 5 — Add repost campaign API endpoints** (`server/app/routers/campaigns.py`):

```python
@router.post("/company/campaigns/{campaign_id}/posts")
async def add_campaign_post(campaign_id: int, data: CampaignPostCreate, ...):
    """Add a pre-written post to a repost campaign."""

@router.get("/company/campaigns/{campaign_id}/posts")
async def list_campaign_posts(campaign_id: int, ...):
    """List all pre-written posts for a repost campaign."""
```

**Step 6 — Update CampaignBrief** to include pre-written posts:

In `server/app/schemas/campaign.py`, add to `CampaignBrief`:
```python
campaign_type: str = "ai_generated"
repost_content: list[dict] | None = None  # Pre-written posts for repost campaigns
```

In `server/app/services/matching.py`, when building `CampaignBrief` for repost campaigns, include the pre-written posts:
```python
repost_content = None
if campaign.campaign_type == "repost":
    # Load campaign_posts for this campaign
    posts_result = await db.execute(
        select(CampaignPost).where(CampaignPost.campaign_id == campaign.id)
            .order_by(CampaignPost.post_order)
    )
    repost_content = [
        {"platform": p.platform, "content": p.content, "image_url": p.image_url,
         "post_order": p.post_order}
        for p in posts_result.scalars().all()
    ]
```

**Step 7 — Update user app flow** (`scripts/background_agent.py`):

When a repost campaign is accepted, skip content generation entirely. Schedule the pre-written posts directly:

```python
if campaign_data.get("campaign_type") == "repost":
    # Schedule pre-written posts directly (no content gen)
    for post_data in campaign_data.get("repost_content", []):
        schedule_post(
            campaign_id=campaign_data["campaign_id"],
            platform=post_data["platform"],
            content=post_data["content"],
            image_url=post_data.get("image_url"),
        )
else:
    # Existing AI content generation flow
    ...
```

**Step 8 — Update invitation UI** in user app:

For repost campaigns, show the actual pre-written content in the invitation card so users know exactly what they are agreeing to post before accepting.

#### How it connects

1. **Matching** (`server/app/services/matching.py`): Repost campaigns use the same matching pipeline (hard filters + AI scoring). The `campaign_type` field does not change matching logic — targeting, niche, platform requirements still apply.
2. **Billing** (`server/app/services/billing.py`): Identical to AI campaigns. Pay per impression/engagement. Budget deduction, hold period, tier multiplier all apply.
3. **Content gen** (`scripts/utils/content_generator.py` / `content_agent.py`): Completely bypassed for repost campaigns. The background agent must check `campaign_type` before triggering content generation.
4. **Posting** (`scripts/post.py`): Unchanged. Repost content flows through the same JSON script engine. The content just comes from `campaign_posts` table instead of AI generation.
5. **Metric scraping** (`scripts/utils/metric_scraper.py`): Unchanged. Scrapes engagement on repost content the same as AI content.
6. **User app draft review**: In semi-auto mode, users see the pre-written content for review (but cannot substantially rewrite it, only minor edits). In full-auto mode, pre-written content posts automatically.

#### Verification criteria

1. Company creates a repost campaign with per-platform content for X, LinkedIn, Reddit. Verify `campaign_type="repost"` in DB and 3 rows in `campaign_posts` table.
2. User polls for campaigns. Repost campaign appears in matched campaigns with `repost_content` populated. Content shows actual post text.
3. User accepts repost campaign. Background agent does NOT trigger `ContentGenerator` or `ContentAgent`. Posts are scheduled directly from `campaign_posts`.
4. Scheduled repost post executes on X via JSON script engine. Post appears on platform with the exact pre-written text.
5. Metrics are scraped for the repost at T+1h. Billing runs and calculates earnings. Identical flow to AI-generated posts.
6. Company creates a repost campaign with no content for LinkedIn (missing platform). User has LinkedIn connected. That platform is simply skipped with no error.

---

### Political Campaigns (No task ID -- from docs/political-campaigns.md)

**Priority**: High (massive revenue opportunity)
**Dependencies**: US legal entity ($5-15K for FEC compliance setup)

Full specification in `docs/political-campaigns.md`. This is a bundle of 6 sub-features that together enable Amplifier for US political campaign clients.

#### What it is

Enable Amplifier to serve political campaigns by adding geographic micro-targeting, political content generation mode, FEC compliance disclaimers, rapid deployment ("war room" mode), political reporting dashboard, and a political campaign wizard. All built within the existing app architecture (DECIDED: one app, not a separate product).

#### Current state

**Campaign model** (`server/app/models/campaign.py`): No `campaign_type` field (also needed by Task #68). No `disclaimer_text` field. No political-specific targeting fields.

**User model** (`server/app/models/user.py`): Has `audience_region` (String, e.g., "us", "global"). MISSING: `zip_code`, `state`, `political_campaigns_enabled`, `political_party_preference`.

**Matching** (`server/app/services/matching.py`): `_passes_hard_filters()` (line 325) checks `target_regions` against `user.audience_region`. No zip code, state, or congressional district filtering.

**Content generator** (`scripts/utils/content_generator.py`): `CONTENT_PROMPT` (line 28) is entirely brand/product focused. No political content types (candidate promotion, issue framing, GOTV, contrast, rapid response).

**Campaign wizard** (`server/app/services/campaign_wizard.py`): `run_campaign_wizard()` (line 291) accepts product-oriented inputs. No political inputs (candidate name, office, district, party, opponent).

**Background agent** (`scripts/background_agent.py`): Campaign polling interval is 10 minutes. Too slow for political rapid response (target: posts live in < 2 hours).

#### What to implement

**Sub-feature 1 — Geographic Micro-Targeting (highest priority):**

Add fields to User model (`server/app/models/user.py`):
```python
zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
state: Mapped[str | None] = mapped_column(String(2), nullable=True)
# US state abbreviation (e.g., "PA", "MI")

political_campaigns_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
# User must opt in to receive political campaigns (default OFF)

political_party_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
# any | democratic | republican | independent | nonpartisan | null
```

Add targeting fields to Campaign model (inside the existing `targeting` JSONB, no new columns needed):
```python
# targeting JSONB gains new optional keys:
# "target_states": ["PA", "MI", "WI"],
# "target_districts": ["PA-07", "MI-08"],
# "target_zip_codes": ["19103", "19104", ...]
```

Create zip-to-district mapping utility (`server/app/utils/geo.py`, NEW):
```python
# Uses free Census Bureau data (ZCTA-to-CD relationship file)
ZIP_TO_DISTRICT: dict[str, str] = {}  # loaded from CSV at startup

def get_congressional_district(zip_code: str) -> str | None:
    """Map a zip code to its congressional district (e.g., 'PA-07')."""
    return ZIP_TO_DISTRICT.get(zip_code)
```

Update `_passes_hard_filters()` in `server/app/services/matching.py`:
```python
# Add after existing region check:
target_states = targeting.get("target_states", [])
if target_states:
    user_state = getattr(user, "state", None)
    if not user_state or user_state not in target_states:
        return False

target_districts = targeting.get("target_districts", [])
if target_districts:
    from app.utils.geo import get_congressional_district
    user_zip = getattr(user, "zip_code", None)
    if not user_zip:
        return False
    user_district = get_congressional_district(user_zip)
    if not user_district or user_district not in target_districts:
        return False

# Political campaign opt-in check
if campaign.campaign_type == "political":
    if not getattr(user, "political_campaigns_enabled", False):
        return False
```

Add zip code collection to user onboarding (`scripts/onboarding.py`) and settings (`scripts/user_app.py` settings routes).

**Sub-feature 2 — Political Content Generation Mode:**

Create political content prompt template (`scripts/utils/political_prompts.py`, NEW):
```python
POLITICAL_CONTENT_TYPES = {
    "candidate_promotion": "Personal endorsement: 'Here's why I'm supporting [candidate]...'",
    "issue_framing": "Education: '[Issue] affects families in [district]. Here's what [candidate] plans...'",
    "gotv": "Voter mobilization: 'Early voting starts [date] in [county]. Don't sit this out.'",
    "contrast": "Comparison: 'While [opponent] voted against [X], [candidate] fought for it.'",
    "rapid_response": "Rebuttal: '[Opponent] just said [quote]. Here's what they're not telling you.'",
}

POLITICAL_CONTENT_PROMPT = """You are a supporter posting on your personal social media account about a political candidate you believe in...
[Platform-specific variants, FEC disclaimer injection, etc.]
"""
```

The content agent's Strategy Phase (Task #52) must detect `campaign_type == "political"` and switch to political prompts. The Research Phase must include daily news monitoring for political campaigns (not just one-time URL scrape).

**Sub-feature 3 — FEC Compliance Disclaimers:**

Add field to Campaign model (`server/app/models/campaign.py`):
```python
disclaimer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
# e.g., "Paid for by Smith for Congress" — FEC requirement for paid political communications
```

Update content generation to append disclaimer:
```python
# In content_agent.py or content_generator.py:
if campaign.get("disclaimer_text"):
    disclaimer = campaign["disclaimer_text"]
    # Per-platform formatting:
    # X: append as last line
    # LinkedIn: append as small text at bottom
    # Reddit: append as footer (---\n{disclaimer})
    # Facebook: append as tag line
```

Update admin review queue to flag political campaigns for compliance check:
```python
# In campaign activation logic:
if campaign.campaign_type == "political":
    campaign.screening_status = "pending"  # Requires admin review
```

**Sub-feature 4 — Rapid Campaign Deployment ("War Room" mode):**

Add `is_rapid_response` flag to Campaign model (inside `targeting` JSONB or as a new column):
```python
is_rapid_response: Mapped[bool] = mapped_column(Boolean, default=False)
```

For rapid-response campaigns:
- Pre-enrolled user pools: users who accepted the parent campaign and opted into `rapid_response_list` get auto-assigned
- Background agent polling interval drops to 60 seconds for rapid campaigns
- Auto-approve + auto-schedule (bypass review even in semi-auto mode)
- Target: campaign created to posts live in < 2 hours

**Sub-feature 5 — Political Reporting Dashboard:**

New company dashboard page (`server/app/templates/company/political_stats.html`, NEW):
- Reach by state/district (map visualization using a JS mapping library)
- Estimated voter contacts: `impressions * estimated_unique_reach * voter_likelihood`
- Message penetration per target district
- Platform breakdown (engagement per dollar per platform)
- Timeline view (message volume over time)

New admin dashboard section for political campaign oversight.

**Sub-feature 6 — Political Campaign Wizard:**

Extend `run_campaign_wizard()` in `server/app/services/campaign_wizard.py` or create a parallel `run_political_wizard()`:
- Input: candidate name, office, district, party, key issues, opponent name, campaign website, opponent website
- Scrape: candidate website, opponent website, local news
- Generate: talking points per issue, platform-specific guidance, suggested posting cadence, targeting pre-configured for the district
- FEC disclaimer auto-generated: "Paid for by {candidate_name} for {office}"

#### How it connects

1. **Matching** (`server/app/services/matching.py`): Geographic filtering added to `_passes_hard_filters()`. Political opt-in check added. Political campaigns only match users with `political_campaigns_enabled=True` AND matching geography. This is the most critical connection -- without geographic matching, political campaigns have zero value.
2. **Content gen** (Task #52): Content agent switches to political prompts when `campaign_type=="political"`. Research Phase adds daily news monitoring for political campaigns.
3. **Billing** (`server/app/services/billing.py`): Political campaigns use higher platform cut (25-30% vs 20%). Requires adding `platform_cut_percent` override per campaign or per `campaign_type`. The `calculate_post_earnings_cents()` function (line 66) reads `settings.platform_cut_percent` -- this must become campaign-type-aware.
4. **User model**: New fields (`zip_code`, `state`, `political_campaigns_enabled`) collected during onboarding and settings. Synced to server.
5. **Admin dashboard**: Political campaigns flagged for compliance review before activation. Admin can verify FEC disclaimers.
6. **Repost campaigns** (Task #68): Political campaigns may use the repost type (pre-written talking points) or AI-generated type. The `campaign_type` field serves double duty: "political" (flag) plus repost/AI mode within that.

#### Verification criteria

1. User sets `zip_code="19103"` (Philadelphia, PA-03). Create political campaign targeting `target_districts=["PA-03"]`. User appears in matched campaigns. User in zip 90210 (CA-36) does NOT match.
2. User has `political_campaigns_enabled=False` (default). Political campaign does NOT appear in their matched campaigns regardless of geography.
3. User opts in to political campaigns. Political campaign with matching district appears. Non-political campaigns still appear based on normal matching.
4. Create political campaign with `disclaimer_text="Paid for by Smith for Congress"`. Generate content for X. Post text must end with "Paid for by Smith for Congress".
5. Create rapid-response political campaign. Enrolled users receive it within 2 minutes (not 10-minute poll interval). Content auto-generates and auto-schedules.
6. Political reporting dashboard shows reach broken down by target state. At least one state with impressions > 0.
7. Political wizard accepts candidate name + district + issues. Generates a brief with district-specific talking points and auto-sets `targeting.target_districts`.

---

## Tier 5: UX Polish, Admin Verification & Compliance

Lower priority -- admin dashboard and system tray work but have not been formally verified. UX improvements that enhance but do not block the product.

---

### Task #39 — Explain: System Tray + Notifications

**Priority**: Low | **Depends on**: #17 (done)

#### What it is
Walk through how the system tray and desktop notifications currently work -- tray icon, right-click menu, dashboard launch, notification triggers, background agent integration.

#### Current state
The system tray (`pystray`) is initialized in `scripts/app_entry.py`. Right-click menu offers: Open Dashboard, Start/Stop Agent, Quit. Desktop notifications use `plyer` for cross-platform toast notifications. The background agent (`scripts/background_agent.py`) writes notifications to the `local_notification` table in `local_db.py`. The user app's dashboard reads from this table.

#### What to implement
Verification only -- walk through the existing flow, identify gaps, fix broken behavior.

#### How it connects
System tray is the user's primary interaction point. If it crashes or fails to launch, the user cannot access the dashboard or control the background agent.

#### Verification criteria
1. Launch the app. System tray icon appears. Right-click shows menu items.
2. Click "Open Dashboard" -- browser opens `localhost:5222`.
3. Background agent generates content -- notification appears in local_notification table AND as a desktop toast.
4. Click "Stop Agent" -- background agent stops. No more polling or posting. Click "Start Agent" -- resumes.
5. Close and reopen the app. Tray icon reappears. Agent state persists (was running -> still running).

---

### Task #40 — Verify: System Tray + Notifications

**Priority**: Low | **Depends on**: #39

#### What it is
Test system tray and notifications against acceptance criteria established in Task #39.

#### Verification criteria
Same as Task #39's criteria. Run each test case, document pass/fail. Fix any failures found.

---

### Task #41 — Explain: Company Dashboard Stats

**Priority**: Low | **Depends on**: #15 (done)

#### What it is
Walk through how company dashboard statistics currently work -- overview metrics, campaign counts, total spend, active users, recent activity.

#### Current state
Company dashboard at `/company/dashboard` (`server/app/routers/company/dashboard.py`). Shows: active campaigns count, total spend, total impressions, active creators. Per-campaign cards with status, budget progress, creator count.

#### What to implement
Verification only -- confirm stats are accurate against actual database data.

#### Verification criteria
1. Create 2 campaigns (1 active, 1 draft). Dashboard shows "1 active campaign", not 2.
2. Campaign with 3 accepted users shows "3 creators" on the campaign card.
3. Total spend matches sum of `(budget_total - budget_remaining)` across all campaigns.
4. Impressions shown match sum of all metrics for the company's campaigns.

---

### Task #42 — Verify: Company Dashboard Stats

**Priority**: Low | **Depends on**: #41

#### Verification criteria
Run all verification test cases from Task #41. Document results. Fix discrepancies.

---

### Task #43 — Explain: Admin Overview

**Priority**: Low | **Depends on**: None

#### What it is
Walk through the admin overview dashboard at `/admin/overview` (`server/app/routers/admin/overview.py`). Shows system-wide metrics: total users, companies, campaigns, posts, revenue.

#### Current state
Admin overview page (`server/app/templates/admin/overview.html`) shows aggregate stats cards and recent activity feed.

#### Verification criteria
1. Total users count matches `SELECT COUNT(*) FROM users`.
2. Total campaigns matches `SELECT COUNT(*) FROM campaigns`.
3. Revenue shown matches sum of all payout amounts.
4. Recent activity shows the 10 most recent events (user signups, campaign creations, posts).

---

### Task #44 — Verify: Admin Overview

**Priority**: Low | **Depends on**: #43

#### Verification criteria
Same as Task #43. Verify each stat against raw database queries.

---

### Task #45 — Explain: Admin Users

**Priority**: Low | **Depends on**: None

#### What it is
Walk through admin user management at `/admin/users` (`server/app/routers/admin/users.py`). List users, view detail, suspend/ban, view assignments and earnings.

#### Current state
Users list page (`server/app/templates/admin/users.html`) shows all users with status, tier, earnings, trust score. User detail page shows profile data, campaign assignments, post history, payout history.

#### Verification criteria
1. Users list shows all registered users with correct tier and trust_score.
2. User detail page shows correct `scraped_profiles` data.
3. Suspend user action sets `status="suspended"`. Suspended user cannot log in or poll campaigns.
4. User's total earnings on detail page matches `total_earned_cents / 100`.

---

### Task #46 — Verify: Admin Users

**Priority**: Low | **Depends on**: #45

#### Verification criteria
Same as Task #45. Test suspend/unsuspend flow. Verify suspended user cannot access API.

---

### Task #47 — Explain: Admin Campaigns

**Priority**: Low | **Depends on**: None

#### What it is
Walk through admin campaign management at `/admin/campaigns` (`server/app/routers/admin/campaigns.py`). List campaigns, view detail, approve/reject screening, manage assignments.

#### Current state
Campaigns list page (`server/app/templates/admin/campaigns.html`) shows all campaigns with status, screening_status, company name, budget. Campaign detail page shows assignments, posts, metrics, budget burn.

#### Verification criteria
1. Campaign list shows all campaigns with correct status and screening_status.
2. Campaign detail shows correct assignment count and per-user post data.
3. Admin can change screening_status from "pending" to "approved" or "rejected".
4. Budget display matches `budget_remaining / budget_total` as percentage.

---

### Task #48 — Verify: Admin Campaigns

**Priority**: Low | **Depends on**: #47

#### Verification criteria
Same as Task #47. Test screening approval and rejection flows. Verify rejected campaigns cannot be activated.

---

### Task #49 — Explain: Admin Payouts

**Priority**: Low | **Depends on**: None

#### What it is
Walk through admin payout management. View all payouts across users, filter by status (pending/available/processing/paid/voided/failed), process bulk payouts.

#### Current state
Admin financial page (`server/app/routers/admin/financial.py` if it exists, or within overview) shows payout list with status, amount, user, campaign. Payout detail shows breakdown (metric_id, post_id, platform, earnings calculation).

#### Verification criteria
1. Payout list shows all payouts with correct status and amount_cents.
2. Filter by status="pending" shows only pending payouts.
3. Payout breakdown matches the earning calculation: `impressions * rate / 1000 * (1 - platform_cut)`.
4. Voided payouts show the reason and the returned budget amount.

---

### Task #50 — Verify: Admin Payouts

**Priority**: Low | **Depends on**: #49

#### Verification criteria
Same as Task #49. Verify payout amounts match billing calculations. Test void flow.

---

### Task #77 — User App: Data Integrity Improvements

**Priority**: Medium | **Dependencies**: None

#### What it is
Four data integrity improvements to prevent data loss and corruption in the user app's local SQLite database.

#### Current state
`scripts/utils/local_db.py` uses raw SQLite with `sqlite3.connect()`. No backups. No transaction wrappers around multi-statement operations. Draft data exists only locally. `campaign_version` column exists on `local_campaign` but is not checked during detail view to detect stale data.

#### What to implement
1. Periodic local DB backup: copy `data/local.db` to `data/local.db.bak` every 6 hours (add to background agent cycle)
2. Sync approved drafts to server: new endpoint `POST /api/users/drafts/sync` that stores draft text on the server as a backup
3. Wrap multi-step SQLite operations in `BEGIN/COMMIT` transactions
4. On campaign detail view, compare `local_campaign.campaign_version` with server `campaign.campaign_version`. Show "Campaign updated -- refresh to see changes" banner if stale.

#### Verification criteria
1. After 6 hours, `data/local.db.bak` exists and is a valid SQLite database.
2. Approve a draft. Call sync endpoint. Draft text appears on server. Delete local DB. Re-sync from server. Draft is recovered.
3. Simulate crash during a multi-insert (kill process mid-operation). Restart. Database is consistent (no partial writes).
4. Company edits campaign brief on server (bumps `campaign_version`). User opens campaign detail. Stale banner appears.

---

### Task #78 — User App: Settings, Metrics & Performance Improvements

**Priority**: Medium | **Dependencies**: None

#### What it is
Settings improvements (auto-populate follower counts, per-platform mode, server sync), metrics improvements (manual entry fallback, resilient selectors, profile refresh), and performance improvements (pagination, caching, lazy loading).

#### Current state
Settings page (`scripts/templates/user/settings.html`) shows API keys and mode toggle. Follower counts must be entered manually even though `scraped_profile` has them. Campaigns list loads all campaigns on every page load (no pagination). No API response caching.

#### What to implement
- Settings: Read `scraped_profile.follower_count` and pre-fill. Add per-platform semi-auto/full-auto toggle. Sync local settings to server on startup.
- Metrics: Add manual metric entry form (fallback when scraping fails). Update CSS selectors for metric scraping resilience. Add 3-day profile refresh interval.
- Performance: Add pagination to campaigns list (20 per page). Cache `/api/campaigns/poll` response for 5 minutes. Lazy-load campaign detail data.

#### Verification criteria
1. Complete profile scrape for X. Open Settings. Follower count for X is pre-populated.
2. Set X to full-auto and LinkedIn to semi-auto. Posting behavior respects per-platform mode.
3. Metric scraping fails for LinkedIn. Manual entry form appears. Enter metrics manually. They sync to server.
4. 50 campaigns in database. Campaigns page loads in < 2 seconds with pagination (showing 20).
5. Navigate to campaigns page twice within 5 minutes. Second load uses cached data (no API call visible in network tab).

---

### Task #79 — User App: UX Polish and Integration Fixes

**Priority**: Medium | **Dependencies**: None

#### What it is
UX improvements (status label renaming, clipboard copy, mobile responsive, form validation, CSV export) and integration fixes (server-side dedup, client-side expiry warnings, conflict detection).

#### Current state
Status labels use internal names (`pending_invitation`, `content_generated`) which confuse users. No clipboard copy for post URLs. Dashboard is not mobile responsive. No client-side form validation. No CSV export for earnings.

#### What to implement
- Rename statuses: `pending_invitation` -> "Invited", `content_generated` -> "Draft Ready", `posted` -> "Live", `paid` -> "Earned"
- Add "Copy URL" button next to each post URL on the Posts tab
- Make dashboard responsive (media queries for 768px and 480px breakpoints)
- Add client-side validation to all forms (required fields, email format, number ranges)
- Add "Export CSV" button on earnings page that downloads per-campaign earnings
- Server-side post URL dedup: prevent same URL from being registered twice
- Client-side invitation expiry warning: show countdown timer on invitations expiring within 24h
- Campaign conflict detection: warn if user accepts two campaigns from competing companies

#### Verification criteria
1. Dashboard shows "Invited" instead of "pending_invitation" on campaign cards.
2. Click "Copy URL" next to a posted URL. Paste in text editor. URL matches.
3. Open dashboard on 768px viewport. All content is visible without horizontal scroll.
4. Submit a form with empty required field. Client-side error appears (no server round-trip).
5. Click "Export CSV" on earnings page. Downloaded file has headers and correct per-campaign data.
6. Register the same post URL twice via API. Second attempt returns error, not duplicate row.

---

### Task #80 — User App: Compliance, Accessibility & Testing

**Priority**: Low | **Dependencies**: None

#### What it is
Legal compliance (ToS, privacy policy, GDPR), accessibility (ARIA, color contrast, keyboard nav), and testing (E2E, unit, mock server, load).

#### Current state
No Terms of Service acceptance during registration. No privacy policy page. No GDPR data export or deletion. No ARIA labels on interactive elements. No automated tests of any kind.

#### What to implement
- Compliance: Add ToS acceptance checkbox on registration (block if unchecked). Create `/privacy` and `/terms` pages. Add GDPR data export (`GET /api/users/me/export` returns all user data as JSON). Add account deletion (`DELETE /api/users/me` with confirmation).
- Accessibility: Add ARIA labels to all buttons, forms, navigation. Check WCAG 2.1 AA color contrast (4.5:1 ratio). Add keyboard navigation (Tab through all interactive elements). Associate labels with form inputs.
- Testing: Write E2E tests for the full flow (register -> onboard -> accept campaign -> generate -> post -> scrape -> earn). Unit tests for content generation, metric scraping, post scheduling. Mock server fixtures for offline testing. Basic load test (10 concurrent users polling).

#### Verification criteria
1. Register without accepting ToS. Registration is blocked.
2. Visit `/privacy`. Privacy policy page renders.
3. Call `GET /api/users/me/export`. Response contains all user data (profile, campaigns, posts, earnings).
4. Call `DELETE /api/users/me` with confirmation. User is deleted. Login fails.
5. Run accessibility audit (Lighthouse or axe). Score >= 90.
6. Tab through the entire dashboard. Every interactive element is reachable via keyboard.
7. Run E2E test suite. All tests pass (register -> earn flow completes).

---

## Summary

| Tier | Tasks | Count | Estimated Effort |
|---|---|---|---|
| **1: Core Loop** | #28-38 (verification) | 11 tasks | 5-7 days |
| **2: Product Gaps** | #66, #67, #70-76, FTC disclosure | 10 tasks | 5-7 days |
| **3: Integrity/Testing** | #53, #54, #60 | 3 tasks | 3-5 days |
| **4: Features** | #51/#59, #52/#63, #58, #61, #62, #64, #65, #68, Political | 12 tasks | 25-35 days |
| **5: Polish/Admin** | #39-50, #77-80 | 18 tasks | 5-7 days |
| **Launch** | Stripe, packaging, Mac, landing page | 4 tasks | 5-7 days |
| **Total** | | **58 tasks** | **48-68 days** |

### Tier 4 Breakdown

| Task | Feature | Key Files to Modify/Create | Schema Changes | Estimated Days |
|---|---|---|---|---|
| #51/#59 | AI Profile Scraping | `scripts/utils/ai_profile_scraper.py` (NEW), `scripts/utils/profile_scraper.py` (modify), `server/app/services/matching.py` (minor) | None (uses existing JSONB columns) | 3-4 |
| #52/#63 | 4-Phase Content Agent | `scripts/utils/content_agent.py` (NEW), `server/app/models/campaign.py`, `server/app/schemas/campaign.py`, `server/app/routers/campaigns.py`, `server/app/services/matching.py`, `scripts/background_agent.py`, `scripts/utils/local_db.py` | Campaign: `campaign_goal`, `tone`, `preferred_formats`. Local: `campaign_goal`, `tone`, `preferred_formats` columns | 6-8 |
| #58 | Campaign Quality Gate | `server/app/services/campaign_quality.py` (NEW), `server/app/routers/campaigns.py`, company dashboard template | None | 2-3 |
| #61 | Self-Learning Content | `scripts/utils/content_performance.py` (NEW), `scripts/utils/content_agent.py` (modify), `scripts/background_agent.py` (modify), `scripts/utils/local_db.py` (alter table) | Local: `agent_draft.hook_type`, `agent_draft.content_format` columns | 3-4 |
| #62 | Free/Paid Tiers | `server/app/models/user.py`, `server/app/services/billing.py`, `server/app/routers/subscriptions.py` (NEW), `scripts/background_agent.py`, `scripts/utils/content_generator.py`, user app templates | User: `subscription_tier`, `stripe_customer_id`, `subscription_status`, `subscription_expires_at` | 4-5 |
| #64 | All Content Formats | `config/scripts/*.json` (6+ NEW scripts), `scripts/engine/script_executor.py` (minor), `scripts/post.py`, `scripts/utils/content_agent.py`, `config/platforms.json` | Local: `post_schedule.content_format` column | 5-7 |
| #65 | Content Preview | `scripts/static/css/platform-previews.css` (NEW), `scripts/templates/user/partials/` (NEW, 6+ templates), `scripts/templates/user/campaign_detail.html` | None | 2-3 |
| #68 | Repost Campaigns | `server/app/models/campaign_post.py` (NEW), `server/app/models/campaign.py`, `server/app/models/__init__.py`, `server/app/schemas/campaign.py`, `server/app/routers/campaigns.py`, `server/app/services/matching.py`, `scripts/background_agent.py`, company dashboard templates | Campaign: `campaign_type`. New table: `campaign_posts` | 3-4 |
| Political | Political Campaigns | `server/app/models/user.py`, `server/app/models/campaign.py`, `server/app/utils/geo.py` (NEW), `server/app/services/matching.py`, `scripts/utils/political_prompts.py` (NEW), `server/app/services/campaign_wizard.py`, company dashboard templates (2+ NEW), admin templates | User: `zip_code`, `state`, `political_campaigns_enabled`, `political_party_preference`. Campaign: `disclaimer_text`, `is_rapid_response`. Also `campaign_type` (shared with Task #68) | 6-8 |

### Tier 5 Breakdown

| Task | Feature | Estimated Days |
|---|---|---|
| #39-40 | System Tray + Notifications | 0.5 |
| #41-42 | Company Dashboard Stats | 0.5 |
| #43-44 | Admin Overview | 0.5 |
| #45-46 | Admin Users | 0.5 |
| #47-48 | Admin Campaigns | 0.5 |
| #49-50 | Admin Payouts | 0.5 |
| #77 | Data Integrity | 1 |
| #78 | Settings/Metrics/Performance | 1.5 |
| #79 | UX Polish + Integration | 1.5 |
| #80 | Compliance + Accessibility + Testing | 2 |

### Dependency Chain (Critical Path)

```
Task #54 (Tests) ──► Task #52/#63 (4-Phase Agent) ──► Task #64 (All Formats)
                                                   ──► Task #65 (Preview)
                                                   ──► Task #61 (Self-Learning)

Task #68 (Repost) ──► Political Campaigns (shares campaign_type field)

Independent (no blockers): #51/#59, #58, #62, #68, Political geo-targeting
```
