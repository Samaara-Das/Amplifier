# Amplifier Product Spec v2

**Status**: Draft — pending founder review
**Date**: 2026-03-24

---

## What Amplifier Is

A two-sided marketplace where companies pay to have their campaigns promoted on social media, and users earn money by posting that content. Amplifier handles the matching, content generation, posting, metric tracking, and payments. Both sides interact through dedicated apps — neither side talks to the other directly.

---

## The Three Apps

### 1. User App (Tauri Desktop — blue/white theme)

A desktop app that runs in the background. Users open it to manage campaigns, review content, and track earnings. Posting happens headlessly in the background on schedule.

### 2. Company Dashboard (Web — blue/white theme)

A web app where companies create campaigns (AI-assisted), monitor performance, and manage budgets. Hosted on Vercel alongside the API.

### 3. Admin Dashboard (Web — blue/white theme)

Internal tool for platform management. Lowest priority — existing functionality is mostly sufficient.

---

## User App — Feature Spec

### Onboarding (first launch)

1. **Register/Login** — Email + password. Creates account on server.
2. **Connect Platforms** — For each platform (X, LinkedIn, Facebook, Reddit), Amplifier opens a browser window. User logs in manually. Session saved. No usernames or passwords entered into Amplifier — authentication happens directly on the platform.
3. **Profile Scraping** — After connecting each platform, Amplifier automatically scrapes:
   - Follower/following count
   - Bio/about text
   - Recent posts (last 30-60 days) — content, engagement metrics, posting frequency
   - Profile picture, display name
   - AI classifies the user's niche(s) from their actual content (not just checkboxes)
4. **Niche Confirmation** — Amplifier shows its AI-detected niches and lets the user confirm or adjust via multi-select checkboxes (finance, tech, beauty, fashion, fitness, gaming, food, travel, education, lifestyle, business, health, entertainment, crypto).
5. **Audience Region** — "Where is most of your audience?" (US, UK, India, EU, Latin America, Southeast Asia, Global)
6. **Operating Mode** — Choose how to participate:
   - Semi-auto (recommended): AI generates content, you review/edit before posting.
   - Full-auto: AI generates and posts automatically.
   - Manual: You write your own content from the brief.
   Payout is the same regardless of mode — earnings depend purely on post engagement metrics.
7. **Done** — Show profile summary, confirm everything works.

Content generation uses Amplifier's own API keys (bundled with the app). Users never need to create or manage API keys.

No CLI. No typing usernames. No self-reporting follower counts. Amplifier figures it out.

### Home / Dashboard

The main screen when you open the app. Shows at a glance:

- **Active Campaigns** — count + total potential earnings
- **Pending Invitations** — new campaigns waiting for accept/reject
- **Posts Queued** — content approved and waiting to post
- **Earnings Balance** — current withdrawable amount
- **Platform Health** — green/yellow/red status per connected platform (session valid, expiring, expired)
- **Recent Activity** — last 5 events (campaign accepted, post published, earnings received, etc.)

### Campaigns Tab

Three sections:

**Invitations** — New campaign matches from the server.
- Card per campaign: title, brief summary, payout rates, estimated earnings, platforms required, deadline (3-day expiry)
- Actions: Accept, Reject, View Details
- Expired invitations auto-dismiss after 3 days
- Rejecting is permanent for that campaign
- Multiple users receive the same campaign invitation — it's not exclusive
- **Max 5 active campaigns at a time.** User must complete or drop a campaign before accepting a new one. Limit may increase for high-trust users in the future.

**Active** — Campaigns the user has accepted and is working on.
- Status per campaign: content generating → pending review → approved → scheduled → posted → metrics collecting → paid
- Expand to see per-platform post status

**Completed** — Past campaigns with final metrics and earnings.

### Posts Tab

All content across all campaigns, organized by status:

**Pending Review** — AI-generated content waiting for user approval.
- Per-platform preview (X, LinkedIn, Facebook, Reddit shown separately)
- Edit per platform independently (change X text without touching LinkedIn)
- Regenerate per platform with AI (one click, new version)
- Image preview + option to regenerate image
- Approve all / Approve individual platforms
- Skip (decline to post this campaign)

**Scheduled** — Approved content queued for posting.
- Shows scheduled post time (decided by Amplifier based on optimal engagement times and spacing rules)
- Can reschedule or cancel before post time

**Posted** — Successfully published.
- Post URL per platform (clickable)
- Engagement metrics (impressions, likes, reposts, comments) — updates as scraping happens
- Post status (live, deleted, flagged)

