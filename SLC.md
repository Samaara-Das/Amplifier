# Amplifier — SLC Spec v1

**Date**: 2026-03-25
**Status**: Draft — awaiting approval

---

## What Amplifier Is

Amplifier is a two-sided marketplace where **companies pay people to post about their products on social media**. Companies create campaigns with budgets. Amplifier's AI matches campaigns to the right users. Users accept campaigns, AI generates tailored content, and Amplifier posts it to their social accounts automatically. Users earn money based on real engagement metrics.

---

## SLC Framework

### Simple
- **Company**: Fill out one form about your product → AI generates your entire campaign → set budget → go live. Under 5 minutes.
- **User**: Install → log in → connect social accounts → accept campaigns → money appears. The app runs in the background and handles everything.
- **No jargon**. No dashboards full of charts nobody reads. Every screen has one clear purpose.

### Lovable
- **Company**: You see exactly which creators are posting for you, what they posted, how it performed, and what you're paying. Real metrics, not vanity numbers. Campaign creation feels like talking to a strategist, not filling out a form.
- **User**: You literally earn money while your computer runs. Content is generated for you, posted for you, metrics are tracked for you. You just review and approve (or let it auto-post). Desktop notifications tell you when there's money to collect.
- **The AI content is genuinely good** — researched, platform-native, UGC-style. Not generic slop.

### Complete
- **Company can go from signup to live campaign with real users posting in under 10 minutes.**
- **User can go from install to first earned dollar with zero manual posting.**
- **No dead ends.** Every screen leads somewhere. Every action has feedback. Every error has a recovery path.

---

## Two Sides, Two Apps

### Server (company + admin dashboards)
- **Tech**: FastAPI + Jinja2 + Supabase PostgreSQL
- **Deployed**: Vercel
- **Who uses it**: Companies (web browser), Admins (web browser)

### User App (desktop)
- **Tech**: Flask (localhost:5222) + local SQLite + Playwright + pystray system tray
- **Runs on**: User's Windows desktop
- **Who uses it**: Users who want to earn money posting

---

## Company Journey

### 1. Register / Login
- Email + password
- Lands on campaign list (empty state with "Create your first campaign" CTA)

### 2. Create Campaign (AI-assisted)
Company fills ONE form with these fields:

| Field | Required | Notes |
|-------|----------|-------|
| Product name | Yes | |
| What is your product? | Yes | Free text description |
| Product features & benefits | Yes | What makes it worth posting about |
| Public links | Yes | Must be publicly accessible. Displayed note: "Enter public URLs so we can learn about your product. The more context, the better." |
| Product images | No | Upload images of the product. These are given to users for their posts. |
| Campaign goal | Yes | Dropdown: brand awareness, leads/signups, sales/conversions, app installs |
| Must-include phrases | No | Words/phrases that MUST appear in posts |
| Must-avoid phrases | No | Words/phrases that must NOT appear |
| Budget | Yes | Minimum $50. Deducted from balance on activation. |
| Payout rates | Yes | Per 1K impressions, per like, per repost, per click. AI suggests defaults. |
| Required platforms | No | Which platforms users must have connected |
| Min followers | No | Per platform minimums |
| Min engagement rate | No | Minimum average engagement rate (%) |
| Max users | Yes | Maximum number of users who can accept this campaign |
| Start date / End date | Yes | |
| Budget exhaustion action | Yes | Auto-pause or auto-complete |

**What happens on submit:**
1. Amplifier scrapes all provided public links using the webcrawler — extracts product info, features, pricing, images, descriptions. Stores everything with the campaign.
2. AI (Gemini) generates: campaign title, detailed brief, content guidance for creators, suggested payout rates, and a reach estimate based on the targeting criteria.
3. Company reviews the AI-generated campaign, edits anything, saves as draft or activates.
4. On activation: budget deducted from company balance, campaign status → active, matching begins.

**What the scraped data is used for:**
The scraped product info + uploaded images + campaign brief are ALL passed to the content generation AI when users create posts. This is why thorough scraping matters — user post quality depends directly on how much the AI knows about the product.

