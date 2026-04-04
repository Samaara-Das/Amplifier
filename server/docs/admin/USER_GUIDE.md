# Amplifier Admin Dashboard — User Guide

## Getting Started

### Accessing the Dashboard
1. Navigate to `http://<your-server>/admin/login`
2. Enter the admin password (default: `admin`, configurable via `ADMIN_PASSWORD` environment variable)
3. You'll be redirected to the Overview dashboard

### Navigation
The left sidebar contains links to all 10 admin pages. The currently active page is highlighted in blue. Click **Logout** at the bottom to end your session.

---

## 1. Overview Dashboard

**URL:** `/admin/`

The overview is your landing page. It shows the health of the entire platform at a glance.

### Top Stats Row
Seven stat cards showing total users, active users, companies, campaigns (total and active), posts, payouts, and platform revenue. Cards with weekly trend data show "+X this week" below the number.

### Health Indicators
Four color-coded dots tell you what needs attention:
- **Pending Reviews** — Red if > 0. Campaigns flagged by content screening awaiting your review.
- **Pending Payouts** — Yellow if > 0. Payouts waiting to be processed.
- **Low Trust Users** — Red if > 0. Users with trust score below 20 who may be gaming the system.
- **Suspended Users** — Yellow if > 0. Users currently suspended.

### Quick Actions
Three buttons to trigger background processes without leaving the page:
- **Run Billing Cycle** — Processes post metrics into earnings and creates payout records
- **Run Payout Cycle** — Processes pending payouts via Stripe (or instant credit in test mode)
- **Run Trust Check** — Detects metrics anomalies and deletion fraud

### Recent Activity
A table showing the last 15 campaign assignments with user email, campaign title, status, and date. Click any user or campaign to navigate to their detail page.

---

## 2. Users

**URL:** `/admin/users`

### List View
Paginated table of all registered users. Each row is clickable.

**Searching and Filtering:**
- **Search** — Type a partial email and click Search. The search uses substring matching (e.g., "test" finds "test@gmail.com").
- **Status filter** — Dropdown to show only Active, Suspended, or Banned users.
- **Sort** — Sort by Newest First, Trust Score, Total Earned, or Email.

**Table Columns:**
- ID, Email, Trust Score (with visual bar), Mode, Platforms (connected count), Total Earned, Status

### User Detail Page
**URL:** `/admin/users/{id}`

Click any user row to see their full profile.

**Actions available:**
- **Suspend** — Temporarily disable the account. They can't log in or participate in campaigns.
- **Unsuspend** — Restore a suspended account to active.
- **Ban** — Permanently disable the account. Requires confirmation.
- **Adjust Trust Score** — Enter a new score (0-100) and click Update. The old and new scores are logged.

**Tabbed sections:**
- **Assignments** — All campaigns this user was assigned to, with status and date
- **Posts** — All posts with platform, URL, status, and engagement metrics
- **Payouts** — Payout history with amounts and status
- **Penalties** — Any penalties issued, with appeal status

---

## 3. Companies

**URL:** `/admin/companies`

### List View
Paginated table of all registered companies with balance, campaign count, and total spending.

**Searching and Filtering:**
- **Search** — Searches both company name and email
- **Status filter** — Active or Suspended
- **Sort** — Newest First, Balance, or Name

### Company Detail Page
**URL:** `/admin/companies/{id}`

**Fund Management:**
The detail page has two forms for managing the company's balance:
- **Add Funds** — Enter an amount and click "Add Funds." This is for manual adjustments, refunds, or testing (bypasses Stripe).
- **Deduct Funds** — Enter an amount and click "Deduct." Requires confirmation. Balance cannot go below $0.

**Company Actions:**
- **Suspend** — Disables the company and pauses ALL their active campaigns automatically. Use this for policy violations or payment disputes.
- **Unsuspend** — Restores the company to active. Note: paused campaigns are NOT automatically resumed — the company must resume them manually.

**Campaigns Table:**
Shows all campaigns by this company with budget breakdowns and status.

---

## 4. Campaigns

**URL:** `/admin/campaigns`

### List View
Paginated table of all campaigns across all companies.

**Searching and Filtering:**
- **Search** — Search by campaign title
- **Status filter** — Draft, Active, Paused, Completed, Cancelled
- **Sort** — Newest First, Budget, or Title

**Table Features:**
- Budget column shows remaining/total with a visual progress bar
- Flagged campaigns show an extra red "flagged" badge next to their status

### Campaign Detail Page
**URL:** `/admin/campaigns/{id}`

**Campaign Actions:**
- **Pause** — Temporarily stops the campaign. Users can no longer post for it.
- **Resume** — Reactivates a paused campaign.
- **Cancel** — Permanently ends the campaign. Remaining budget is automatically refunded to the company's balance. Requires confirmation.

**Tabbed sections:**
- **Brief** — The full campaign brief and content guidance
- **Users** — All assigned users with their assignment status
- **Posts** — All posts with per-post engagement metrics (impressions, likes, reposts, comments) and links to the live posts
- **Configuration** — Raw payout rules, targeting criteria, penalty rules, and assets (JSON format)

---

## 5. Financial

**URL:** `/admin/financial`

### Stats Row
- **Platform Revenue** — Total budget spent by companies minus total paid to users. This is Amplifier's gross revenue.
- **Total Budget Spent** — How much companies have spent across all campaigns
- **Pending Payouts** — Amount waiting to be paid out
- **Total Paid** — Amount already paid to users
- **Failed Payouts** — Amount from failed payout attempts

