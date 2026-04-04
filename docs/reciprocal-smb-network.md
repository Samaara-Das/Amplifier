# Promote to Get Promoted: Reciprocal Cross-Promotion Network

**Status**: Idea stage — not started, will be built later
**Origin**: Daniel (co-founder) concept — "this is what Amplifier is really about"
**Relationship to current product**: The current paid campaign model (companies pay, users post) ships first. This reciprocal model becomes the V2 platform direction. Both models coexist in the same product.

---

## Table of Contents

1. [The Concept](#the-concept)
2. [How It Works](#how-it-works)
3. [Why This Is a Better Business](#why-this-is-a-better-business)
4. [The Credit System](#the-credit-system)
5. [Matching Algorithm](#matching-algorithm)
6. [Content Generation](#content-generation)
7. [Revenue Model](#revenue-model)
8. [Architecture: How It Maps to Existing Amplifier](#architecture-how-it-maps-to-existing-amplifier)
9. [Vertical Expansion](#vertical-expansion)
10. [Go-to-Market Strategy](#go-to-market-strategy)
11. [Risks and Mitigations](#risks-and-mitigations)
12. [Comparables and Prior Art](#comparables-and-prior-art)
13. [What to Build When](#what-to-build-when)

---

## The Concept

**"Promote to get promoted."**

Small businesses promote other non-competing small businesses on their social media accounts. In return, those businesses promote them back. Everyone becomes a lead generation engine for everyone else.

This is fundamentally different from the current Amplifier model:

- **Current model (V1):** One-directional paid reach. A company pays money, users post campaigns, users earn cash. Two separate actor types — demand side (companies) and supply side (users).
- **Reciprocal model (V2):** Every participant is both a promoter AND gets promoted. There's one actor type — a small business — that sits on both sides simultaneously.

The key reframe: **the "influencers" don't have to be random people. They can be other small businesses.** After all, those businesses are also run by people. And those people have a much stronger incentive to participate — they get their own business promoted in return, not just a few dollars.

The packaging: **"I am a small business, and I love to support other small businesses."** This isn't advertising. It's community support. It's word-of-mouth, automated.

---

## How It Works

### The Basic Mechanic

1. A **dentist** in Austin installs Amplifier and connects their social accounts (X, LinkedIn, Facebook)
2. Amplifier's matching algorithm finds 5 **non-competing local businesses**: an auto shop, a roofer, a laundromat, a personal trainer, a florist
3. The dentist's Amplifier app **automatically generates and posts** UGC-style content promoting those 5 businesses on the dentist's social accounts
4. In return, each of those 5 businesses' Amplifier apps **automatically post content promoting the dentist**
5. Result: the dentist promoted 5 businesses, and 5 businesses promoted the dentist. **5x the visibility the dentist could achieve alone.**
6. The more businesses a participant promotes, the more businesses promote them back
7. Commission layer: each business also **earns credits (or cash)** for the promotions they perform

### The Flywheel

```
Business joins network
        |
        v
Promotes other local businesses (automated by Amplifier)
        |
        v
Those businesses promote them back (automated by Amplifier)
        |
        v
Business gets real customers from cross-promotion
        |
        v
Business tells other business owners ("you need to get on this")
        |
        v
More businesses join --> network becomes more valuable for everyone
        |
        v
(repeat)
```

This is a true network effect. Every new business that joins makes the network more valuable for every existing member — more potential promoters, more diverse audiences, more visibility per participant.

### Concrete Example: One Day in the Network

**Morning (8 AM EST):** The dentist's Amplifier app posts on LinkedIn:
> "Quick shoutout to Dave's Auto on 5th Street. I've been taking my car there for 3 years — honest pricing, never tries to upsell. If you're in the Austin area and need a mechanic, Dave's your guy."

**Midday (12 PM EST):** The auto shop's Amplifier app posts on Facebook:
> "If anyone needs a great dentist, Dr. Sarah Chen on Congress Ave is phenomenal. My whole family goes to her. She just got some new equipment that makes cleanings way faster. Highly recommend."

**Evening (6 PM EST):** The roofer's Amplifier app posts on X:
> "Had my office redone by @ApexPainters last month. They matched the color perfectly and finished a day early. If you need painting done in Austin, these guys are the real deal."

None of this required any human effort. The content was AI-generated to sound like a genuine personal recommendation. The posting was automated. The scheduling was optimized for each platform's peak engagement windows.

Each business's followers see a trusted local recommendation — not an ad. That's the difference.

---

## Why This Is a Better Business

### The Cold Start Problem Disappears

The current Amplifier model has a classic two-sided marketplace cold start problem:
- You need **companies willing to pay** for campaigns (demand side)
- You need **users willing to post** campaigns (supply side)
- Companies won't pay until there are enough users
- Users won't join until there are enough campaigns
- Two separate acquisition funnels, two separate value propositions, two separate onboarding flows

The reciprocal model collapses both sides into one. Every SMB is both the company (wants promotion) and the user (promotes others). **One sale gets you both sides of the marketplace.** This isn't a small difference — it's the difference between a marketplace that never reaches liquidity and one that does.

### The Incentive Alignment Is Stronger

| Factor | Random Users (V1) | Small Businesses (V2) |
|--------|-------------------|-----------------------|
| **Motivation to post** | Earn $2-5 per post. Weak — barely worth the effort. | Get their own business promoted to new audiences. Strong — direct ROI in new customers. |
| **Content authenticity** | Random person promoting a brand they've never used. Feels like a paid ad. | Business owner recommending a fellow local business. Feels like word-of-mouth. |
| **Audience quality** | User's followers are personal connections — friends, family, college classmates. Mixed commercial intent. | Business's followers are customers and prospects. High commercial intent. |
| **Retention** | Leaves when a better side hustle appears. No switching cost. | Stays because their business depends on the promotion network. High switching cost. |
| **Acquisition cost** | Must find users AND companies separately. Two funnels. | One sale = one entity that is both promoter and promoted. One funnel. |
| **Network effect** | Users don't benefit from other users joining. No network effect. | Every new business makes the network more valuable for all existing members. True network effect. |
| **Lifetime value** | Low. Users churn when campaigns dry up. | High. Businesses stay as long as they're getting customers — potentially years. |

### The TAM Is Massive

- **33 million small businesses** in the US alone
- Every single one wants more customers
- Every single one has social media accounts they barely use (or use poorly)
- The current solution — pay for Facebook/Google ads, hire a social media manager — costs $500-5,000+/month and is out of reach for most SMBs
- Amplifier offers the same result (more visibility, more customers) at $29-79/month with zero effort

### The Emotional Pitch Is Viral

"I support small businesses" is something people genuinely feel good about. It's not a marketing angle — it's a cultural value. Small business owners already cross-refer informally. They already recommend each other at networking events, in casual conversations, on Nextdoor. Amplifier just automates what they already want to do.

The pitch at a networking event: "Install this app. It automatically promotes other local businesses on your social media. In return, they promote you. No ad spend. No effort." That room signs up on the spot. This pitch doesn't work for the current model ("install this app and post ads for companies to earn $3").

---

## The Credit System

### Why Credits (Not 1:1 Swaps)

Straight 1:1 promotion swaps don't work because businesses have vastly different audience sizes. A dentist with 15,000 followers promoting a barber with 300 followers is a wildly unequal exchange. The dentist is giving 50x more value than they're receiving.

The solution: **promotion credits** — an internal currency that normalizes the value of promotions across different audience sizes.

### How Credits Work

**Earning credits:**
- You earn credits every time your Amplifier app posts content promoting another business
- The number of credits earned is proportional to your reach: more followers + higher engagement = more credits per promotion
- Formula: `credits_earned = (your_follower_count / 1000) * platform_weight * engagement_multiplier`

**Spending credits:**
- You spend credits when another business promotes you
- The cost is proportional to the promoter's reach: being promoted by a high-reach business costs more credits
- Formula: `credits_spent = (promoter_follower_count / 1000) * platform_weight`

**Platform weights** (reflecting commercial value of each platform's audience):
| Platform | Weight | Rationale |
|----------|--------|-----------|
| LinkedIn | 1.2 | Highest commercial intent, professional audience |
| X | 1.0 | Baseline |
| Facebook | 0.8 | Broad but lower commercial intent |
| Reddit | 0.7 | Niche communities, lower direct conversion |

**Engagement multiplier:** 1.0 - 2.0, based on the promoter's actual engagement rate. Rewards businesses with active, engaged audiences over those with inflated follower counts.

### Credit Flow Example

**Setup:** 4 businesses in the Austin network:
- Dentist: 15,000 followers (X)
- Auto shop: 2,000 followers (X, Facebook)
- Restaurant: 10,000 followers (Facebook, Instagram)
- Personal trainer: 800 followers (Instagram)

**Week 1 activity:**

| Promoter | Promotes | Platform | Credits Earned | Credits Spent by Promoted |
|----------|----------|----------|----------------|---------------------------|
| Dentist | Auto shop | X | 15 | 15 |
| Dentist | Restaurant | X | 15 | 15 |
| Auto shop | Dentist | X | 2 | 2 |
| Auto shop | Trainer | Facebook | 1.6 | 1.6 |
| Restaurant | Dentist | Facebook | 8 | 8 |
| Restaurant | Trainer | Facebook | 8 | 8 |
| Trainer | Dentist | Instagram | 0.8 | 0.8 |

**End-of-week credit balances:**
- Dentist: earned 30, spent 10.8 → **surplus of 19.2 credits** (can cash out or save)
- Auto shop: earned 3.6, spent 15 → **deficit of 11.4 credits** (needs to promote more or buy credits)
- Restaurant: earned 16, spent 15 → **roughly balanced** (+1 credit)
- Trainer: earned 0.8, spent 9.6 → **deficit of 8.8 credits** (needs to promote more or buy credits)

**What happens with imbalances:**
- The dentist has surplus credits because their large audience generates more value per promotion. They can: (a) cash out surplus credits for real money, or (b) save them to get promoted by even larger businesses later
- The auto shop and trainer have deficits. They can: (a) promote more businesses to earn credits organically, (b) buy credits from Amplifier, or (c) accept fewer promotions until their balance recovers
- Amplifier facilitates the exchange and takes a cut on every credit purchase/cashout

### Credit Marketplace

- **Buying credits:** Businesses that want more promotion than they can earn organically buy credits from Amplifier. Price: $1 per credit (for example).
- **Cashing out credits:** Businesses with surplus credits sell them back to Amplifier. Price: $0.80 per credit (for example).
- **The spread** ($0.20 per credit, or 20%) is Amplifier's revenue from the credit marketplace.
- **This is identical in structure to the current 20% platform cut** on paid campaign earnings. Same economics, different mechanism.

---

## Matching Algorithm

### Reciprocal Matching vs. Current Campaign Matching

The existing Amplifier matching algorithm (hard filters + Gemini AI scoring) adapts for reciprocal matching. The core architecture stays the same — what changes are the filter dimensions.

### Hard Filters (Must Pass All)

**1. Non-competing industries**
- A dentist and a roofer: OK (no competition)
- A dentist and another dentist in the same area: NOT OK (direct competitors)
- Need an industry taxonomy. Options:
  - NAICS codes (6-digit, 1,057 categories — probably too granular)
  - Simplified Amplifier taxonomy (~50-100 categories): "Dental", "Auto repair", "Roofing", "Restaurant - Italian", "Restaurant - Mexican", "Personal training", "Salon", "Legal", etc.
  - Businesses self-select their category on signup. AI verifies from their website/Google listing.
- Same-category businesses within the same geographic area are excluded. Same-category businesses in different cities may be allowed (a dentist in Austin promoting a dentist in Dallas doesn't compete).

**2. Geographic proximity**
- Local businesses promoting each other is authentic. A dentist in Austin promoting a roofer in Seattle feels random and inauthentic.
- Default: same metro area or within 30 miles
- Configurable per business: some may want a wider radius (e.g., e-commerce businesses that serve nationally)
- Use zip code or city + state for matching. No need for precise geolocation.

**3. Platform overlap**
- Businesses must share at least 1 connected social platform
- No point matching a LinkedIn-only business with an Instagram-only business — neither can promote the other

**4. Quality threshold**
- Minimum trust score (from existing trust system)
- Minimum follower count (e.g., 100+ on at least one platform — filters out empty/fake accounts)
- Business verification: valid Google Business listing, or website domain ownership, or minimum social account age

**5. Credit eligibility**
- Business has enough credits to "pay" for the promotions they'll receive
- OR business opts into "earn first" mode: promote others first to build up credit balance before receiving promotions
- Prevents businesses from joining, getting promoted, and never promoting anyone back

### Soft Scoring (AI-Enhanced)

After hard filters, remaining candidates are scored on:

**1. Audience complementarity (highest weight)**
- Do their audiences share demographics but different needs?
- A dentist's patients are local homeowners. Homeowners also need roofers, plumbers, landscapers, auto mechanics. High complementarity.
- A dentist's patients and a skateboard shop's customers have little overlap. Low complementarity.
- AI evaluates this from both businesses' profile data, recent posts, and follower demographics.

**2. Brand alignment**
- Is the quality/price tier similar?
- Premium dental practice + budget laundromat: feels off-brand. The dentist's audience expects premium recommendations.
- Premium dental practice + premium personal trainer: feels natural. Similar clientele.
- AI evaluates from business website, pricing signals, review ratings, social media aesthetic.

**3. Content compatibility**
- Will a promotion post for Business B feel natural on Business A's feed?
- If Business A posts sleek professional content and Business B has a casual/funny brand, the cross-promotion might feel jarring.
- AI evaluates from recent post history, tone analysis, visual style.

**4. Reciprocal balance**
- Prefer matches where both businesses have similar reach (within 3x of each other)
- A 15,000-follower business promoting a 300-follower business creates a large credit imbalance
- Balanced matches are more sustainable long-term
- Not a hard filter — unbalanced matches still happen, but the credit system handles the value difference

### Match Output

The matching algorithm produces a ranked list of recommended cross-promotion partners for each business. The business can:
- **Accept all** — Amplifier handles everything automatically
- **Review and approve** — see who they'll be promoting and opt in/out per business
- **Block specific businesses** — "never promote this business" (for any reason)

---

## Content Generation

### The Voice: Personal Recommendation

This is NOT a campaign brief from a corporate marketing team. This is one local business owner recommending another to their audience. The AI content must sound like:

**What good cross-promotion content sounds like:**
- "If you're in the Austin area and need your roof done, I've been sending everyone to Apex Roofing. They did my office last year and were phenomenal."
- "Quick shoutout to my friend Maria at Bloom Florist — she did the arrangements for our office and the patients haven't stopped complimenting them."
- "Best auto shop in town? Dave's Auto on 5th Street. I've taken my car there for 3 years. Honest pricing, never tries to upsell."
- "I don't usually recommend other businesses on here, but I have to make an exception for @SunnySideCafe. Best breakfast tacos in Austin, hands down."

**What bad cross-promotion content sounds like:**
- "Check out this amazing business! They offer quality services at competitive prices." (generic, no personal connection, sounds like an ad)
- "SPONSORED: Visit Dave's Auto for all your automotive needs! Use code DENTAL10 for 10% off." (obviously paid, kills trust)
- "I'm proud to partner with Apex Roofing as part of a local business promotion network." (transparent about the mechanic, breaks the illusion)

### What the AI Needs Per Post

For each cross-promotion post, the AI content generator receives:

1. **Promoter's business profile** — name, industry, voice/tone from recent posts, audience demographics
2. **Promoted business's info** — name, what they do, location, key selling points (from their website/Google listing)
3. **A plausible connection** — AI constructs a believable reason the promoter knows/uses the promoted business. Options:
   - Geographic ("they're right down the street from my office")
   - Personal experience ("I've been going there for years")
   - Staff connection ("my employee recommended them")
   - Mutual customers ("so many of my patients have mentioned them")
4. **Platform-specific format:**
   - X: Punchy, 280 chars, direct recommendation
   - LinkedIn: Professional story, 200-500 chars, business context
   - Facebook: Conversational, 100-300 chars, community feel
   - Reddit: Genuine review style, detailed, no promotional language

### Content Rules

**Frequency limits:**
- Maximum **2-3 cross-promotions per week** per business account
- Never more than 1 per day
- Must be mixed with the business's own organic content (if any)
- Rotate which businesses are promoted — don't promote the same one repeatedly

**Authenticity safeguards:**
- Never disclose that the promotion is automated or part of a network
- Never use hashtags like #ad, #sponsored, #partner (because it's NOT paid promotion — it's reciprocal)
- Vary the content structure and tone — don't post the same template with different business names
- Include specific details about the promoted business (not just "they're great") — the AI should pull specific details from the business's website/profile
- Occasionally include a minor qualifier ("parking is a bit tight, but worth it") to sound real

**What to never generate:**
- Price claims ("cheapest in town") — could be false advertising
- Health/safety claims ("best dental work in Austin") — liability risk
- Guarantees ("you won't be disappointed") — can't guarantee another business's service
- Competitor bashing ("unlike that OTHER auto shop...") — unprofessional

### Image Generation

- Cross-promotion posts CAN include images but don't have to
- If the promoted business has good photos (from their Google listing, website, or social media), Amplifier can use those with img2img transformation to create UGC-style images
- If no photos available, text-only posts are fine — text recommendations are the most authentic format anyway
- Never use stock photos or obviously AI-generated images for cross-promotions — they undermine the authentic personal recommendation feel

---

## Revenue Model

### Five Revenue Layers

**Layer 1: Monthly subscription (primary, predictable)**

| Tier | Price | What You Get |
|------|-------|--------------|
| Free | $0 | 2 cross-promotions/month, basic matching, see if it works |
| Growth | $29/month | 10 cross-promotions/month, analytics dashboard showing reach/engagement from promotions received |
| Pro | $79/month | Unlimited cross-promotions, priority matching (promoted first by new members), premium placement, detailed analytics |

Revenue math: 1,000 Pro subscribers = ~$79K MRR. 10,000 Growth subscribers = ~$290K MRR. Blended: even modest adoption creates strong recurring revenue.

**Layer 2: Credit marketplace spread (20% take rate)**

- Amplifier buys surplus credits from high-reach businesses at $0.80/credit
- Amplifier sells credits to lower-reach businesses at $1.00/credit
- The $0.20 spread (20%) is pure margin
- Revenue scales automatically with network transaction volume
- This is the same take-rate model as the existing paid campaign billing system

**Layer 3: Premium placement**

- Businesses pay extra to jump the promotion queue — get promoted by higher-reach accounts first
- Similar to Yelp's boosted listings or Google Ads sponsored results
- Sold as a monthly add-on ($19-49/month) or per-placement fee ($5-10)
- Doesn't replace organic matching — it supplements it

**Layer 4: Paid campaigns (existing V1 model, preserved)**

- Larger companies with marketing budgets that want one-directional promotion (not reciprocal) still use the current paid campaign model
- They pay cash, users/businesses post their campaigns, posters earn cash
- This becomes the "enterprise" or "brand" tier of Amplifier
- Coexists with the reciprocal model — same platform, different campaign type (`campaign_type: "paid"` vs `campaign_type: "reciprocal"`)
- SMBs in the reciprocal network can ALSO accept paid campaigns from larger companies for extra income

**Layer 5: Vertical-specific licensing**

- Political campaigns, franchise networks, and large organizations license the platform at premium rates
- Custom matching rules, compliance features (FEC disclaimers for political), dedicated support
- $2K-$10K/month per organization
- See [Vertical Expansion](#vertical-expansion) below

### Revenue Projection (Conservative)

| Milestone | Timeline | Revenue |
|-----------|----------|---------|
| 100 businesses in 1 city (pilot) | Month 1-3 | $3-5K MRR (mostly Growth tier) |
| 500 businesses across 3 cities | Month 4-8 | $20-30K MRR |
| 2,000 businesses across 10 cities | Month 9-15 | $80-120K MRR |
| 10,000 businesses nationally | Month 16-24 | $400K-700K MRR |

These numbers assume blended ARPU of $40-70/business/month (mix of Free, Growth, and Pro tiers plus credit marketplace revenue).

---

## Architecture: How It Maps to Existing Amplifier

### What Stays the Same (Everything Core)

The entire Amplifier engine carries forward unchanged:

- **AI content generation** (AiManager, Gemini/Mistral/Groq fallback chain) — same engine, new content voice template
- **Image generation** (ImageManager, 5 providers, UGC post-processing) — same engine
- **Posting pipeline** (Playwright, JSON script engine, selector chains, human timing) — unchanged
- **Metric scraping** (hybrid API + Playwright, tiered schedule) — unchanged
- **Scheduling** (region-aware peak windows, spacing, jitter) — unchanged
- **Session management** (persistent browser profiles, health checks) — unchanged
- **Trust system** (0-100 score, fraud detection, penalties) — unchanged
- **User app** (Flask dashboard, background agent) — extended with new views

### What Changes

| Current Concept | Reciprocal Concept | What to Build |
|----------------|--------------------|-|
| Company (creates campaigns, pays) | SMB (both promotes and gets promoted) | `BusinessProfile` model — extends User with business-specific fields (name, industry, address, website, Google Business URL, credit balance, verified flag) |
| User (posts campaigns, earns cash) | Same SMB entity | Same user, same device, same app. The SMB is a User with `is_business=True` |
| Campaign (company manually writes brief) | Auto-campaign from business profile | Auto-generate a "promote my business" campaign by scraping the business's website and Google Business listing. No manual brief writing needed. |
| Matching (AI scores user-to-campaign fit) | Reciprocity matching (non-competing, local, complementary) | Add new filter dimensions: industry_code exclusion, geographic proximity, credit balance. New `reciprocal_matching.py` service alongside existing `matching.py` |
| Content gen (UGC voice for brand campaign) | Cross-promotion voice (personal recommendation) | New content template/voice: "local business recommendation" mode in ContentGenerator |
| Billing (impressions x rate = cash) | Credits (promote = earn, get promoted = spend) | New `CreditLedger` model + credit exchange logic alongside existing Payout system |
| Payout (Stripe Connect cash out) | Credit cash-out or reinvest | Existing Stripe payout handles credit-to-cash conversion |

### New Database Models

```
BusinessProfile
    id                  INTEGER PRIMARY KEY
    user_id             INTEGER FK → User
    business_name       TEXT NOT NULL
    industry_code       TEXT NOT NULL (FK → IndustryTaxonomy)
    business_address    TEXT
    city                TEXT
    state               TEXT
    zip_code            TEXT
    business_website    TEXT
    google_business_url TEXT
    google_rating       REAL
    verified            BOOLEAN DEFAULT FALSE
    credit_balance      INTEGER DEFAULT 0 (in credit units)
    created_at          DATETIME

IndustryTaxonomy
    code                TEXT PRIMARY KEY ("dental", "auto_repair", "roofing", etc.)
    name                TEXT NOT NULL
    category            TEXT ("health", "home_services", "food", "retail", etc.)
    non_compete_group   TEXT (businesses in same group + same area can't cross-promote)

CreditLedger
    id                  INTEGER PRIMARY KEY
    business_id         INTEGER FK → BusinessProfile
    type                TEXT ("earned", "spent", "purchased", "cashed_out")
    amount              INTEGER (credit units, can be negative for spent/cashed_out)
    related_exchange_id INTEGER FK → PromotionExchange (nullable)
    description         TEXT
    created_at          DATETIME

PromotionExchange
    id                  INTEGER PRIMARY KEY
    promoter_id         INTEGER FK → BusinessProfile
    promoted_id         INTEGER FK → BusinessProfile
    platform            TEXT
    post_url            TEXT
    content_text        TEXT
    credits_earned      INTEGER (by promoter)
    credits_spent       INTEGER (by promoted)
    status              TEXT ("scheduled", "posted", "verified", "failed")
    posted_at           DATETIME
    verified_at         DATETIME (metrics confirmed post is live)
    created_at          DATETIME
```

### New Services

```
server/app/services/
    reciprocal_matching.py    # Non-competing, geographic, credit-balanced matching
    credit_exchange.py        # Credit earning, spending, purchasing, cashout logic
    business_verification.py  # Google Business listing verification, website check
    auto_campaign.py          # Auto-generate campaign brief from business profile/website
```

### User App Changes

The local user app (Flask dashboard) adds:
- **Business profile setup** in onboarding (business name, industry, address, website)
- **Network view** — see which businesses are promoting you and which you're promoting
- **Credit balance** — current credits, earning/spending history
- **Match preferences** — approve/block specific businesses, set quality tier preference
- **Promotion feed** — see all cross-promotions posted on your behalf (with engagement metrics)

---

## Vertical Expansion

The reciprocal promotion engine is a general-purpose growth tool. The core technology (AI content, automated posting, matching, credits) stays the same. What changes per vertical: matching rules, content voice, onboarding flow, and revenue model.

### Tier 1: Build First (Highest Conviction)

**Local SMBs** (primary vertical)
- Who: Dentists, roofers, restaurants, salons, auto shops, personal trainers, florists, lawyers, accountants — any local service business
- Matching: Non-competing industries + same metro area
- Content: Personal recommendation ("my buddy's shop")
- Revenue: Subscription $29-79/month
- TAM: 33M US small businesses
- Why first: Strongest pitch, highest retention, clearest network effect

**Political campaigns** (already documented in `docs/political-campaigns.md`)
- Who: Candidates + local business supporters
- Matching: Same district + political alignment
- Content: Grassroots endorsement, GOTV messaging
- Revenue: Campaign pays 25-30% platform cut, $500 minimum budget
- Why Tier 1: Massive spend ($16B/cycle), time-bound urgency, existing doc with full strategy

### Tier 2: Build After SMBs Prove Out

**Creator collectives**
- Who: Indie musicians, podcasters, YouTubers, Substack writers, course creators
- Matching: Same genre/niche + similar audience size (within 5x)
- Content: "Check out this incredible artist/creator I've been following"
- Revenue: Freemium subscription ($0/free, $19/month pro)
- Why: Every small creator's #1 problem is discovery. Cross-promotion is the proven growth hack (podcast swaps, YouTube collabs). Amplifier automates the coordination AND the content.

**E-commerce / DTC brands**
- Who: Small Shopify stores, Etsy sellers, Amazon FBA brands
- Matching: Non-competing product categories + similar price tier
- Content: "I've been using this and love it" — product recommendation UGC
- Revenue: % of attributed sales (affiliate tracking) or subscription
- Why: Meta CPMs are $15-30 for small DTC brands. Cross-promotion from a trusted brand page is free and more effective. This IS what DTC brands pay influencers $200-2,000/post for.

**Nonprofits / causes**
- Who: Food banks, animal shelters, literacy programs, community organizations
- Matching: Mission-aligned + same region
- Content: "This organization is doing incredible work in our community"
- Revenue: Grant-funded subscription or donation-based
- Why: Nonprofits genuinely want to support each other. Their boards and volunteers have personal social accounts with untapped reach. "Every nonprofit in your city promoting every other nonprofit" is a powerful pitch.

### Tier 3: Explore After Validation

| Vertical | Participants | Matching | Content Voice | Revenue Model |
|----------|-------------|----------|---------------|---------------|
| SaaS / B2B tools | Non-competing software companies | Complementary tools (CRM + design tool) | "Our team uses this daily" | Per-lead fee or subscription |
| Real estate agents | Agents in different neighborhoods | Non-overlapping territories | "Looking in [area]? Talk to [agent]" | Referral fee split |
| Freelancers / consultants | Designers, copywriters, devs, coaches | Non-competing specialties | "Need a [skill]? I always recommend [name]" | Subscription |
| Events / conferences | Meetup organizers, conference hosts | Non-competing dates/topics | "Can't make ours? Check out [event]" | Per-registration attribution |
| Franchise networks | Individual franchise locations | Same brand, different cities | Corporate-approved cross-location promotion | Franchise HQ pays |
| Recruiters | Recruiters in different industries | Non-competing industries | "Know someone in [field]? My colleague is hiring" | Placement fee split |

### The Pattern Behind All Verticals

Every vertical shares three properties:
1. **Fragmented actors** — many small players, none with enough reach alone
2. **Non-competing relationships** — they don't steal each other's customers/audience
3. **Underutilized audiences** — they have followers/connections they're barely monetizing

Amplifier is the **coordination layer** that turns fragmented, underutilized audiences into a collective growth network. The engine is the same. The vertical is just the context.

---

## Go-to-Market Strategy

### City-by-City Rollout (Not National Launch)

Don't launch nationally. Pick **one metro area** and saturate it. Get density. Get case studies. Then expand.

**Ideal pilot city characteristics:**
- Mid-size metro (500K-2M population)
- High SMB density
- Active local business networking culture (BNI chapters, chamber of commerce, Nextdoor)
- Tech-friendly / early-adopter culture
- Examples: Austin TX, Phoenix AZ, Charlotte NC, Nashville TN, Denver CO

### Acquisition Channels (Ranked by Conviction)

**1. BNI groups and chamber of commerce meetings (highest conviction)**
- Walk into any local business networking event and pitch: "Install this app. It automatically promotes other local businesses on your social media. In return, they promote you. No ad spend. No effort."
- BNI groups are literally built on the principle of reciprocal referrals. Amplifier automates what they already do manually.
- One pitch at one BNI chapter = 20-40 businesses exposed to the concept. Target: 3-5 signups per event.
- There are 10,000+ BNI chapters worldwide. This is a scalable acquisition channel.

**2. Local business Facebook groups**
- Every city has multiple "Austin Small Business Owners", "Phoenix Entrepreneurs" type groups
- Post results: "5 local businesses in Austin started cross-promoting each other last month. The dentist got 47 new appointment requests. The auto shop got 23. Zero ad spend."
- Social proof + specific numbers = signups

**3. Referral program (built into the product)**
- Each business that joins can invite 5 others
- The inviter gets bonus credits (equivalent to $10-20 in promotion value)
- The invitee gets a free month of Growth tier
- This mirrors how BNI grows — personal referrals between business owners who trust each other
- Viral coefficient target: 1.3+ (each business brings in 1.3 more on average)

**4. Local business directories / Google Maps outreach**
- Identify clusters of non-competing businesses in the same area
- Cold outreach: "We matched you with 5 businesses near you who want to cross-promote. Here's what that looks like."
- Include a mock-up of what the AI-generated cross-promotion post would look like for THEIR business

**5. Partnerships with business service providers**
- Accountants, bookkeepers, business coaches, web designers — anyone who serves multiple SMB clients
- They become channel partners: recommend Amplifier to their client base, earn a referral fee
- One accountant with 50 SMB clients = 50 potential Amplifier businesses

### The Pitch (Reframed for Different Audiences)

| Audience | Pitch |
|----------|-------|
| Business owner who does no marketing | "Your social media runs itself and brings you customers. No ads. No agency. Just other local businesses recommending you." |
| Business owner who runs Facebook ads | "You're paying $500/month for ads. What if 5 other businesses promoted you for free — to their own customers?" |
| Business owner who is skeptical | "You only promote businesses you'd actually recommend. You can approve or block any match. It's word-of-mouth, automated." |
| BNI member | "You already do referrals. Amplifier puts those referrals on social media where they reach 1,000x more people — automatically." |
| Business owner afraid of social media | "You don't touch social media at all. The app handles everything — content, posting, scheduling. You just approve or let it run." |

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Audience mismatch** — dentist's followers don't care about a roofer | Medium | AI matching scores audience complementarity. Content framed as genuine personal recommendation, not ad. Frequency limited to 2-3/week so it doesn't dominate the feed. |
| **Quality / reputation contamination** — premium brand accidentally promotes a bad business | High | Business verification via Google Business listing (minimum 3.5 star rating). Opt-in quality tiers ("only match me with 4+ star businesses"). Ability to review and block specific businesses before any promotion goes live. |
| **Content feels spammy** — followers unfollow because the feed is full of promotions | High | Strict frequency limits: max 2-3 cross-promotions per week, never more than 1 per day. Content must be mixed with the business's own organic posts. AI generates varied, authentic-sounding recommendations (not templates). |
| **Value imbalance** — large business gives far more than it receives | Medium | Credit system handles this mathematically. Large businesses earn surplus credits they can cash out or save. Small businesses buy credits or promote more businesses to earn. The system is designed for imbalance — credits normalize it. |
| **Cold start** — need businesses on both sides for the network to work | High | Seed with existing BNI groups (they already cross-refer and will adopt fastest). Start with 10-20 businesses in one city and run manually initially. Amplifier staff can be "seed promoters" for early members until density grows. |
| **Gaming / fake businesses** — people create fake accounts to earn credits | Medium | Business verification (Google Business listing, website domain ownership, minimum social account age). Trust score system flags anomalies. Credit cashout requires identity verification. |
| **Platform ToS risk** — automated posting may violate social media terms of service | Medium | Same risk as current Amplifier V1. Mitigated by: human-emulation posting engine, persistent browser sessions (not automation frameworks), natural posting frequency (2-3/week is less than most humans), no bulk behavior. |
| **Cannibalization of paid model** — if businesses promote each other for free via credits, why would companies pay for campaigns? | Low | Different segments entirely. SMBs use reciprocal model (free/cheap, local reach, community feel). Larger brands with marketing budgets use paid campaigns (guaranteed reach, precise targeting, no reciprocal obligation, national/global reach). Both coexist. |
| **Legal risk** — is automated cross-promotion considered advertising? | Low-Medium | It's not paid advertising — no money changes hands between businesses (credits are internal). It's closer to word-of-mouth referrals. However: FTC guidelines on endorsements may apply if the relationship isn't disclosed. Research needed on whether reciprocal promotion networks require disclosure. |
| **Content quality degradation at scale** — AI recommendations get repetitive or generic | Medium | Track content variety metrics per business. Flag and regenerate content that's too similar to previous posts. Rotate recommendation angles (personal experience, staff recommendation, community shoutout, specific product/service highlight). |

---

## Comparables and Prior Art

### What exists today and how Amplifier differs:

**BNI (Business Network International)**
- 300,000+ members worldwide doing in-person reciprocal referrals
- Limitation: manual, in-person only, doesn't scale to social media
- Amplifier relationship: automates what BNI does manually, extends it to social media reach

**Alignable**
- Social network for local businesses (like LinkedIn for SMBs)
- Limitation: businesses post on Alignable's platform, not on their own social accounts. Reach stays within Alignable.
- Amplifier relationship: posts go on the business's OWN social accounts, reaching their actual followers (not a separate platform's user base)

**Nextdoor**
- Local community network where businesses can participate
- Limitation: recommendations are organic/manual, no automation, limited to Nextdoor's platform
- Amplifier relationship: automated content + posting to all major social platforms, not confined to one network

**Yelp / Google Business (review-based visibility)**
- Businesses get visibility through customer reviews
- Limitation: reviews are passive (depend on customers writing them), expensive to boost (Yelp ads)
- Amplifier relationship: active promotion by peer businesses, not passive reviews. And it's reciprocal.

**Influencer marketing platforms (AspireIQ, Grin, Creator.co)**
- Connect brands with influencers for paid promotions
- Limitation: expensive ($200-5,000+ per post), designed for brand-influencer relationships, not peer-to-peer SMB
- Amplifier relationship: same underlying mechanic (someone promotes your business) but peer-to-peer, reciprocal, and dramatically cheaper

**Key differentiator:** None of these combine (1) automated AI content generation + (2) automated social media posting + (3) reciprocal peer-to-peer promotion + (4) credit-based fair exchange. Each existing solution does 1-2 of these. Amplifier does all 4.

---

## What to Build When

This is a future direction. The sequencing matters.

### Phase 0: Ship Current V1 (NOW)

Before building any reciprocal features:
1. The current paid campaign model (companies pay, users post) must work **end-to-end**: content generates, posts go live, metrics come back, earnings calculate, payouts work
2. Get 1 real company to run 1 real campaign with 1 real user posting, real engagement, real earnings
3. Prove the engine works with real money before expanding the business model

### Phase 1: Manual Validation (After V1 Works)

Validate the reciprocal model WITHOUT building new features:
1. Find 5 local SMBs in one city who are non-competing
2. Set them up as both Companies AND Users in the existing Amplifier system
3. Manually create campaigns for each business (use the existing AI campaign wizard to generate briefs from their websites)
4. Each business's Amplifier app posts the other businesses' campaigns
5. Run for 2-4 weeks. Measure:
   - Did they get real engagement on the cross-promotion posts?
   - Did they get real leads / new customers?
   - Did the content feel authentic to their followers?
   - Did any followers complain or unfollow?
   - Would the businesses pay $29-79/month for this?
6. If YES → proceed to Phase 2
7. If NO → understand why and iterate before committing engineering time

### Phase 2: Build Reciprocal Features (After Manual Validation)

Only build after Phase 1 proves the concept works:
1. BusinessProfile model + onboarding flow
2. Industry taxonomy + non-competition matching
3. Credit system (earning, spending, purchasing, cashout)
4. Auto-campaign generation from business profile
5. "Personal recommendation" content voice in ContentGenerator
6. Business network view in user app dashboard
7. Subscription tiers (Free / Growth / Pro)

### Phase 3: Scale and Expand (After Phase 2 Has Traction)

Once the SMB reciprocal model has 100+ businesses and proven unit economics:
1. City-by-city expansion (3-5 cities)
2. Referral program with viral mechanics
3. Channel partner program (accountants, business coaches)
4. Premium placement + credit marketplace
5. Begin exploring Tier 2 verticals (creators, DTC, nonprofits)

### What NOT to Do

- Do NOT build credit system, reciprocal matching, or business profiles before the current V1 engine is proven end-to-end
- Do NOT launch in multiple cities simultaneously — density in one city beats presence in ten
- Do NOT build vertical-specific features (creators, SaaS, etc.) before SMBs are working
- Do NOT over-engineer the credit system before understanding real-world credit flow patterns
- Do NOT assume the reciprocal model replaces the paid campaign model — they coexist

---

*This document captures Daniel's "promote to get promoted" concept as a strategic direction for Amplifier V2. The current paid campaign marketplace (V1) ships first. Everything in this doc is built later, after V1 is proven and the reciprocal model is manually validated.*
