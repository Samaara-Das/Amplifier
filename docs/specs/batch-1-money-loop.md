# Batch 1: Money Loop Specifications

**Tasks:** #1 (URL capture), #9 (metric scraping), #10 (billing), #11 (earnings display)

These four tasks form the core money loop: post goes live → URL captured → metrics scraped → billing calculates earnings → user sees money. If any link breaks, nobody gets paid.

---

## Task #1 — Fix URL Capture (LinkedIn, Facebook, Reddit)

### Status: TEST FIRST

URL capture worked in previous testing sessions. **Test all 4 platforms first. Only fix if broken.** The spec below documents the fix strategy IF the test reveals failures.

### Problem (if broken)

After posting, the system must capture the post's permanent URL so the metric scraper can revisit it later. Last known state:
- **X**: Works. Navigates to profile, finds `article[data-testid='tweet'] a[href*='/status/']`.
- **LinkedIn**: May fail. Waits for "View post" dialog that doesn't appear for text-only posts.
- **Facebook**: May fail. Returns profile URL (`facebook.com/me`), not the actual post URL.
- **Reddit**: May fail. Redirect to `/comments/` is not detected.

Without URLs, the metric scraper has nothing to visit, billing has no metrics to process, and users earn $0.

### What "Fixed" Looks Like

Each platform's JSON posting script (`config/scripts/{platform}_post.json`) must capture the real post permalink after posting succeeds.

#### LinkedIn

**Primary approach:** After clicking Post, wait up to 10s for any success indicator, then navigate to `https://www.linkedin.com/in/me/recent-activity/all/`. Wait 3s for page load. Extract `href` from the first `a[href*="/feed/update/"]` element. This is the most recent post's permanent URL.

**Why this works:** LinkedIn's recent activity page always lists posts in reverse chronological order. The post we just made will be first.

