# Amplifier — Concept Document

## The One-Line Version

Amplifier is a marketplace where companies pay everyday people to post about their products on social media — and AI handles everything from content creation to posting to payment.

---

## The Problem

### Companies Can't Afford Social Media Marketing

Social media marketing is broken for most companies.

Hiring an influencer costs $500-$50,000 per post. Running ads means competing in auctions against companies with 100x your budget. Going "organic" means shouting into the void and hoping someone listens.

The result: small and mid-size companies — the ones who actually need social media marketing — can't afford it. The companies that can afford it are fighting over the same small pool of influencers, driving prices higher every year.

And here's the kicker: when you do pay for an influencer post, you're paying upfront with no performance guarantee. You send $2,000 to someone with 50K followers, they post a story that disappears in 24 hours, and you have no idea if it moved the needle.

### People Can't Monetize Their Social Media

On the other side, billions of people spend hours every day on social media and earn nothing from it.

Platform monetization has impossibly high bars. YouTube requires 1,000 subscribers and 4,000 watch hours. TikTok's Creator Fund needs 10,000 followers. Instagram's bonuses are invite-only. For the vast majority of people — the ones with 200 followers on X, 500 connections on LinkedIn, 300 friends on Facebook — there's simply no way to earn money from the time they spend online.

Affiliate marketing exists, but it's saturated and obvious. Every post looks like an ad. People tune it out.

### The Gap Nobody's Filling

There are roughly 5 billion social media users worldwide. Fewer than 1% are "creators" or "influencers." The other 99% — normal people with real social networks — represent a massive, untapped distribution channel.

If you could coordinate thousands of normal people to post authentic content about products they'd actually use, you'd unlock:

- **Massive reach at low cost.** 1,000 people with 500 followers each = 500,000 potential impressions.
- **Authentic distribution.** Real people posting on their real profiles to people who actually know them. No "ad" label. No algorithm penalty.
- **Performance alignment.** Pay only for engagement that actually happens — not for the privilege of being posted about.

That's what Amplifier does.

---

## How Amplifier Works

### For Companies

1. **Create a campaign.** Describe your product, paste your website URL. Amplifier's AI scrapes your site and generates a complete campaign brief — what to say, how to say it, who should say it.

2. **Set your budget and rates.** Decide how much you'll pay per 1,000 impressions, per like, per share, per click. Set a total budget. Amplifier suggests rates based on your niche.

3. **Go live.** That's it. AI automatically matches your campaign to relevant users based on their social media profiles, niches, audience, and posting history. Users start posting within 24 hours. You pay only for real engagement.

4. **Track everything.** See exactly which users are posting, what they posted, how each post performed, and what you're paying. Export reports. Adjust budget. Pause or resume anytime.

**Time from signup to live campaign: under 10 minutes.**

### For Users (Amplifiers)

1. **Install the app.** Desktop app for Windows. Connect your social media accounts (X, LinkedIn, Facebook, Reddit). The app never sees your passwords — it uses persistent browser sessions.

2. **Accept campaigns.** AI matches you with campaigns that fit your niche and audience. You see the campaign brief, payout rates, and what's expected. Accept up to 3 campaigns at a time.

3. **Review or auto-post.** AI generates platform-native content for each of your connected platforms. In semi-auto mode, you review and approve. In full-auto mode, it posts automatically.

4. **Earn money.** The app tracks your posts' engagement (impressions, likes, shares) and reports it to the server. Earnings appear in your dashboard. Cash out when you hit $10.

**Time from install to first earning: same day.**

---

## What Makes Amplifier Different

### vs. Influencer Marketing Agencies

| | Influencer Agencies | Amplifier |
|---|---|---|
| **Cost** | $500-$50K per post | Pay per engagement (often $5-$50 per user per campaign) |
| **Payment model** | Pay upfront, hope for results | Pay only for real engagement |
| **Reach** | Concentrated in few influencers | Distributed across thousands of normal people |
| **Content** | Created by influencer (variable) | AI-generated, platform-native, brand-guided |
| **Setup time** | Weeks of negotiation | Minutes |
| **Tracking** | Manual, screenshots | Automated metric scraping + billing |

### vs. Affiliate Marketing (ShareASale, Impact, etc.)