### 3. Campaign Goes Live → Matching
- Server-side AI matching runs when users poll for campaigns (see User Journey)
- Matching respects `max_users` — stops sending invitations once `accepted_count >= max_users`
- Company sees invitation stats on campaign detail page

### 4. Monitor Campaign
Campaign detail page shows:
- **Stats cards**: posts, unique creators, impressions, engagement, budget spent/remaining, cost per 1K impressions, cost per engagement
- **Per-platform breakdown**: posts, impressions, likes, reposts, comments, spend, CPM, CPE per platform
- **Creator table**: each user who accepted — their posts (with URLs), metrics, estimated earnings, actual paid. Sorted by performance.
- **Invitation funnel**: sent → accepted → rejected → expired → pending
- **Budget management**: top-up, 80% alert, exhaustion handling

### 5. Billing
- Stripe test mode integration
- Companies add funds via Stripe checkout (test cards)
- Balance tracked on company record
- Budget deducted on campaign activation, refunded on draft deletion

### 6. Campaign List
- All campaigns with status, budget, performance summary
- Filter by status (draft, active, paused, completed)

---

## User Journey

### 1. Register / Login
- Email + password (Google auth: later, not v1)
- JWT saved locally

### 2. Onboarding (4 steps)

**Step 1 — Connect Platforms**
- 4 platform cards: X, LinkedIn, Facebook, Reddit
- Click "Connect" → Playwright browser opens with persistent profile → user logs in manually → closes browser
- **On browser close, Amplifier auto-scrapes the profile.** Scraper extracts everything available per platform:

| Field | X | LinkedIn | Facebook | Reddit |
|-------|---|----------|----------|--------|
| Display name | Yes | Yes | Yes | Yes |
| Bio/headline | Yes | Yes | Yes | Yes |
| Follower count | Yes | Yes (connections) | Yes (friends) | Yes |
| Following count | Yes | Yes | Yes | No |
| Profile picture URL | Yes | Yes | Yes | Yes |
| Recent posts (up to 20) | Yes | Yes | Yes | Yes |
| Post engagement (likes, comments, reposts per post) | Yes | Yes | Yes | Yes (score, comments) |
| Average engagement rate | Calculated | Calculated | Calculated | Calculated |
| Posting frequency | Calculated | Calculated | Calculated | Calculated |
| Account age / join date | If available | If available | If available | Yes (cake day) |
| Location (from profile) | If available | If available | If available | No |
| Niche/topics (from bio + posts) | AI-detected | AI-detected | AI-detected | AI-detected |

- All scraped data stored locally AND synced to server (server needs it for matching)
- Scraping status shown in real-time (polling every 3s)

**Step 2 — Choose Niches**
- 20 niche checkboxes. **None pre-selected.** User manually picks the niches they want to post for.
- AI-detected niches shown as suggestions (e.g., "Based on your profile, you might be interested in: finance, tech") but NOT auto-checked.
- No audience region dropdown. **Amplifier auto-detects the user's region** from their IP/system locale and sets it automatically. Shown as read-only text: "Your detected region: US"

**Step 3 — Operating Mode**
- **Semi-auto** (default): AI generates content daily. User reviews, edits, approves before posting. Desktop notification sent when drafts are ready.
- **Full-auto**: AI generates and posts automatically. No review step. Desktop notification sent when posts go live.

**Step 4 — API Keys**
- User is guided to create 2-3 free API keys (Gemini, Mistral, Groq) with step-by-step instructions and direct links.
- Each key has a "Paste your key here" field + a "Test" button that verifies the key works.
- **At least 1 working key is required** to proceed. More keys = better reliability (fallback chain).
- Keys stored locally in the user's config. Amplifier never sends them to the server.

**Step 5 — Summary + Done**
- Shows: connected platforms, selected niches, detected region, mode, API keys status
- "Start Amplifier" button → saves everything, syncs to server, starts background agent

### 3. Campaign Discovery
- Background agent polls server every 10 minutes
- Server runs AI matching (see Matching section below)
- **User is limited to 3 active campaigns.** No new invitations are sent if user already has 3 active. This limit is shown on the campaigns page: "You can have up to 3 active campaigns."
- Campaign invitations show: title, brief, detailed campaign description (the full AI-generated brief + content guidance), payout rules (rates per metric), required platforms, campaign duration

