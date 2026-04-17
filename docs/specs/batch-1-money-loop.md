# Batch 1: Money Loop — Product Spec

**Tasks:** #1 (URL capture), #9 (metric scraping), #10 (billing), #11 (earnings display)

These four tasks form the core money loop: post goes live -> URL captured -> metrics scraped -> billing calculates earnings -> user sees money. If any link breaks, nobody gets paid.

---

## Task #1 — Post URL Capture

### Status: TEST FIRST

URL capture worked in previous testing sessions. Test all 4 platforms first. Only fix what is broken.

### Problem

After posting, the system must capture the post's permanent URL so the metric scraper can revisit it later. Without URLs, the metric scraper has nothing to visit, billing has no metrics to process, and users earn $0.

**Last known state per platform:**

| Platform | Status | Issue |
|----------|--------|-------|
| X | DISABLED (2026-04-14) — code preserved. See Task #40. | Finds the `/status/` URL from the profile page |
| LinkedIn | May fail | Waits for a "View post" dialog that doesn't appear for text-only posts |
| Facebook | May fail | Returns the profile URL, not the actual post URL |
| Reddit | May fail | Redirect to `/comments/` is not detected |

### URL Capture Strategy Per Platform

#### LinkedIn

- **Primary:** After posting, navigate to the user's recent activity page. The most recent post (just created) will be first. Extract the permanent URL.
- **Fallback:** If no permanent post link is found, use the recent activity page URL itself (the post exists there).
- **Expected URL format:** `https://www.linkedin.com/feed/update/urn:li:activity:{id}/`

#### Facebook