Affiliate networks pay for conversions (clicks, signups, purchases). Amplifier pays for engagement (impressions, likes, shares). This matters because:

- Affiliate links are obvious and people avoid them
- Affiliate requires the user to manually craft promotional content
- Amplifier content looks like normal social media posts because it is — AI generates authentic UGC, not ads

### vs. Social Media Management Tools (Hootsuite, Buffer, etc.)

These tools help you manage your own accounts. Amplifier manages other people posting about you. Completely different value proposition — Amplifier is a distribution channel, not a scheduling tool.

### vs. UGC Platforms (Billo, JoinBrands, etc.)

UGC platforms connect brands with creators who make content. But the brand still has to distribute that content themselves. Amplifier generates AND distributes — content is posted directly to users' real social accounts, reaching their real audiences.

---

## The Business Model

### Revenue

Amplifier takes a **20% cut** of all earnings.

When a company pays $1.00 for engagement on a user's post:
- **$0.80** goes to the user
- **$0.20** goes to Amplifier

That's it. No subscription fees. No setup costs. Pure marketplace economics.

### Unit Economics (Projected)

| Metric | Value |
|---|---|
| Average campaign budget | $200-$500 |
| Average payout per user per campaign | $5-$50 |
| Amplifier revenue per campaign | $40-$100 (20% of budget) |
| Cost to serve (AI API calls, hosting) | ~$2-5 per campaign |
| Gross margin | ~90%+ |

The economics work because:
- AI content generation uses free-tier APIs (Gemini, Mistral, Groq)
- Hosting is on Vercel's free/hobby tier
- Database is Supabase's free tier
- All compute-heavy work (Playwright, AI generation) runs on users' devices

### How Money Flows

```
Company deposits funds (Stripe) → Company balance
Company activates campaign → Budget locked from balance
Users post + get engagement → Billing calculates earnings
    → 80% credited to user's balance
    → 20% retained by Amplifier
    → Deducted from campaign budget
User cashes out ($10 minimum) → Stripe Connect payout
```

---

## Market Opportunity

### The Social Media Marketing Market

- Global social media advertising market: **$230+ billion** (2025)
- Influencer marketing market: **$21+ billion** (2025), growing 30%+ annually
- Creator economy: **$100+ billion** (2025)

### Amplifier's Addressable Market

**TAM (Total Addressable Market):** $21B — the global influencer marketing spend. Amplifier is a direct alternative to influencer marketing for the "long tail" of companies and creators.

**SAM (Serviceable Addressable Market):** $5B — small-to-mid companies in the US spending $500-$50K annually on social media marketing. These companies can't afford traditional influencer deals but need social proof and organic-looking distribution.

**SOM (Serviceable Obtainable Market):** $50M — 1% of SAM within 3 years. 10,000 companies spending an average of $5,000/year on Amplifier campaigns. At 20% take rate = $10M annual revenue.

### Why Now

1. **AI is finally good enough.** Gemini, GPT-4, Claude can generate genuinely good, platform-native social media content. This wasn't possible 2 years ago.
2. **Social media is saturated.** Organic reach is dying. Companies need new distribution channels.
3. **The gig economy is mainstream.** People are used to earning money from apps (Uber, DoorDash, Fiverr). Earning from social media posts is a natural extension.
4. **Platform APIs are accessible.** Browser automation + APIs make it possible to automate posting and metric collection across platforms.

---

## What's Built

Amplifier is not a pitch deck. It's a working product.

### Shipped (V1)

- **Server** — 52+ API endpoints, deployed on Vercel with Supabase PostgreSQL
- **Company Dashboard** — 6 pages: login, campaign list, AI campaign wizard, campaign detail with analytics, billing, settings
- **Admin Dashboard** — 6 pages: overview, user management, campaign management, fraud detection, payouts, platform stats
- **User App** — Desktop app with 5-step onboarding, campaign dashboard, background agent
- **AI Matching** — Gemini scores user profiles against campaign briefs, with hard filters and niche-overlap fallback
- **AI Content Generation** — Platform-native content for X, LinkedIn, Facebook, Reddit. Research phase scrapes company URLs. Provider fallback chain (Gemini → Mistral → Groq).
- **Posting Engine** — Playwright automation with human emulation on 4 platforms (X, LinkedIn, Facebook, Reddit). Text, image+text, and image-only support.
- **Metric Scraping** — API-first for X and Reddit, browser fallback for LinkedIn and Facebook. Tiered schedule (1h, 6h, 24h, 72h).
- **Billing** — Incremental billing on metric submission, budget capping, auto-pause on exhaustion
- **Trust & Fraud** — Trust scoring (0-100), deletion detection, metrics anomaly detection, penalty system
- **Payments** — Stripe Checkout for company top-ups, Stripe Connect stub for user payouts