### Billing & Payout Controls
- **Run Billing Cycle** — Processes all posts with final metrics. Calculates earnings based on payout rules (rate per 1K impressions, per like, per repost, per click), applies the platform cut, creates Payout records, and updates user balances. A success message shows the number of posts processed and amounts.
- **Run Payout Cycle** — Processes pending payouts. If Stripe is configured, sends real payments. Otherwise, marks them as paid (test mode).

### Transaction Table
Paginated list of all payouts with:
- User email (clickable to user detail)
- Campaign name
- Amount
- Status (pending, processing, paid, failed)
- Expandable breakdown (click "Show details" to see how the amount was calculated)
- Date

**Filter by** status (pending/paid/failed) or search by user email.

---

## 6. Fraud & Trust

**URL:** `/admin/fraud`

### Stats
- **Total Penalties** — Number of penalties issued
- **Total Penalized** — Dollar amount penalized
- **Pending Appeals** — Appeals awaiting your decision
- **Low Trust Users** — Users with trust < 20 who are still active

### Running Trust Checks
Click **Run Trust Check** to execute:
1. **Metrics anomaly detection** — Flags users whose engagement is 3x+ the platform average
2. **Deletion fraud detection** — Flags posts marked as "live" that are older than 24 hours (may have been deleted)

Results appear in two tables (Anomalies and Deletions) above the penalties table.

### Penalty Management
Paginated table of all penalties with:
- Reason (content_removed, off_brief, fake_metrics, platform_violation)
- Amount
- Description

### Processing Appeals
When a user appeals a penalty, buttons appear in the Appeal column:
- **Approve** — Marks the appeal as "upheld" and restores 10 trust points to the user. Requires confirmation.
- **Deny** — Marks the appeal as "denied" with no score change.

Previously processed appeals show their result as a badge (Upheld or Denied).

---

## 7. Analytics

**URL:** `/admin/analytics`

### Platform Breakdown
A table showing per-platform performance:
- Number of posts per platform
- Success rate (% of posts still live vs. deleted/flagged)
- Average impressions and likes per post
- Total impressions and engagement

### Top Performing Posts
A leaderboard of the 10 posts with the highest total engagement (likes + reposts + comments), showing the platform, user, individual metrics, and a link to the live post.

---

## 8. Review Queue

**URL:** `/admin/review-queue`

### Pending Tab
Shows campaigns flagged by the content screening system. Each item displays:
- Campaign title and company name
- Brief preview (first 200 characters)
- Flagged keywords (red badges)
- Screening categories (yellow badges)

**Actions:**
- **Approve** — Marks the campaign as approved. It becomes available for user matching.
- **Reject** — Enter a rejection reason in the text field and click Reject. The campaign is cancelled and its remaining budget is refunded to the company. Requires confirmation.

### Reviewed Tab
History of all previously reviewed campaigns showing the decision (Approved/Rejected) and any notes.

---

## 9. Settings

**URL:** `/admin/settings`

Read-only display of the current system configuration:
- **Platform** — Platform cut % (default 20%), minimum payout threshold ($10), server URL
- **Authentication** — JWT algorithm and token expiry
- **Database** — Connection string (masked), debug mode status
- **Integrations** — Stripe and Supabase Storage status (Configured or Not configured)

Settings are controlled by environment variables. To change them, update the `.env` file or Vercel environment variables and restart the server.

---

## 10. Audit Log

**URL:** `/admin/audit-log`

### Viewing the Log
A paginated table of every admin action ever taken, newest first.

**Columns:**
- **Time** — When the action occurred
- **Action** — The action identifier (e.g., `user_suspended`, `company_funds_added`)
- **Target** — The type and ID of the affected entity. IDs are clickable links to the entity's detail page.
- **Details** — Context data (email, amounts, scores, reasons)
- **IP** — The admin's IP address at the time of the action

### Filtering
- **Action dropdown** — Filter by specific action type (dynamically populated with all action types that exist in the log)
- **Target Type dropdown** — Filter by entity type (user, company, campaign, penalty, system)
- **Clear Filters** — Reset all filters

### What Gets Logged
Every action that changes data:
- User: suspend, unsuspend, ban, trust score adjustment
- Company: add funds, deduct funds, suspend, unsuspend
- Campaign: pause, resume, cancel
- Review: approve, reject
- Appeals: approve, deny
- System: billing cycle, payout cycle, trust check

---

## Common Workflows

### Adding Funds to a Company (for Testing)
1. Go to **Companies** → Click the company row
2. In the **Manage Funds** section, enter an amount
3. Click **Add Funds**
4. The balance updates immediately. The action is logged in the audit trail.

### Investigating a Suspicious User
1. Go to **Users** → Search by email or filter by status
2. Click the user row to see their detail page
3. Check the **Penalties** tab for past issues
4. Check the **Posts** tab for suspicious engagement patterns
5. Adjust trust score or suspend/ban as needed

### Processing the Weekly Billing
1. Go to **Financial**
2. Click **Run Billing Cycle** — This processes all final metrics into payout records
3. Review the resulting message for the number of posts processed
4. Click **Run Payout Cycle** — This processes pending payouts
5. Both actions are logged in the audit trail

### Reviewing Flagged Content
1. Go to **Review Queue** — The pending count shows in the nav
2. Review each flagged campaign's brief and flagged keywords
3. Click **View Campaign** to see the full details
4. Click **Approve** or enter a rejection reason and click **Reject**