**Failed** — Posts that failed to publish.
- Error message (session expired, selector failed, timeout)
- Retry button
- Platform health link if session issue

### Earnings Tab

- **Balance** — current withdrawable amount
- **Total Earned** — lifetime earnings
- **Pending** — earnings being calculated (metrics not yet final)
- **Per-Campaign Breakdown** — table: campaign name, posts, impressions, engagement, earned, status
- **Per-Platform Breakdown** — which platforms earn the most
- **Payout History** — past withdrawals with status (pending, processing, paid, failed)
- **Withdraw Button** — request payout when balance > $10

### Settings Tab

- **Operating Mode** — switch between full_auto / semi_auto / manual
- **Connected Platforms** — status per platform, re-authenticate button, disconnect
- **Profile** — scraped data summary (follower counts, detected niches). Refresh button to re-scrape.
- **Posting Schedule** — view/adjust posting windows (Amplifier suggests optimal times)
- **Notifications** — toggle alerts for new campaigns, post failures, earnings received
- **Account** — email, change password, delete account

### Statistics (visible across tabs)

- Trust score (0-100) with explanation of what affects it
- Average engagement rate per platform
- Campaign completion rate
- Total campaigns completed
- Best performing platform
- Earnings trend (last 30 days chart)
- Post success rate per platform

### Background Agent (headless, always running)

Runs as a system tray icon. Handles:

- **Posting** — Publishes approved content at scheduled times via headless Playwright with human behavior emulation
- **Metric Scraping** — Revisits posts at T+1h, 6h, 24h, 72h to collect engagement data
- **Session Health** — Periodically checks each platform session is valid. Alerts user if expired. Does NOT block campaigns — just alerts.
- **Campaign Polling** — Checks server for new campaign invitations every 10 minutes
- **Post Failure Alerts** — If a post fails (session expired, platform error), alerts the user immediately
- **Profile Refresh** — Re-scrapes user profiles weekly to keep niche/follower data current

### Post Scheduling Rules