### Live URLs

- Company Dashboard: `https://server-five-omega-23.vercel.app/company/login`
- Admin Dashboard: `https://server-five-omega-23.vercel.app/admin/login`
- API Docs: `https://server-five-omega-23.vercel.app/docs`

### In Progress

- Verification of all built features (26/68 tasks complete)
- URL capture fixes for LinkedIn/Facebook/Reddit
- Remaining feature verification (metrics, billing, earnings, admin features)

---

## Risks and Honest Challenges

### Platform Detection

Social media platforms actively detect and block automation. Amplifier mitigates this with:
- Persistent browser profiles (looks like a real user)
- Human emulation (character-by-character typing, random delays, feed browsing)
- Stealth browser flags
- **But**: X has already locked one test account during development. This is the #1 technical risk.

**Mitigation path:** Official platform APIs (X API, LinkedIn API) for posting instead of browser automation. This is on the roadmap.

### Chicken-and-Egg Marketplace Problem

Every marketplace faces this: companies won't come without users, users won't come without campaigns.

**Approach:** Start with the personal brand engine (already built) to onboard early users who post their own content. Then introduce campaigns once there's a user base. Also: the founder's trading community provides an initial pool of beta users.

### Legal / Compliance

Automated posting on behalf of users may violate some platform ToS. FTC requires disclosure of paid partnerships.

**Approach:** Content guidance includes disclosure language. Long-term: pursue platform partnership programs and comply with advertising disclosure requirements.

### Revenue Scale

At 20% of micro-transactions, reaching meaningful revenue requires volume. $10M ARR needs ~$50M in total campaign spend flowing through the platform.

**Approach:** Focus on retention and automation. If companies see ROI, they increase budgets and create more campaigns. The flywheel: more users → better matching → better results → more company spend → more users.

---

## What We Need (The Co-Founder Opportunity)

### Current State

Amplifier is built by a solo founder. The V1 is functional — server deployed, 4 platforms working, AI pipeline operational. But scaling from "working prototype" to "real business" requires more than one person.

### What a Co-Founder Brings

**If technical:** Take ownership of the posting engine reliability (the hardest technical problem), platform API integrations, and infrastructure scaling. The solo founder handles product, growth, and business development.

**If business/growth:** Take ownership of go-to-market — acquiring the first 100 companies, building the user acquisition funnel, managing partnerships, and handling legal/compliance. The solo founder handles engineering and AI.

**Either way:** A co-founder brings accountability, complementary skills, and the ability to move twice as fast on a product that already works.

### The Opportunity

You're not joining a slide deck. You're joining a working product with:
- A deployed server handling real API traffic
- AI that generates genuinely good, platform-native content
- Browser automation that posts to 4 major platforms
- A billing system that calculates real earnings
- A trust system that detects fraud
- A clear path to revenue (company → budget → users → engagement → billing → cash out)

The hard engineering is largely done. What's needed now is the last mile: polishing the product, acquiring the first customers, and proving the business model works.

---

## Summary

| | |
|---|---|
| **What** | Marketplace connecting companies with everyday social media users for paid, AI-generated posts |
| **How** | AI generates content, Playwright posts it, metrics are scraped, billing is automatic |
| **Revenue** | 20% of all engagement-based earnings |
| **Stage** | V1 built and deployed, pre-revenue, in verification phase |
| **Market** | $21B influencer marketing market, targeting the long tail |
| **Differentiator** | Performance-based billing + AI-native everything + user-side compute |
| **#1 Risk** | Platform automation detection |
| **#1 Opportunity** | First mover in AI-powered micro-influencer marketplace |