**Fallback:** If no `/feed/update/` link found, use `https://www.linkedin.com/in/me/recent-activity/all/` as the URL (better than nothing — at least it's a page where the post exists).

**Expected URL format:** `https://www.linkedin.com/feed/update/urn:li:activity:{numeric_id}/`

#### Facebook

**Primary approach:** After posting, navigate to `https://www.facebook.com/me`. Wait 3s. Look for the first `a[href*="/posts/"]` or `a[href*="/permalink/"]` link in the feed. Facebook's profile page shows posts in reverse chronological order.

**Why this works:** Facebook profile pages show the user's own posts. The most recent post will be at the top.

**Fallback approach:** If no permalink found (Facebook's React UI is heavily obfuscated), use `https://www.facebook.com/me` as the URL. This is the current behavior and is acceptable because Facebook consistently blocks post URL extraction. The metric scraper can still try to scrape the profile page for the most recent post's engagement.

**Expected URL format:** `https://www.facebook.com/{user_id}/posts/{post_id}` or `https://www.facebook.com/permalink.php?story_fbid={id}`

#### Reddit

**Primary approach:** After clicking Post, poll `page.url` for up to 15s (check every 2s) looking for `/comments/` in the URL. Reddit redirects from the submit page to `/r/{subreddit}/comments/{id}/` on success.

**Alternative:** Check for `?created=t3_` query parameter in the redirect URL. Extract the post ID from `t3_XXXXX` and construct the URL as `https://www.reddit.com/user/{username}/comments/{post_id}/`.

**Fallback:** Navigate to `https://www.reddit.com/user/{username}/submitted/`, wait 2s, extract `href` from the first `a[href*="/comments/"]`.

**Expected URL format:** `https://www.reddit.com/r/{subreddit}/comments/{post_id}/` or `https://www.reddit.com/user/{username}/comments/{post_id}/`

### Implementation Details

**Where to change:** `config/scripts/linkedin_post.json`, `config/scripts/facebook_post.json`, `config/scripts/reddit_post.json`. Each script's `extract_url` section needs updating.

**Optional step support:** Add `"optional": true` field to `ScriptStep` in `scripts/engine/script_parser.py`. When a step fails and `optional` is `true`, log a warning but continue execution. This allows the primary URL extraction to fail gracefully and fall back to the secondary approach.

**`posted_no_url` handling:** Posts that fail URL extraction entirely should still be marked `posted_no_url` (not `failed`). The post went live — we just can't find the URL. These posts can be manually URL-captured later or skipped by the metric scraper.

### Verification

1. Post to LinkedIn. Check `local_post.post_url` contains `/feed/update/`. If not, check it contains `/recent-activity/`.
2. Post to Facebook. Check `local_post.post_url` contains `/posts/` or `/permalink/` or at minimum `facebook.com/me`.
3. Post to Reddit. Check `local_post.post_url` contains `/comments/`.
4. Post to X. Confirm it still works (regression check). URL should contain `/status/`.
5. Temporarily break a URL selector. Confirm post is marked `posted_no_url`, not `failed`.

---

## Task #9 — Metric Scraping (Detailed Spec Per Platform)

### What Metric Scraping Does

After a post goes live, the background agent revisits the post URL at scheduled intervals to scrape engagement metrics. These metrics are the billing input — the numbers that determine how much the user earns.

### Scraping Schedule

Scrape **once every 24 hours** for the **lifetime of the campaign** (until campaign status is `completed`, `cancelled`, or `expired`).

Every scrape is stored. The **latest scrape** is the billing source of truth — billing always uses the most recent metric values for each post.

No tiered schedule. No `is_final` flag needed. Simple: every 24h, revisit the post URL and record current engagement numbers.

### Metrics Available Per Platform (from actual UI — confirmed via screenshots)

Not all metrics are visible on all platforms. Only scrape what's actually shown on the post page:

| Metric | X | LinkedIn | Facebook | Reddit |
|--------|---|----------|----------|--------|
| **Views** | YES | NO | NO | NO |
| **Likes** | YES | YES (reactions count) | YES | YES (upvote score) |
| **Comments** | YES | YES | YES | YES |
| **Reposts/Shares** | YES | YES (reposts) | YES (shares) | NO |

**Important:** Impressions/views are ONLY available on X. LinkedIn, Facebook, and Reddit do not show view counts on post pages. The billing formula must account for this — `rate_per_1k_views` only generates earnings on X posts.

### Per-Platform Scraping Logic

#### X (Twitter)

**Scrapes:** views, likes, comments, reposts

1. Navigate to the post URL (`https://x.com/{user}/status/{id}`)
2. Wait for page load (5s timeout)
3. Find the engagement metrics bar: `[role="group"]` containing `[aria-label]` elements
4. Parse aria-labels for: "view" → views, "like" → likes, "repost" → reposts, "repl"/"comment" → comments
5. Extract numbers (handle abbreviated: "1.2K" → 1200, "3.4M" → 3400000)

**Edge cases:**
- Post deleted: "This post is unavailable" or 404 → mark `local_post.status = "deleted"`, stop future scraping
- Account suspended: "Account suspended" → mark deleted
- Rate limited: CAPTCHA → skip this scrape

#### LinkedIn

**Scrapes:** likes (reactions), comments, reposts. NO views.

1. Navigate to the post URL (`https://www.linkedin.com/feed/update/urn:li:activity:{id}/`)
2. Wait for page load (5s timeout)
3. Find reactions count: text like "X and 292 others" or `.social-details-social-counts__reactions-count` → extract number
4. Find comments: text containing "X comments" → extract number
5. Find reposts: text containing "X repost" → extract number
6. Set views/impressions = 0 (not available on LinkedIn post page)

**Edge cases:**
- Post deleted: "This content isn't available" → mark deleted
- Login required: redirect to login → mark session expired, skip
- Zero engagement is valid — store zeros

#### Facebook

**Scrapes:** likes, comments, shares. NO views.

1. Navigate to the post URL
2. Wait for page load (5s)
3. Find likes: number next to thumbs-up icon or `[aria-label*="reaction"]` → parse count
4. Find comments: number next to comment icon, or text containing "X comments" → parse
5. Find shares: number next to share icon, or text containing "X shares" → parse
6. Set views/impressions = 0 (not available on Facebook post page)

**Edge cases:**
- Facebook blocks non-logged-in access → Playwright uses persistent profile
- Post URL is `facebook.com/me` (fallback) → find most recent post on profile
- "Content not available" → mark deleted

#### Reddit

**Scrapes:** likes (upvote score), comments. NO reposts, NO views.

1. Navigate to the post URL (`https://www.reddit.com/r/{sub}/comments/{id}/`)
2. Wait for page load (5s)
3. Find upvote score: number between up/down arrows, or `shreddit-post[score]` attribute
4. Find comments: number next to comment icon, or `shreddit-post[comment-count]` attribute
5. Set reposts = 0, views = 0 (not available on Reddit)

**Edge cases:**
- Post removed: "[removed]" or "[deleted]" → mark deleted
- Subreddit private/banned → mark deleted
- Score is negative → store as-is (valid data)

### Number Parsing

All scrapers must handle abbreviated numbers:
- "1,234" → 1234
- "1.2K" → 1200
- "3.4M" → 3400000
- "12K" → 12000
- Empty / null / "—" → 0

### Deleted Post Detection

Each platform scraper checks for deletion indicators FIRST before trying to extract metrics:

| Platform | Deletion Indicators |
|----------|-------------------|
| X | "This post is unavailable", "Account suspended", "This post was deleted", HTTP 404 |
| LinkedIn | "This content isn't available", "This page doesn't exist" |
| Facebook | "This content isn't available", "Sorry, this content isn't available" |
| Reddit | "[removed]", "[deleted]", "This post was removed", HTTP 404 |

When a deleted post is detected:
1. Set `local_post.status = "deleted"`
2. Do NOT store a zero-metric row (would look like engagement dropped to zero)
3. Stop all future scraping for this post
4. Notify server via `update_post_status()` → triggers `void_earnings_for_post()` if within 7-day hold

### Rate Limit Handling

When a platform returns a CAPTCHA, login page, or rate limit indicator:
1. Skip this scrape (do NOT store zero metrics)
2. Increment a per-platform consecutive limit counter
3. After 3 consecutive rate limits, skip ALL scraping for that platform for 1 hour
4. Log: "Rate limited on {platform}, skipping for 1 hour"

### Storage

Each scrape creates one row in `local_metric`:
```
post_id, impressions, likes, reposts, comments, clicks=0, scraped_at, reported=0
```

Note: `impressions` will be 0 for LinkedIn/Facebook/Reddit (only X has views). `reposts` will be 0 for Reddit. `clicks` is always 0 (not scrapeable).

### Server Sync

After scraping, `sync_metrics_to_server()`:
1. Query `local_metric WHERE reported = 0 AND post has server_post_id`
2. Send batch to `POST /api/metrics`
3. Mark as `reported = 1`
4. Server-side billing triggers automatically on metric submission

### Verification

1. Post to X. Wait 65+ min. Run scraper. Expect: 1 metric row with non-zero impressions or likes.
2. Post to LinkedIn. Run scraper after T+1h. Expect: non-zero reactions.
3. Simulate T+72h: manually set `posted_at` to 73 hours ago. Run scraper. Expect: `is_final = 1`.
4. Run scraper twice quickly. Expect: no duplicate metric rows.
5. Delete a post on X. Run scraper. Expect: `local_post.status = "deleted"`, no zero-metric row.

---

## Task #10 — Billing (Detailed Spec)

### What Billing Does

Converts scraped metrics into user earnings. Reads payout rules from the campaign, applies per-metric rates, deducts platform cut (20%), applies tier CPM multiplier, caps to remaining budget, creates Payout records with 7-day hold.

### Billing Trigger

Billing runs when metrics are submitted to the server via `POST /api/metrics`. The server processes each metric and creates earnings records.

### Earnings Formula

```
raw_cents = (views / 1000 * rate_per_1k_views_cents)    # X only — other platforms have 0 views
          + (likes * rate_per_like_cents)                 # all platforms
          + (comments * rate_per_comment_cents)           # all platforms
          + (reposts * rate_per_repost_cents)             # X, LinkedIn, Facebook only — Reddit has 0

platform_cut = 0.20  (20%)
user_earning_cents = raw_cents * (1 - platform_cut)

# Apply tier CPM multiplier (Amplifier tier = 2x)
if user.tier == "amplifier":
    user_earning_cents = user_earning_cents * 2

# Cap to remaining budget
budget_cost_cents = raw_cents  # full cost deducted from campaign
if budget_cost_cents > campaign.budget_remaining_cents:
    budget_cost_cents = campaign.budget_remaining_cents
    user_earning_cents = budget_cost_cents * (1 - platform_cut)
```

### Payout rates (set by company per campaign)

| Rate Field | What it pays for | Available on | Example |
|-----------|-----------------|-------------|---------|
| rate_per_1k_views | Views/impressions | X only | $0.50/1K |
| rate_per_like | Likes, reactions, upvotes | All 4 platforms | $0.01/like |
| rate_per_comment | Comments, replies | All 4 platforms | $0.02/comment |
| rate_per_repost | Reposts, shares | X, LinkedIn, Facebook (not Reddit) | $0.05/repost |

All rates stored and calculated in **integer cents** internally. `rate_per_click` removed — clicks not scrapeable.

**Implication for companies:** Reddit-only campaigns should set higher `rate_per_like` and `rate_per_comment` since views and reposts aren't available. The campaign wizard should suggest appropriate rates per platform.

### Deduplication

Each metric submission includes a `metric_id`. The billing system tracks which metrics have already been billed via `Payout.breakdown["metric_id"]`. If a metric ID has already been billed, skip it.

### Budget Management

| Event | Action |
|-------|--------|
| `budget_remaining < $1.00` | Auto-pause or auto-complete campaign (based on `budget_exhaustion_action` setting) |
| `budget_remaining < 20% of budget_total` | Send budget alert to company (once, set `budget_alert_sent = True`) |
| Campaign cancelled | Refund `budget_remaining` to `company.balance_cents` |

### Hold Period

Every Payout is created with:
- `status = "pending"`
- `available_at = created_at + 7 days`

`promote_pending_earnings()` runs periodically and moves payouts from `pending` → `available` when `available_at <= now`.

During the hold period, `void_earnings_for_post()` can cancel earnings if:
- Post is detected as deleted
- Metrics are flagged as anomalous
- Admin manually voids

Voided earnings return funds to `campaign.budget_remaining`.

### Tier Promotion

After each successful billing:
1. Increment `user.successful_post_count`
2. Check promotion rules:
   - 20+ posts → Grower (from Seedling)
   - 100+ posts AND trust_score >= 80 → Amplifier (from Grower)
3. Amplifier tier gets **2x CPM multiplier** on all future earnings

### What Billing Outputs

For each billed metric:
1. `Payout` record with `amount_cents`, `status="pending"`, `available_at`, `breakdown` (JSON with metric details)
2. `user.earnings_balance_cents` incremented
3. `user.total_earned_cents` incremented
4. `campaign.budget_remaining` decremented
5. `user.successful_post_count` incremented

### Verification

1. X post with `rate_per_1k_views = $0.50`, `rate_per_like = $0.01`, `rate_per_comment = $0.02`. Metric: 1000 views, 10 likes, 5 comments. Expected earning: (50 + 10 + 10) * 0.80 = 56 cents.
2. Same metric ID submitted twice. Expect: no duplicate Payout.
3. Campaign with `budget_remaining = $1.00`. Metric that would earn $3.00. Expect: earning capped. Campaign status changes.
4. Amplifier tier user. Submit metric. Expect: earning doubled (2x multiplier).
5. Run `promote_pending_earnings()` on a 8-day-old payout. Expect: status changes from `pending` to `available`.
6. Void a pending payout. Expect: funds return to campaign budget.

---

## Task #11 — Earnings Display + Withdrawal (Detailed Spec)

### Status: TEST FIRST

Earnings display showed $0.55 in the dashboard during testing. **Test the full flow first (post → metrics → billing → earnings page). Only fix if broken.** The spec below documents the expected behavior and fix strategy.

### Problem (if broken)

The server calculates earnings correctly, but the user app may show $0 if there's no sync mechanism from server `Payout` records to the local `local_earning` table.

### Data Flow

```
Server billing creates Payouts
    ↓
User app calls GET /api/users/me/earnings
    ↓
Response: {total_earned, current_balance, pending, per_campaign, payout_history}
    ↓
User app stores in local_earning table (cache)
    ↓
Dashboard and Earnings page read from local_earning
```

### Server Earnings Endpoint

`GET /api/users/me/earnings` should return:

```json
{
  "total_earned_cents": 4500,
  "available_balance_cents": 2000,
  "pending_balance_cents": 2500,
  "per_campaign": [
    {
      "campaign_id": 1,
      "campaign_title": "Smart Money Indicator Beta",
      "earned_cents": 3000,
      "pending_cents": 1500,
      "available_cents": 1500,
      "post_count": 5
    }
  ],
  "payout_history": [
    {
      "id": 1,
      "amount_cents": 1000,
      "status": "paid",
      "created_at": "2026-04-01T...",
      "available_at": "2026-04-08T..."
    }
  ]
}
```

### Local Sync

After fetching earnings from server, update `local_earning` table:
1. For each campaign in `per_campaign`, upsert a row in `local_earning`
2. Update the `amount` and `status` fields
3. The dashboard reads from `local_earning` for display

This sync happens:
- On every page load of `/earnings`
- On dashboard load (summary only — total_earned)
- After the background agent polls campaigns (piggyback on the poll cycle)

### Withdrawal Flow

1. User clicks "Withdraw" on the Earnings page
2. User enters amount (minimum $10.00 = 1000 cents)
3. App calls `POST /api/users/me/payout` with `{"amount_cents": 1000}`
4. Server validates:
   - `amount_cents >= 1000` (minimum $10)
   - `amount_cents <= user.earnings_balance_cents` (can't withdraw more than available)
   - User has `stripe_account_id` set (Stripe Connect onboarded) — if not, return error "Connect your bank account first"
5. Server creates Payout with `status = "processing"`
6. Server decrements `user.earnings_balance_cents` by amount
7. Response: `{"success": true, "payout_id": X}`
8. Actual Stripe transfer happens in `process_pending_payouts()` batch job

### Display on User App

**Dashboard card:** Shows `total_earned` (all time) from `GET /api/users/me/earnings`

**Earnings page sections:**
1. **Summary cards:** Total Earned | Available Balance | Pending (in hold)
2. **Per-campaign breakdown:** Table with campaign title, earned, pending, available, post count
3. **Payout history:** Table with amount, status, date
4. **Withdraw button:** Enabled when `available_balance >= $10.00`

### Verification

1. Create campaign, post, submit metrics, run billing. Visit `/earnings`. Expect: `total_earned > 0`.
2. Verify `pending` shows payouts in 7-day hold. Verify `available` shows only post-hold earnings.
3. Click withdraw $10 (when balance >= $10). Expect: server returns success, balance decremented.
4. Dashboard card shows same `total_earned` as earnings page.
5. Refresh earnings page. Expect: data matches server (local_earning synced).
