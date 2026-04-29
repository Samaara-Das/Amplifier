# Batch 4: Business & Launch Specifications

**Tasks:** #19 (Stripe live integration), #22 (landing page), #6 (metrics accuracy). Task #17 (Free/Pro tiers) deferred — see stub below.

---

## Task #17 — [DEFERRED] Free/Pro Tiers

**Status: Deferred to post-launch (2026-04-29).** Full spec preserved in the task-master task description (task #17). Reasoning: amplifiers with no earnings track record cannot rationally evaluate a $19.99/mo subscription; Pro converts post-traction users, which MVP hasn't produced yet. The 20% platform cut is sufficient monetization for MVP. The Free 4 posts/day cap is removed alongside Pro — it only made sense as upgrade friction. Reputation tier (seedling/grower/amplifier) still governs campaign count and earnings multiplier; no per-day post cap from a subscription axis remains. Revisit triggers: amplifier cohort earning $300+/month consistently, OR campaign-supply scarcity making match-priority valuable, OR feature demand that genuinely costs money to deliver.

---

## Task #19 — Stripe Live Integration (Company Checkout + User Connect)

### Overview

Stripe must work in both directions for real money to flow:
- **Companies pay IN** via Stripe Checkout (top up campaign budget)
- **Users get paid OUT** via Stripe Connect Express (receive earnings)

Currently: company Checkout exists in test mode. User payouts are a stub (always marks "paid" without sending money).

**Existing Stripe account:** Father's company has a live, working Stripe account that will be used for Amplifier. No need to create a new Stripe account.

### Company Side: Checkout (already built, needs live keys)

1. Company clicks "Add Funds" on the billing page
2. Enters amount (minimum $50)
3. Server creates a Stripe Checkout session
4. Company completes payment with real card
5. **Webhook** (`checkout.session.completed`) fires → server credits company balance
6. Company can now activate campaigns with that balance

**What needs to change for live:**
- Set real Stripe keys on the server (production environment)
- Use webhook for payment confirmation instead of redirect-based verification (more reliable)
- Add idempotency check: if the same Checkout session is verified twice, don't double-credit the balance

### User Side: Connect Express (not built yet)

Users need to onboard with Stripe Connect to receive real payouts.

**Onboarding flow:**
1. User navigates to Settings → "Connect Bank Account" (or Earnings page → "Set up payouts")
2. Server creates a Stripe Connect Express account for the user
3. User is redirected to Stripe's hosted onboarding form (collects bank details, identity, tax info)
4. After completing onboarding, user is redirected back to the app
5. Server stores the user's Stripe account ID
6. User can now receive payouts

**Payout flow (automated):**
1. User has available earnings >= $10.00 (past the 7-day hold)
2. User clicks "Withdraw" on the Earnings page OR payouts run on a schedule
3. Server creates a Stripe Transfer from Amplifier's account to the user's Connect account
4. Payout status: available → processing → paid (or failed)
5. User sees the payout in their bank account (typically 2-3 business days)

**What happens without Stripe Connect:**
- User can still earn and see their balance
- Withdrawal button shows "Connect your bank account first"
- Earnings accumulate until the user completes Stripe onboarding

### Webhook Endpoints

The server needs a webhook endpoint that handles events from both Checkout and Connect:

| Event | Action |
|-------|--------|
| checkout.session.completed | Credit company balance (with idempotency check) |
| transfer.paid | Confirm user payout successful |
| transfer.failed | Mark payout as failed, return funds to user's available balance |
| account.updated | Track user's Stripe account verification status |

### Edge Cases

- Company clicks success page twice → balance only credited once (idempotency)
- User completes Stripe onboarding but bank details are invalid → transfer fails, funds return to available balance
- User requests withdrawal of $15 but only $12 is available → reject with "Insufficient available balance"
- User has no Stripe account → can't withdraw, earnings accumulate safely
- Stripe is down → payouts fail gracefully, retry on next cycle

### Acceptance Criteria

1. Company tops up $100 using a real card. Balance increases by $100 after webhook fires. Balance does NOT increase if page is refreshed (idempotency).
2. User completes Stripe Connect onboarding. Their Stripe account ID is stored. "Connect your bank account" changes to "Connected."
3. User with $15 available balance clicks "Withdraw $15". Stripe Transfer is created. Payout status moves to "paid" after processing. User's available balance decrements.
4. User without Stripe Connect tries to withdraw. Error message: "Connect your bank account first."
5. Transfer fails (bad bank details). Payout status = "failed". Funds return to user's available balance.

---

## Task #22 — Landing Page

### Overview

A public-facing website that explains Amplifier to both companies and users. Must convert visitors into signups (companies) and downloads (users).

### Two Audiences, One Page

| Section | For Companies | For Users |
|---------|-------------|-----------|
| Hero | "Get real people to post about your product" | "Earn money posting about products you love" |
| How it works | Create campaign → Set budget → Track results | Sign up → Get matched → Post & earn |
| Pricing | Pay per engagement (impressions, likes, reposts) | Free to join, earn per post |
| CTA | "Create Campaign" → links to company dashboard | "Download Amplifier" → links to installer download |

### Page Sections (top to bottom)

1. **Hero** — Split message for both audiences. Bold headline, short subtitle, two CTA buttons (Company / User)
2. **How it works** — 3-step visual flow for each audience
3. **For Companies** — Why use Amplifier: real people (not bots), pay only for results, AI-matched creators, campaign analytics
4. **For Users** — Why join: earn money from social media you already use, AI generates content for you, get matched to brands you care about, cash out anytime
5. **Pricing** — Companies: pay per engagement (show the rate types). Users: free, earn from day one
6. **Trust/Social Proof** — Platform stats (campaigns created, posts made, earnings paid). Placeholder for testimonials.
7. **FAQ** — Common questions: "How much can I earn?", "What platforms are supported?", "How does payment work?", "Is it free?"
8. **Footer** — Links to Terms, Privacy Policy, company dashboard, support email

### Technical Requirements

- Static site (no server rendering needed). Can be HTML + CSS or a simple framework (Next.js, Astro).
- Deployed to Vercel (same platform as the server)
- Loads in under 2 seconds
- Mobile responsive
- SEO: title tag, meta description, Open Graph tags for social sharing
- Download link for Windows installer (and Mac when ready)

### Acceptance Criteria

1. Navigate to the landing page URL. Page loads in under 2 seconds. Both company and user messaging is visible.
2. Click "Create Campaign". Redirects to company login/register page.
3. Click "Download Amplifier". Installer download starts.
4. Share the URL on LinkedIn/Facebook/Reddit. Preview card appears with title, description, and image (OG tags working).
5. View on mobile (375px width). All content is readable, CTAs are tappable, no horizontal scroll.
6. FAQ section answers the 4 key questions.

---

## Task #6 — Metrics Accuracy

### Overview

Metrics drive billing. Inaccurate metrics mean inaccurate payouts — users lose trust if underpaid, companies lose money if overpaid. This task adds validation and handles edge cases in the metric scraping pipeline.

### Deleted Post Detection

When the scraper visits a post URL and the post has been deleted, it must detect this and stop scraping. Without detection, deleted posts produce zero-metric rows that look like engagement dropped to zero — which is different from "this post no longer exists."

**Per-platform deletion signals:**

| Platform | Signs the post was deleted (verified against real deleted posts) |
|----------|--------------------------|
| X | "This post is unavailable", "This account doesn't exist", "This post was deleted", "Hmm...this page doesn't exist" (unicode-normalized), "Account suspended", "Page not found", HTTP 404 via API |
| LinkedIn | "This content isn't available", "This page doesn't exist", "This post has been removed", "This post cannot be displayed", "Content unavailable" |
| Facebook | "This content isn't available", "This page isn't available", "The link you followed may be broken", "Content not found", "This post is no longer available", "Content isn't available right now". Also detects author-deleted posts via permalink: if permalink URL loads but shows "No more posts" (empty feed), the post is gone. |
| Reddit | "Sorry, this post was removed", "Sorry, this post was deleted", "This post was removed by", "This post was deleted by", "This post has been removed", "This post is no longer available", "Page not found". Also checks `shreddit-post[removed="true"]` attribute for mod removals AND `shreddit-post[author="[deleted]"]` / `is-author-deleted` attribute for user-deleted posts. Note: `[deleted]`/`[removed]` in body text NOT used (causes false positives from deleted comments). |

**When a deleted post is detected:**
1. Mark the post as "deleted" in the local database
2. Do NOT record a zero-metric row (zeros would look like real engagement data)
3. Stop all future scraping for this post
4. Notify the server via `PATCH /api/posts/{id}/status` with `{"status": "deleted"}` — the server calls `void_earnings_for_post()` which voids pending payouts and returns funds to the campaign budget

### Rate Limit Handling

Platforms may block repeated automated visits with CAPTCHAs, login walls, or rate limit pages.

**When rate limiting is detected:**
1. Skip the current scrape (do NOT record zero metrics)
2. Track consecutive rate limits per platform
3. After 3 consecutive rate limits on a platform, pause all scraping for that platform for 1 hour
4. Resume automatically after the cooldown

### Duplicate Prevention

The same metric values should not be billed twice. The billing system must check if a metric has already been processed before creating a new earning record.

### Edge Cases

- Post gets 0 likes and 0 comments (brand new post) → store zeros, this IS valid data (different from deletion)
- Reddit score goes negative → store as-is, negative scores are valid
- Scraper finds engagement numbers but the page is still loading → wait for page to fully load before extracting
- Platform changes their UI → metric extraction returns all zeros. This should trigger a warning, not silent billing of $0.

### Acceptance Criteria

1. Delete a post on X. Run the scraper. The post is marked as "deleted" in the database. No zero-metric row is stored. Future scraping skips this post. _(N/A while X disabled; test equivalent on LinkedIn/Facebook/Reddit)_
2. A post with 0 likes and 0 comments (real post, just no engagement). Scraper stores the zeros correctly. This is valid data.
3. Platform rate limits the scraper 3 times in a row. Scraping for that platform pauses for 1 hour. Other platforms continue normally.
4. Same metric data submitted to the server twice. Only one earning record is created (no duplicates).
5. Server is notified about a deleted post. Pending earnings for that post are voided. Funds return to the campaign budget.
