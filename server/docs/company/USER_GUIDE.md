# Amplifier Company Dashboard — User Guide

## Getting Started

### Creating an Account
1. Navigate to `http://<server>/company/login`
2. Click the **Register** tab
3. Enter your company name, email, and password (min 6 characters)
4. You'll be logged in and redirected to the Dashboard

### Logging In
1. Navigate to `http://<server>/company/login`
2. Enter your email and password
3. Click **Sign In**

---

## 1. Dashboard

**URL:** `/company/`

The Dashboard is your home base. It shows everything you need at a glance.

### Metric Cards (Top Row)
Eight cards showing your key numbers:
- **Account Balance** (green) — Available funds for campaigns
- **Active Campaigns** — Currently running campaigns
- **Influencers** — Total creators who've worked on your campaigns
- **Total Posts** — Posts created across all campaigns
- **Total Impressions** — How many people saw your content
- **Total Engagement** (green) — Likes + reposts + comments
- **Total Spent** (yellow) — Budget consumed across all campaigns
- **Cost per 1K Imp.** — Average cost efficiency

### Smart Alerts
Color-coded alerts appear when action is needed:
- **Yellow (Warning):** Low balance — you need funds to create or activate campaigns
- **Blue (Info):** Draft campaigns waiting to be activated
- **Red (Danger):** Active campaigns running low on budget (< 20% remaining)

### Quick Actions
Three buttons for the most common tasks:
- **+ Create Campaign** — Start the AI campaign wizard
- **Add Funds** — Go to billing to top up your balance
- **View Analytics** — See detailed cross-campaign performance

### Recent Campaigns
A table of your 5 most recent campaigns with budget progress bars, impressions, and engagement. Click any row to see the full campaign detail.

---

## 2. Campaigns

**URL:** `/company/campaigns`

### Viewing Campaigns
A paginated list of all your campaigns (15 per page). Each row shows:
- Campaign title (with "Flagged" badge if content screening flagged it)
- Status (draft, active, paused, completed, cancelled)
- Budget remaining / total with a visual progress bar
- Number of influencers and posts
- Impressions and engagement totals

### Searching and Filtering
- **Search:** Type a campaign title and click Search
- **Status filter:** Dropdown to show only campaigns with a specific status
- **Sort:** Order by newest, budget, or title

### Creating a Campaign
Click **+ Create Campaign** in the top right (or sidebar). You need at least $50 in your balance.

---

## 3. Campaign Wizard (Create Campaign)

**URL:** `/company/campaigns/new`

The AI-powered wizard walks you through 4 steps to create a complete campaign.

### Step 1: Product Basics
- **Product name** — Your product or service name
- **Description** — What it is and what problem it solves
- **Features & benefits** — Key selling points
- **Campaign goal** — Choose one:
  - Brand Awareness — Get your name out there
  - Product Launch — Announce something new
  - Event Promotion — Drive attendance
  - Lead Generation — Capture interest
- **Product URLs** — Your website pages (the AI will crawl these to understand your product). Add up to 3 URLs.
- **Product images** — Upload images the AI will reference (JPEG, PNG, WebP, GIF, max 4MB each)
- **Product files** — Upload documents with additional info (PDF, DOCX, TXT, max 4MB, up to 5 files)

### Step 2: Target Audience
- **Categories** — Select relevant niches (finance, tech, lifestyle, gaming, etc.)
- **Regions** — Where your target audience is located (US, UK, EU, Global, etc.)
- **Platforms** — Which social platforms to target (X, LinkedIn, Facebook, Reddit)
- **Minimum followers** — Set minimum follower counts per platform
- **Max creators** — Optional limit on how many influencers can join
- **Min engagement rate** — Optional minimum engagement threshold

### Step 3: Content Direction
- **Must-include phrases** — Type phrases and press Enter to add them as chips
- **Must-avoid phrases** — Topics or words creators should NOT mention
- **Tone guidance** — How the content should feel

Click **Generate with AI** to trigger the campaign brief generation. The AI will:
1. Crawl your product URLs (up to 10 pages per URL)
2. Analyze your product info, images, and documents
3. Generate a complete campaign brief, content guidelines, payout rates, and budget suggestion

### Step 4: Review & Activate
The AI-generated campaign is shown for review. You can edit everything:
- **Title** — The campaign name creators will see
- **Brief** — The main content creators use (500-1000 words)
- **Content guidance** — Tone and style directions
- **Payout rates** — How much you pay per 1K impressions, per like, per repost, per click
- **Budget** — Total campaign budget (min $50). Your balance must cover it.
- **Start/End dates** — Campaign timeline
- **Budget exhaustion action** — What happens when budget runs out:
  - Auto-pause: Campaign pauses, you can top up and resume
  - Auto-complete: Campaign ends permanently

Click **Save as Draft** to save without activating, or **Activate Campaign** to go live immediately (deducts budget from your balance).

---

## 4. Campaign Detail

**URL:** `/company/campaigns/{id}`

### Overview Stats
Seven metric cards at the top: Impressions, Engagement, Spent, Creators, Posts, Cost/1K, Cost/Engagement.

### Budget Progress
A visual bar showing how much budget has been consumed. Colors indicate urgency:
- Green: < 70% consumed
- Yellow: 70-90% consumed
- Red: > 90% consumed