Amplifier decides when to post based on:
- Optimal engagement times per platform, based on the campaign's target region (e.g., US campaign posts during US peak hours, UK campaign during UK peak hours)
- Maximum campaign posts per day (depends on user's active campaigns and platforms)
- Minimum spacing between campaign posts (at least 30 mins apart)
- Platform variety (don't post to the same platform back-to-back for different campaigns)
- Random ordering to avoid patterns

---

## Company Dashboard — Feature Spec

### Campaign Creation (AI Wizard)

A step-by-step wizard where an AI assistant walks the company through campaign setup:

**Step 1: Campaign Basics**
- AI asks: "What product or service are you promoting?"
- AI asks: "What's the main goal? (Brand awareness, product launch, event promotion, lead generation)"
- AI asks: "Drop your company website and/or product page links"
- Amplifier scrapes the provided URLs (if accessible) to extract: company description, product details, brand voice, key selling points, images, pricing
- AI uses scraped data to pre-fill and enrich the campaign brief, content guidance, and suggested tone
- Company types answers or selects from options

**Step 2: Target Audience**
- AI asks: "Who should post about this?"
- Checkboxes: Niche categories (finance, tech, beauty, etc.)
- Checkboxes: Target regions (US, UK, EU, etc.)
- Checkboxes: Required platforms (X, LinkedIn, Facebook, Reddit)
- Slider/input: Minimum follower count per platform

**Step 3: Content Direction**
- AI asks: "What tone should the posts have?" (Professional, casual, funny, educational, inspirational)
- AI asks: "Any must-include phrases, links, or hashtags?"
- AI asks: "Anything to avoid?"
- Text inputs for each

**Step 4: Budget & Payout**
- AI suggests budget based on targeting scope: "Based on ~47 matching users with an estimated reach of 150K-300K impressions, we recommend a budget of $200-500."
- AI suggests payout rates based on industry averages
- Company adjusts: budget (minimum $50), rate per 1K impressions, per like, per repost, per click
- Start date, end date

**Step 5: Review & Edit**
- AI generates the full campaign: title, description, content guidance, targeting, payout rules, budget
- Company reads, edits any field directly
- Preview of how the campaign invitation will look to users
- Save as draft or activate immediately

**Step 6: Reach Estimation**
- Before activating, show: "~47 users match your criteria. Estimated reach: 150K-300K impressions. Estimated cost: $150-350."
- This updates live as the company changes targeting

### Campaign Management

**Campaign List**
- All campaigns with status badge (draft, active, paused, completed, cancelled)
- Quick stats: users reached, posts, impressions, engagement, budget spent/remaining
- Actions: View, Edit, Pause, Resume, Cancel, Clone
- Filter by status
- Sort by date, budget, performance

**Campaign Detail**
- **Overview Stats**: impressions, engagement, posts, unique users, budget spent, budget remaining, cost per impression, cost per engagement
- **Budget Progress Bar**: visual spend tracker with alert at 80%
- **Invitation Status**: how many users received the campaign, how many accepted, rejected, expired, pending
- **Per-User Performance Table**:
  - User identifier (display name or anonymized ID)
  - Platforms they posted to
  - Post URLs (clickable)
  - Impressions, likes, reposts, comments per post
  - Total earned by this user
  - Assignment status
- **Per-Platform Breakdown**: which platforms are delivering the best ROI
- **Timeline**: when posts went out, when metrics were collected
- **Actions**: Edit campaign (even if active), adjust budget, pause, cancel

**Campaign Editing (active campaigns)**
- Can edit: brief, content guidance, budget (increase only), end date, payout rates
- Cannot edit: targeting criteria (would invalidate existing matches)
- Changing payout rates only affects future posts, not already-billed ones
- **How edits propagate to users**:
  - Already posted content: untouched, earnings unaffected
  - Approved but not yet posted: flagged as "Campaign updated — please re-review" so user sees changes before posting
  - Not yet generated: uses updated brief automatically
  - User app picks up changes on next poll cycle (every 10 minutes)

**Campaign Cloning**
- Duplicate any campaign with new dates and budget
- Pre-fills everything from the original

### Budget Management

- **Company Balance**: top-up via Stripe (or placeholder for now)
- **Minimum Campaign Budget**: $50
- **Budget Alerts**: notification when campaign hits 80% spent
- **Budget Exhaustion**: company chooses per-campaign: auto-pause (can top up and resume) or auto-complete (campaign ends)
- **Budget Top-Up for Active Campaigns**: increase budget without creating a new campaign

### Company Statistics

- Total campaigns (all time)
- Active campaigns count
- Total spend (all time)
- Average cost per impression across all campaigns
- Average cost per engagement
- Best performing campaign (by ROI)
- Best performing platform
- Total reach (impressions across all campaigns)
- User retention (how many users accept invitations across multiple campaigns)
- Spend trend (last 30 days chart)

### Reporting & Export

- Download campaign report as CSV or PDF
- Includes: campaign details, per-user breakdown, per-platform stats, timeline, spend summary
- Filterable by date range

### Prohibited Content

Campaigns are screened at creation for prohibited categories:
- Adult / sexually explicit content
- Gambling
- Drugs / controlled substances
- Weapons
- Financial fraud / scams / get-rich-quick schemes
- Hate speech / discrimination

Automated keyword screening. Flagged campaigns require manual admin review before activation.

---

## Admin Dashboard — Feature Spec (low priority)

Existing functionality is mostly sufficient. Additions for this version:

- **Campaign Review Queue** — Flagged campaigns from automated screening. Admin approves or rejects.
- **Platform Stats** — Aggregate metrics: total posts per platform, success rate per platform, average engagement per platform
- Everything else (users, fraud, payouts, billing) already exists

---

## Matching Algorithm — Updated

The current matching uses self-reported niche tags and follower counts. The new version uses scraped data for much more accurate matching.

### Data Available Per User (from scraping)

- Follower count per platform (verified, not self-reported)
- Recent post content (last 30-60 days)
- AI-detected niches from actual content
- Engagement rate per platform (avg likes/comments per post relative to followers)
- Posting frequency
- Bio text
- Audience region (self-reported, verified where possible)

### Matching Flow

1. Company activates campaign
2. Server runs matching against all active users
3. **Hard filters**: required platforms connected, follower minimums met, desired niche, region matches, user not suspended, user not already invited to this campaign
4. **AI scoring**: campaign brief + user profile (scraped posts, bio, niches) fed to AI to score relevance 0-100
5. **Trust bonus**: user trust score contributes to ranking
6. **Engagement bonus**: users with higher engagement rates ranked higher
7. Top N users receive campaign invitations
8. Invitations expire after 3 days if not accepted/rejected
9. Expired/rejected slots can be re-offered to other matching users

### What Companies See

- Number of users invited
- Number accepted / rejected / expired / pending
- Per-user: display name, platforms, follower counts, engagement rate, post URLs, metrics

---

## Post Scheduling — How It Works

When a user approves content, Amplifier schedules posts automatically:

1. Look at user's active campaigns and approved content queue
2. Determine optimal posting times per platform, based on each campaign's target region (e.g., US campaign posts during US peak hours, UK campaign during UK peak hours)
3. Space posts minimum 30 minutes apart
4. Limit campaign posts per day based on user's campaign load and platforms
5. Randomize exact times within windows (avoid posting at exactly :00 every time)
6. Personal brand posts (if user also uses that pipeline) interleave with campaign posts

The user can see the schedule in the Posts tab and adjust if needed.

---

## Profile Scraping — What Gets Extracted

When a user connects a platform, Amplifier scrapes:

| Data | How | Frequency |
|------|-----|-----------|
| Follower/following count | Profile page | On connect + weekly |
| Bio/about text | Profile page | On connect + weekly |
| Display name + profile picture | Profile page | On connect + weekly |
| Recent posts (last 30-60) | Profile/feed page | On connect + weekly |
| Per-post engagement (likes, comments, shares) | Post pages | On connect + weekly |
| Posting frequency | Calculated from post dates | On connect + weekly |
| AI niche classification | From post content + bio | On connect + weekly |

This data is:
- Stored locally in the desktop app
- Sent to server (follower counts, niches, engagement rates) for matching
- Refreshed weekly by the background agent
- User can manually trigger a refresh

---

## Platform Session Health

The background agent checks platform sessions periodically:

| Status | Meaning | Action |
|--------|---------|--------|
| Green | Session valid, posting works | None |
| Yellow | Session expiring soon (e.g., cookies near expiry) | Alert user |
| Red | Session expired, posting will fail | Alert user: "Click to re-authenticate" |

When a post fails due to a session issue:
- User gets an immediate alert
- The post is marked "failed" with a retry button
- Campaigns are NOT blocked — other platforms still post normally
- The failed platform's post retries automatically once the user re-authenticates

---

## Content Quality

All AI-generated content goes through quality scoring before the user sees it:

- Banned phrase detection (AI-sounding language, prohibited claims)
- Platform length limits enforced
- Emotional hook check (first line must trigger engagement)
- Campaign brief adherence (content matches what the company asked for)
- Score 0-100 displayed to user
- Content below 60/100 gets a warning: "This draft may not perform well. Consider editing or regenerating."
- Company brand guidelines (from content_guidance field) checked automatically

---

## Billing & Earnings

### How Users Earn

```
earning = (impressions/1000 * rate_per_1k) + (likes * rate_per_like) + (reposts * rate_per_repost) + (clicks * rate_per_click)
user_gets = earning * 80% (Amplifier keeps 20%)
```

Earnings depend purely on engagement metrics. Operating mode (full_auto/semi_auto/manual) affects the workflow, not the payout.

### Billing Cycle
- Metrics scraped at T+1h, 6h, 24h, 72h
- T+72h metric is marked final
- Final metrics trigger billing calculation
- Earnings credited to user balance
- Campaign budget decremented

### Payout
- Minimum withdrawal: $10
- User requests payout from Earnings tab
- Processed via Stripe Connect (skeleton for now)
- Payout history tracked

---

## What's NOT in This Version (Noted for Later)

- Campaign exclusivity (competing brands)
- Stripe payment integration (real money flow)
- Web dashboard split (separate from desktop app)
- Direct messaging between companies and users
- Content moderation by companies (pre-approval of user content)
- Guaranteed minimum payout per post
- A/B testing for campaigns
- Multi-user company accounts (team members)
- Email verification
- Rate limiting
- CSRF protection
- Redis background jobs (manual admin triggers for now)
- TikTok and Instagram posting (code preserved, disabled)
- Dispute resolution / appeal process improvements
- Auto-update mechanism for desktop app

---

## Theme

- **Primary**: Blue (#2563eb) and white
- **Accent**: Light blue (#3b82f6)
- **Background**: White (#ffffff) with light gray (#f8fafc) sections
- **Text**: Dark gray (#1e293b)
- **Success**: Green (#10b981)
- **Warning**: Amber (#f59e0b)
- **Error**: Red (#ef4444)
- **Font**: DM Sans (same as current)

Applied consistently across all three apps (user, company, admin).

Note: UI/UX polish is low priority. Functional first, pretty later.