### 4. Content Generation (AI Agent)
When a user accepts a campaign, the content generation agent runs:

**Phase 1 — Research**
- Loads campaign data: brief, content guidance, scraped product info (from company's links), product images, must-include/avoid
- Browses the web using webcrawler: searches for the product, competitor content, trending posts in the niche, relevant hashtags
- Builds a research brief: what the product is, what angle works, what's trending, what competitors say

**Phase 2 — Content Strategy**
AI agent decides:
- **Post type** per platform: text-only, image+text, or carousel (based on what performs best on each platform)
- **Posting frequency**: how many posts per day per platform (based on campaign duration, budget, and platform norms)
- **Tone and angle**: derived from campaign brief + research (NOT hardcoded)
- **Scheduling**: posts timed for when the campaign's target audience is online (based on target region → timezone → platform peak hours)

**Phase 3 — Content Creation**
For each scheduled post:
- Generates platform-native content (different format/length/style per platform)
- Content style: **UGC (user-generated content)** — should feel like a real person recommending a product, not an ad
- Goals: be viral, get leads/attention for the company, feel authentic
- Uses product images from campaign when appropriate
- Includes must-include phrases, avoids must-avoid phrases
- Each day's content is unique (AI receives previous posts to avoid repetition)

**Phase 4 — Review or Auto-post**
- **Semi-auto**: drafts saved, desktop notification sent "You have N drafts to review", user approves/edits/rejects on the campaign detail page
- **Full-auto**: drafts auto-approved and scheduled immediately

**Content prompt is GENERIC** — no personal branding, no trading references, no audience-specific assumptions. The prompt adapts to whatever the campaign is about.

**AI fallback chain**: User's Gemini key → User's Mistral key → User's Groq key. If all fail, content generation is skipped for this cycle and retried next cycle.

### 5. Posting
- Background agent checks for due posts every 60 seconds
- Opens Playwright with the platform's persistent browser profile
- Posts content (platform-specific: X dispatch_event click, LinkedIn shadow DOM, etc.)
- Captures post URL by navigating to own profile
- Syncs post to server (registers post URL + content hash)
- **Desktop notification**: "Posted to X for [Campaign Name]"

### 6. Metric Scraping
- Scraping schedule: T+1h, T+6h, T+24h, T+72h, then every 24h while campaign is active
- Per-platform scraping extracts: impressions/views, likes, reposts/shares, comments, saves (if available)
- Clicks hardcoded to 0 (not available via browser scraping — noted for later API migration)
- Metrics synced to server on every scrape
- Server triggers billing on every metric submission

### 7. Earnings
- Earnings page shows: total earned, available balance, pending (estimated from unbilled metrics)
- Per-campaign breakdown: campaign name, total posts, total earned
- Per-platform breakdown
- Payout history
- Withdrawal: $10 minimum → creates payout record (Stripe payout is a stub for now — test mode on company side only)

### 8. Desktop Experience
- **System tray icon** (pystray): "Amplifier" with status indicator
- Right-click menu: "Open Dashboard" (opens browser to localhost:5222), "Pause Agent", "Resume Agent", "Quit"
- **App must be running for posts and scraping to happen.** User sees a clear message: "Keep Amplifier running in the background for your campaigns to work."
- Desktop notifications via Windows toast (win10toast or plyer):
  - "You have N drafts to review" (semi-auto)
  - "Posted to [platform] for [campaign]" (after successful post)
  - "Post failed on [platform]" (on failure)
  - "New campaign invitation: [title]"

### 9. Dashboard
- Active campaigns count
- Pending invitations count
- Posts this month (actual month filter, not all-time)
- Total earned
- Platform health (connected/disconnected per platform)

### 10. Settings
- Connected platforms with Connect/Reconnect
- Operating mode toggle
- Niche tags (editable)
- API keys (editable, with test buttons)
- Detected region (read-only)
- Logout

---

## AI Matching (Server-Side)

Runs when a user polls for campaigns. Pipeline:

### Hard Filters (pass/fail)
1. Campaign is active and has budget remaining
2. User not already invited to this campaign
3. `accepted_count < max_users` for the campaign
4. User has at least 1 of the required platforms connected
5. User meets min follower counts per platform
6. User meets min engagement rate
7. User's region matches campaign's target regions (or campaign targets "global")
8. User has fewer than 3 active campaigns

### AI Scoring (fully AI-driven)
- Gemini reads the user's full scraped profile data: bio, posts with engagement metrics, followers, following, about section, work experience, personal details — across all connected platforms
- AI judges fit based on topic relevance, audience fit, and authenticity
- AI is told most users are normal people (not influencers) — low follower counts and infrequent posting are normal and should not be penalized
- Returns relevance score 0-100
- Cached 24 hours per (campaign, user) pair
- Fallback to niche-tag overlap if AI fails

### Selection
- Sort by AI score descending
- Invite up to `max_users - accepted_count` users
- Create `CampaignAssignment` with status `pending_invitation` (expires in 3 days)

---

## Billing

### How Earnings Are Calculated
```
raw_earning = (impressions/1000 * rate_per_1k_impressions)
            + (likes * rate_per_like)
            + (reposts * rate_per_repost)
            + (clicks * rate_per_click)

user_earning = raw_earning * 0.80   (Amplifier takes 20%)
```

### When Billing Runs
- Triggered on every metric submission (not batched, not cron)
- Incremental: tracks billed metric IDs to prevent double-billing
- Caps earnings to remaining campaign budget
- Auto-pauses or auto-completes campaign when budget exhausted (<$1 remaining)

### Money Flow
```
Company adds funds (Stripe test mode) → company.balance
Company activates campaign → balance deducted → campaign.budget_remaining
User posts + metrics scraped → billing calculates earnings
Earnings credited to user.earnings_balance
User requests withdrawal ($10 min) → payout record created
```
*Note: Actual money transfer to users is a stub. Stripe Connect for user payouts is post-v1.*

---

## What's NOT in v1 (Backlog)

These are explicitly deferred. Do not build them.

- Google auth for users
- Content screening (AI-based campaign content moderation)
- Official platform APIs for posting (replace Playwright)
- Official platform APIs for metric collection
- TikTok and Instagram support
- Stripe Connect for user payouts (real money transfer)
- Auto-start on Windows login
- Mobile app
- User-facing analytics dashboard (beyond basic earnings)
- Campaign A/B testing
- Referral system
- Multi-language support
- Rate limiting / abuse prevention (beyond trust score)
- Email notifications
- Webhook integrations for companies
- Public API for companies

---

## Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Server framework | FastAPI + Jinja2 | Already built, deployed, working |
| Server database | Supabase PostgreSQL | Already deployed, free tier |
| User app UI | Flask on localhost | Direct Python calls, no bridge layers, ships fast |
| User app database | Local SQLite | Offline-capable, zero config |
| Browser automation | Playwright | Already working for 4 platforms |
| AI providers | Gemini → Mistral → Groq (user's own keys) | Free tier, fallback chain |
| Content research | webcrawler CLI | Already installed, works well |
| Desktop presence | pystray system tray | Lightweight, pure Python, no Electron/Tauri bloat |
| Desktop notifications | win10toast / plyer | Native Windows toasts |
| Payments | Stripe test mode | Demo-ready, 30 min setup |
| Deployment (server) | Vercel | Already deployed |
| Distribution (user app) | PyInstaller single exe + system tray | Simplest path to "double-click to run" |

---

## Build Order (Vertical Slices)

### Slice 1: Company Flow
Clean up dead code → fix campaign creation wizard → scraping → matching with max_users → campaign detail with verified stats

### Slice 2: User Flow
Onboarding (enhanced scraping, manual niches, auto-region, API key setup) → campaign invitations → content generation agent (research + strategy + creation) → posting pipeline → desktop tray + notifications

### Slice 3: Money Flow
Metric scraping (verified) → billing (verified) → earnings display → Stripe test mode for companies → withdrawal

### Slice 4: Polish
UI improvements → edge cases → error handling → "Posts This Month" fix → 3-campaign limit UX → full-auto verification