The exhaustion action setting and remaining amount are displayed below the bar.

### Invitation Status
A stacked bar showing how influencer invitations are progressing:
- **Green:** Accepted
- **Yellow:** Pending
- **Red:** Rejected
- **Gray:** Expired

### Platform ROI Breakdown
A table showing performance per platform (X, LinkedIn, Facebook, Reddit). Columns include posts, impressions, engagement, estimated spend, cost/1K, and cost/engagement. This tells you which platforms deliver the best ROI.

### Influencer Roster
Every creator assigned to this campaign, sorted by earnings (highest first). Shows:
- Creator handles and connected platforms
- Assignment status (accepted, posted, paid, etc.)
- Post links (clickable)
- Impressions, likes, engagement
- Estimated earnings (calculated from payout rules)
- Actual amount paid

### Campaign Brief & Config
Two-column layout showing the full brief, content guidance, payout rules, and schedule.

### Actions

**Status Changes:**
- **Activate** (draft → active) — Deducts budget from balance
- **Pause** (active → paused) — Temporarily stops the campaign
- **Resume** (paused → active) — Reactivates a paused campaign
- **Cancel** (any → cancelled) — Ends the campaign and refunds remaining budget

**Edit Campaign:**
Click **Edit Campaign** to open a modal where you can update:
- Title, brief, content guidance
- Payout rates (per 1K, per like, per repost, per click)
- End date
- Budget exhaustion action
Changes increment the campaign version so influencers see the update.

**Top Up Budget:**
Click **Top Up Budget** to add more funds to this campaign from your balance. If the campaign was auto-paused due to budget exhaustion, topping up will automatically reactivate it.

---

## 5. Influencers

**URL:** `/company/influencers`

A cross-campaign view of every creator who has worked on any of your campaigns.

### Summary Stats
Five metric cards: Total Creators, Total Posts, Total Impressions, Total Engagement, Total Paid.

### Creator Table
Each influencer shows:
- **Email** — Creator identifier
- **Platforms** — Which platforms they're connected to (shown as badges)
- **Trust Score** — Platform trust rating (0-100 with visual bar)
- **Campaigns** — How many of your campaigns they've participated in
- **Posts** — Total posts across your campaigns
- **Impressions** — Total impressions generated
- **Engagement** — Total likes + reposts + comments
- **Engagement Rate** — Percentage of impressions that converted to engagement. Color-coded:
  - Green (>= 5%): High performer
  - Yellow (>= 2%): Average
  - Gray (< 2%): Below average
- **Total Paid** — Total amount paid to this creator

### Search
Filter by email to find specific influencers.

---

## 6. Billing

**URL:** `/company/billing`

### Balance Overview
Three stat cards: Current Balance, Total Allocated (across all campaigns), Total Spent.

### Adding Funds
Enter an amount and click **Pay with Stripe**:
- **With Stripe configured:** You'll be redirected to Stripe's secure checkout page. After payment, you'll return to the billing page with your balance updated.
- **Without Stripe (test mode):** The amount is instantly credited to your balance.

### Campaign Budget Allocations
A table showing how your funds are distributed across campaigns:
- Campaign title (linked to detail page)
- Amount allocated
- Amount spent
- Amount remaining
- Campaign status
- Date created

---

## 7. Analytics

**URL:** `/company/stats`

### Overview Stats
Five cards: Total Campaigns, Active Campaigns, Total Spend, Total Reach (impressions), Total Engagement.

### Cost Metrics
Three cards: Average Cost per 1K Impressions, Average Cost per Engagement, Current Balance.

### Best Performers
Two side-by-side cards:
- **Best Campaign** — The campaign with the highest engagement-per-dollar ratio. Shows title (linked), impressions, engagement, spent, and efficiency score.
- **Best Platform** — The platform generating the most engagement across all campaigns.

### Platform Breakdown
Table showing each platform's total engagement and percentage share of total engagement. Sorted by engagement, with visual share bars.

### Monthly Spend
Table showing spend by month with visual distribution bars, giving you a trend of your marketing investment over time.

---

## 8. Settings

**URL:** `/company/settings`

Update your company name and email address. Email changes are validated for uniqueness — if another account uses that email, the update is rejected.

---

## Common Workflows

### First Campaign (Start to Finish)
1. Register at `/company/login`
2. Go to **Billing** → Add $100 (test mode credits instantly)
3. Go to **Create Campaign** → Fill in product info, select audience, set content direction
4. Click **Generate with AI** → Review the brief
5. Click **Activate Campaign** → Budget deducted, campaign goes live
6. Check **Campaign Detail** → Watch as influencers get matched and start posting
7. Monitor **Dashboard** → See impressions and engagement grow

### Topping Up a Running Campaign
1. Go to **Billing** → Add funds if needed
2. Go to **Campaign Detail** → Click **Top Up Budget**
3. Enter amount → The campaign's budget increases, and if it was auto-paused, it resumes

### Understanding Your ROI
1. Go to **Campaign Detail** → Check the Platform ROI table
2. Compare cost/1K and cost/engagement across platforms
3. Go to **Analytics** → See which campaigns and platforms perform best
4. Go to **Influencers** → See which creators deliver the highest engagement rates
5. Use these insights to refine targeting in your next campaign