- **Primary:** After posting, navigate to the user's profile. The most recent post will be at the top. Extract the post permalink.
- **Fallback:** If no permalink is found (Facebook's UI is heavily obfuscated), use the profile URL. The metric scraper can still attempt to find the most recent post's engagement on the profile page.
- **Expected URL format:** `https://www.facebook.com/{user_id}/posts/{post_id}` or `https://www.facebook.com/permalink.php?story_fbid={id}`

#### Reddit

- **Primary:** After clicking Post, wait up to 15 seconds for a redirect to the `/comments/` URL (Reddit redirects from the submit page to the new post on success).
- **Alternative:** Check for a `?created=` query parameter in the redirect URL and construct the post URL from the extracted post ID.
- **Fallback:** Navigate to the user's submitted posts page and extract the URL of the most recent post.
- **Expected URL format:** `https://www.reddit.com/r/{subreddit}/comments/{post_id}/`

### Business Rules

- A post that succeeds but fails URL extraction must be marked `posted_no_url` (not `failed`). The post went live -- we just cannot find the URL. These posts can be manually URL-captured later or skipped by the metric scraper.
- The URL extraction step should be non-blocking: if it fails, the post is still considered successful.

### Acceptance Criteria

1. LinkedIn post URL contains `/feed/update/` or at minimum `/recent-activity/`.
2. Facebook post URL contains `/posts/` or `/permalink/` or at minimum is a profile URL.
3. Reddit post URL contains `/comments/`.
4. X post URL still contains `/status/` (regression check). _(N/A while X disabled — see Task #40)_
5. When URL extraction fails entirely, the post is marked `posted_no_url`, not `failed`.

---

## Task #9 — Metric Scraping

### What Metric Scraping Does

After a post goes live, the system revisits the post URL at scheduled intervals to scrape engagement metrics. These metrics are the billing input -- the numbers that determine how much the user earns.

### Scraping Schedule

Scrape **once every 24 hours** for the **lifetime of the campaign** (until campaign status is `completed`, `cancelled`, or `expired`).

Every scrape is stored. The **latest scrape** is the billing source of truth -- billing always uses the most recent metric values for each post.

No tiered schedule. No final-scrape flag. Simple: every 24 hours, revisit the post URL and record current engagement numbers.

### Metrics Available Per Platform

Not all metrics are visible on all platforms. Only scrape what is actually shown on the post page:

| Metric | X | LinkedIn | Facebook | Reddit |
|--------|---|----------|----------|--------|
| **Views** | YES | NO | NO | YES |
| **Likes** | YES | YES (reactions count) | YES | YES (upvote score) |
| **Comments** | YES | YES | YES | YES |
| **Reposts/Shares** | YES | YES (reposts) | YES (shares) | NO |

**Key implication:** Views are available on X and Reddit. LinkedIn and Facebook do not show view counts on post pages. The billing formula accounts for this -- `rate_per_1k_views` generates earnings on X and Reddit posts. _(X disabled 2026-04-14; applies to Reddit only until X is re-enabled)_

### Per-Platform Scraping Behavior

#### X (Twitter)

**Scrapes:** views, likes, comments, reposts

Navigate to the post URL. Extract engagement metrics from the metrics bar (views, likes, reposts, comments). Handle abbreviated numbers (e.g., "1.2K" = 1,200).

**Edge cases:**
- Post deleted or account suspended: mark post as `deleted`, stop future scraping
- Rate limited / CAPTCHA: skip this scrape, do not store zero metrics

#### LinkedIn

**Scrapes:** likes (reactions), comments, reposts. NO views.

Navigate to the post URL. Extract reactions count, comments count, and reposts count. Views are not available -- store as 0.

**Edge cases:**
- Post deleted ("This content isn't available"): mark post as `deleted`
- Redirect to login page: mark session as expired, skip this scrape
- Zero engagement is valid -- store zeros

#### Facebook

**Scrapes:** likes, comments, shares. NO views.

Navigate to the post URL. Extract likes, comments, and shares counts. Views are not available -- store as 0.

**Edge cases:**
- Facebook blocks non-logged-in access: the system uses persistent browser profiles
- Post URL is the profile URL (fallback from Task #1): find the most recent post on the profile page
- "Content not available": mark post as `deleted`

#### Reddit

**Scrapes:** likes (upvote score), comments. NO reposts, NO views.

**Scrapes:** likes (upvote score), comments, views. NO reposts.

**Preferred method:** Use Playwright browser scraping as the primary method. Reddit post pages show view counts in the UI (e.g., "1,234 views") which PRAW cannot access. Extract views from the post page along with score and comment count.

**Alternative:** Use Reddit API (PRAW) for score and comment count if Playwright scraping fails. PRAW is free and reliable (60 req/min rate limit) but does NOT return view counts -- store views as 0 when using PRAW only.

Reposts are not available on Reddit -- store as 0.

**Edge cases:**
- Post removed or subreddit is private/banned: mark post as `deleted`
- Negative upvote score: store as-is (valid data)

### Number Parsing

All scrapers must handle abbreviated numbers:

| Raw Value | Parsed |
|-----------|--------|
| "1,234" | 1234 |
| "1.2K" | 1200 |
| "12K" | 12000 |
| "3.4M" | 3400000 |
| Empty / null / "--" | 0 |

### Deleted Post Detection

Each platform has specific deletion indicators that must be checked BEFORE attempting metric extraction:

| Platform | Deletion Indicators (verified against real deleted posts) |
|----------|-------------------|
| X | "This post is unavailable", "This account doesn't exist", "This post was deleted", "Hmm...this page doesn't exist" (unicode-normalized), "Account suspended", "Page not found", HTTP 404 via API |
| LinkedIn | "This content isn't available", "This page doesn't exist", "This post has been removed", "This post cannot be displayed", "Content unavailable" |
| Facebook | "This content isn't available", "This page isn't available", "The link you followed may be broken", "Content not found", "This post is no longer available", "Content isn't available right now". Also detects author-deleted posts via permalink: if permalink URL loads but shows "No more posts" (empty feed), the post is gone. |
| Reddit | "Sorry, this post was removed/deleted", "This post was removed/deleted by", "This post has been removed", "This post is no longer available", "Page not found". Also checks `shreddit-post[removed="true"]` attribute for mod removals AND `shreddit-post[author="[deleted]"]` / `is-author-deleted` attribute for user-deleted posts. Note: `[deleted]`/`[removed]` NOT used in body text search (causes false positives from deleted comments). |

**When a deleted post is detected:**
1. Mark the post status as `deleted`
2. Do NOT store a zero-metric row (it would look like engagement dropped to zero and would distort billing)
3. Stop all future scraping for this post
4. Notify the server via `PATCH /api/posts/{id}/status` → `void_earnings_for_post()` voids pending payouts, returns funds to campaign budget

### Rate Limit Handling

When a platform returns a CAPTCHA, login page, or rate limit indicator:
1. Skip this scrape (do NOT store zero metrics)
2. Track consecutive rate limits per platform
3. After 3 consecutive rate limits, skip ALL scraping for that platform for 1 hour

### Server Sync

After each scraping run, unreported metrics are batched and sent to the server. The server triggers billing automatically upon receiving new metrics.

### Acceptance Criteria

1. X post scraped after 24+ hours returns non-zero views or likes. _(N/A while X disabled — see Task #40)_
2. LinkedIn post scraped returns reactions count.
3. Reddit post scraped returns view count, upvote score, and comment count.
4. Facebook post scraped returns likes, comments, or shares.
5. Running the scraper twice in quick succession does not create duplicate metric rows.
6. Deleting a post on any platform results in the post being marked `deleted` with no zero-metric row stored.
7. Metrics are synced to the server after each scraping run.
8. After 3 consecutive rate limits on a platform, scraping for that platform pauses for 1 hour.

---

## Task #10 — Billing

### What Billing Does

Converts scraped metrics into user earnings. Reads payout rates from the campaign, applies per-metric rates, deducts the platform cut (20%), applies tier multiplier, caps to remaining campaign budget, and creates payout records with a 7-day hold.

### Billing Trigger

Billing runs when metrics are submitted to the server. The server processes each metric and creates earnings records.

### Earnings Formula

```
raw_cents = (views / 1000 * rate_per_1k_views_cents)    -- X and Reddit; LinkedIn/Facebook have 0 views
           + (likes * rate_per_like_cents)                -- all platforms
           + (comments * rate_per_comment_cents)          -- all platforms
           + (reposts * rate_per_repost_cents)            -- X, LinkedIn, Facebook only; Reddit has 0

platform_cut = 20%
user_earning_cents = raw_cents * (1 - platform_cut)

-- Tier multiplier
If user is Amplifier tier: user_earning_cents = user_earning_cents * 2

-- Budget cap
budget_cost_cents = raw_cents  (full cost before platform cut, deducted from campaign)
If budget_cost_cents > campaign remaining budget:
    budget_cost_cents = campaign remaining budget
    user_earning_cents = budget_cost_cents * (1 - platform_cut)
```

### Payout Rates (Set by Company Per Campaign)

| Rate | What It Pays For | Available On | Example |
|------|-----------------|--------------|---------|
| rate_per_1k_views | Views / impressions | X, Reddit | $0.50 per 1K views |
| rate_per_like | Likes, reactions, upvotes | All 4 platforms | $0.01 per like |
| rate_per_comment | Comments, replies | All 4 platforms | $0.02 per comment |
| rate_per_repost | Reposts, shares | X, LinkedIn, Facebook (not Reddit) | $0.05 per repost |

All rates are stored and calculated in **integer cents** internally. There is no rate for clicks -- clicks are not scrapeable.

**Implication for companies:** Reddit-only campaigns should set higher `rate_per_like` and `rate_per_comment` since reposts are not available. Views ARE available on Reddit, so `rate_per_1k_views` applies. The campaign creation wizard should suggest appropriate rates based on the target platforms.

### Deduplication

Each metric submission includes a unique metric ID. The billing system tracks which metrics have already been billed. If a metric ID has already been processed, it is skipped. No duplicate payouts are created.

### Budget Management

| Event | Action |
|-------|--------|
| Remaining budget < $1.00 | Auto-pause or auto-complete campaign (based on campaign setting) |
| Remaining budget < 20% of total budget | Send one-time budget alert to the company |
| Campaign cancelled | Refund remaining budget to company balance |

### 7-Day Hold Period

Every payout is created with a 7-day hold:
- **Status:** `pending`
- **Available date:** creation date + 7 days

A periodic job promotes payouts from `pending` to `available` when the hold period expires.

During the hold period, earnings can be voided if:
- The post is detected as deleted
- Metrics are flagged as anomalous (fraud detection)
- An admin manually voids the payout

Voided earnings return funds to the campaign's remaining budget.

### Tier Promotion

After each successful billing event:
1. Increment the user's successful post count
2. Check promotion thresholds:
   - **Seedling -> Grower:** 20+ successful posts
   - **Grower -> Amplifier:** 100+ successful posts AND trust score >= 80
3. Amplifier tier earns a **2x multiplier** on all future earnings

### What Billing Produces

For each billed metric:
1. A payout record with the earning amount, `pending` status, available date, and a breakdown of which metrics contributed
2. User's earnings balance incremented
3. User's lifetime total earned incremented
4. Campaign's remaining budget decremented
5. User's successful post count incremented

### Acceptance Criteria

1. X post with `rate_per_1k_views = $0.50`, `rate_per_like = $0.01`, `rate_per_comment = $0.02`. Metric: 1,000 views, 10 likes, 5 comments. Expected earning: (50 + 10 + 10) * 0.80 = 56 cents.
2. Submitting the same metric ID twice produces no duplicate payout.
3. Campaign with $1.00 remaining budget. Metric that would earn $3.00. Earning is capped to the remaining budget. Campaign status changes.
4. Amplifier-tier user submits a metric. Earning is doubled (2x multiplier applied).
5. A payout older than 7 days is promoted from `pending` to `available`.
6. Voiding a pending payout returns funds to the campaign budget.
7. A user reaching 20 successful posts is promoted from Seedling to Grower.
8. A user reaching 100 successful posts with trust score >= 80 is promoted from Grower to Amplifier.

---

## Task #11 — Earnings Display and Withdrawal

### Status: TEST FIRST

Earnings display showed $0.55 in a previous testing session. Test the full flow first (post -> metrics -> billing -> earnings page). Only fix what is broken.

### Data Flow

```
Server calculates earnings and creates payout records
    |
    v
User app fetches earnings summary from server
    |
    v
Response includes: total earned, available balance, pending balance,
                    per-campaign breakdown, payout history
    |
    v
User app caches earnings data locally
    |
    v
Dashboard and Earnings page display from local cache
```

### Earnings API Response

The server returns the following earnings summary to the user app:

- **total_earned_cents** -- lifetime earnings (all time)
- **available_balance_cents** -- earnings past the 7-day hold, available for withdrawal
- **pending_balance_cents** -- earnings still in the 7-day hold period
- **per_campaign** -- breakdown per campaign: campaign name, total earned, pending, available, post count
- **payout_history** -- list of all payouts: amount, status, creation date, available date

### Sync Triggers

The user app syncs earnings data from the server:
- On every page load of the Earnings page
- On Dashboard load (summary total only)
- After each campaign polling cycle (piggyback on the existing poll)

### Withdrawal Flow

1. User clicks "Withdraw" on the Earnings page
2. User enters an amount (minimum: $10.00)
3. The system validates:
   - Amount >= $10.00 minimum
   - Amount <= user's available balance (cannot withdraw more than earned)
   - User has connected a bank account (Stripe Connect onboarded). If not, return an error: "Connect your bank account first"
4. A payout record is created with `processing` status
5. User's available balance is decremented by the withdrawal amount
6. Actual bank transfer is processed in a background batch job via Stripe Connect

### User Interface

**Dashboard card:** Shows total lifetime earnings.

**Earnings page sections:**
1. **Summary cards:** Total Earned | Available Balance | Pending (in hold)
2. **Per-campaign breakdown:** Table showing campaign name, earned, pending, available, post count
3. **Payout history:** Table showing amount, status, date
4. **Withdraw button:** Enabled only when available balance >= $10.00

### Acceptance Criteria

1. After completing the full loop (post -> metrics -> billing), the Earnings page shows total earned > $0.
2. Pending balance reflects payouts still within the 7-day hold period.
3. Available balance reflects only payouts past the 7-day hold.
4. Clicking Withdraw with a valid amount ($10+, within available balance) succeeds and decrements the balance.
5. Clicking Withdraw without a connected bank account shows "Connect your bank account first."
6. Clicking Withdraw for more than the available balance is rejected.
7. Dashboard card and Earnings page show consistent total earned figures.
8. Refreshing the Earnings page pulls fresh data from the server.
