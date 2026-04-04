# Amplifier — Pitch Deck

---

## Slide 1: Title

# Amplifier

### The AI-powered marketplace that turns everyday social media users into a distribution channel.

Companies pay for real engagement. Users earn by posting. AI handles everything in between.

---

## Slide 2: The Company Problem

# Companies can't afford social media marketing.

| What exists today | The problem |
|---|---|
| Influencer marketing | $500-$50,000 per post, no performance guarantee |
| Social media ads | Auction-based pricing, declining organic reach |
| Organic posting | Requires a team, takes months to build, no reach |
| Affiliate marketing | Saturated, looks like ads, audiences tune it out |

**Result:** Small-to-mid companies — the ones who need it most — are priced out of social media distribution.

---

## Slide 3: The User Problem

# 5 billion people use social media daily and earn nothing from it.

- YouTube monetization requires **1,000 subscribers + 4,000 watch hours**
- TikTok Creator Fund requires **10,000+ followers**
- Instagram bonuses are **invite-only**
- 99% of social media users have **no path to earning money** from the time they spend online

**The opportunity:** Turn the long tail of social media — normal people with 200-2,000 followers — into a paid distribution channel.

---

## Slide 4: The Solution

# Amplifier connects companies with everyday people for paid social media posts.

**For companies:**
- Describe your product → AI generates your entire campaign
- Set a budget and pay-per-engagement rates
- Users matched by AI start posting within 24 hours
- Pay only for real impressions, likes, shares, and clicks

**For users:**
- Connect your social accounts
- Accept campaigns matched to your niche
- AI generates platform-native content for you
- Earn money from your posts' engagement

**AI handles:** Campaign briefs, user matching, content generation, posting, metric tracking, and billing.

---

## Slide 5: How It Works

```
COMPANY                         AMPLIFIER                        USER
                                
1. Create campaign     ───►    AI generates brief       ───►   Matched by niche & profile
   (product + budget)          AI matches users                 
                                                                
2. Budget locked       ◄───    Invitations sent         ───►   Accepts campaign (max 3)
                                                                
                               AI generates content     ───►   Reviews & approves
                               (per-platform, UGC-style)       (or auto-posts)
                                                                
3. Tracks performance  ◄───    Posts to social media    ◄───   Playwright automation
                               Scrapes engagement              (human emulation)
                                                                
4. Pays per engagement ───►    Calculates billing       ───►   Earns 80% of engagement value
   (from campaign budget)      Takes 20% cut                   Cashes out at $10+
```

**End-to-end automation.** Company sets it up once. Users accept and earn. Everything else is AI.

---

## Slide 6: Market Size

# $21 billion influencer marketing market, growing 30%+ annually.

| | Size | Description |
|---|---|---|
| **TAM** | $21B | Global influencer marketing spend |
| **SAM** | $5B | US small-to-mid companies spending $500-$50K/year on social media |
| **SOM** | $50M | 10,000 companies × $5,000 avg spend × 20% take rate (3-year target) |

### Why now:
- **AI content is finally good enough** — platform-native UGC that doesn't look AI-generated
- **Organic reach is dying** — companies need new distribution channels beyond ads
- **Gig economy is mainstream** — people expect to earn from apps
- **The long tail is untapped** — nobody is monetizing the 99% of users with <2K followers

---

## Slide 7: Business Model

# 20% of every dollar that flows through the platform.

```
Company pays $1.00 for engagement
    → $0.80 goes to the user
    → $0.20 goes to Amplifier
```

| Metric | Value |
|---|---|
| Revenue model | 20% marketplace take rate |
| Average campaign budget | $200-$500 |
| Amplifier revenue per campaign | $40-$100 |
| Cost to serve per campaign | ~$2-5 (AI APIs + hosting) |
| Gross margin | ~90%+ |
| User payout minimum | $10 |
| Minimum campaign budget | $50 |

**Why margins are high:**
- AI APIs use free tiers (Gemini, Mistral, Groq)
- Hosting on Vercel free/hobby tier
- All compute-heavy work (browser automation, AI generation) runs on users' devices
- No content moderation team needed — AI generates, trust system monitors

---

## Slide 8: Competitive Landscape

|  | Amplifier | Influencer Agencies | Affiliate Networks | UGC Platforms |
|---|---|---|---|---|
| **Who posts** | Normal people (AI-assisted) | Influencers (manual) | Anyone (manual) | Creators make content, brand distributes |
| **Payment** | Per engagement | Per post (upfront) | Per conversion | Per content piece |
| **Content** | AI-generated, platform-native | Creator-made | Creator-made | Creator-made |
| **Distribution** | Direct to user's real accounts | Direct to influencer's accounts | Links shared by affiliates | Brand's own channels |
| **Min budget** | $50 | $500-$50,000 | Varies | $200-$1,000 |
| **Setup time** | Minutes | Weeks | Days | Days |
| **Follower requirement** | None | 10K+ typically | None | Varies |

### Amplifier's moat:
1. **AI-native from day one** — not bolted onto a manual process
2. **User-side compute** — credentials never leave user's device, eliminates ban risk at scale
3. **Performance billing** — only sustainable with automated metric scraping, which we've built
4. **Network effects** — more users → better matching → better results → more companies → more users

---

## Slide 9: What's Built (Traction)

# This is not a slide deck. It's a working product.

### Shipped (V1)

| Component | Status | Details |
|---|---|---|
| **Server API** | Live | ~90 routes (27 API + 36 admin + 21 company + 2 system + 2 health), Vercel + Supabase PostgreSQL |
| **Company Dashboard** | Live | Campaign wizard, analytics, billing, settings |
| **Admin Dashboard** | Live | Users, campaigns, fraud detection, payouts |
| **User Desktop App** | Working | 5-step onboarding, campaign management, earnings |
| **AI Matching** | Working | Gemini-powered profile scoring + hard filters |
| **AI Content Generation** | Working | Platform-native text + images for X, LinkedIn, Facebook, Reddit. img2img from campaign product photos, daily image rotation. |
| **Posting Engine** | Working | 4 platforms, JSON script engine with fallback selector chains, human emulation, image support |
| **Metric Scraping** | Working | API + browser hybrid, tiered schedule |
| **Billing Engine** | Working | Incremental, dedup, auto-pause on budget exhaustion |
| **Trust & Fraud** | Working | Score system, deletion + anomaly detection |
| **Payments** | Working | Stripe Checkout + Connect (test mode) |

### Live URLs
- Company Dashboard: `server-five-omega-23.vercel.app/company/login`
- Admin Dashboard: `server-five-omega-23.vercel.app/admin/login`
- API Docs: `server-five-omega-23.vercel.app/docs`

---

## Slide 10: Product Highlights

### Company Experience
- **AI Campaign Wizard** — Paste your product URL. AI scrapes your site and generates a complete campaign: title, brief, content guidance, targeting, payout rates. Under 5 minutes to go live.
- **Real-Time Analytics** — See every post, every user, every metric. Per-platform breakdown. CSV export.
- **Budget Control** — Set max budget, auto-pause when exhausted, top up anytime. Pay only for engagement.

### User Experience
- **Zero-Effort Earning** — AI generates content. App posts it. Metrics are tracked. Money appears.
- **Semi-Auto or Full-Auto** — Review every post before it goes live, or let the AI handle everything.
- **Multi-Platform** — One app, four platforms (X, LinkedIn, Facebook, Reddit). More coming.

### AI Content Quality
- **Platform-native** — A tweet doesn't look like a LinkedIn post doesn't look like a Reddit thread
- **Research-backed** — AI scrapes company websites before writing
- **UGC-style** — Reads like a real person sharing their experience, not an ad
- **Anti-repetition** — Each post uses different hooks, angles, and structures

---

## Slide 11: Roadmap

| Phase | Timeline | Focus |
|---|---|---|
| **V1 Verification** | Now | Fix remaining bugs, verify all features end-to-end |
| **Beta Launch** | Q2 2026 | First 10 companies, 100 users. Validate unit economics. |
| **Content Quality** | Q3 2026 | 4-phase AI content agent, image/video generation, platform preview |
| **Reliability** | Q3 2026 | Official platform APIs (replace Playwright), X lockout fix |
| **Scale** | Q4 2026 | Free/paid tiers, self-learning content, mobile companion app |
| **Distribution** | 2027 | Web-based user dashboard, Tauri desktop agent, public API |

### Key milestones:
- **First paying company** — validate that companies will put real money in
- **First user payout** — validate that users earn and cash out
- **100 concurrent campaigns** — validate scaling and matching quality
- **Official platform APIs** — eliminate automation detection risk

---

## Slide 12: Team & What We Need

### Current Team

**Solo Founder** — Built the entire V1: server, dashboards, AI pipeline, posting engine, billing, fraud detection, deployment. Background in trading indicators, social media automation, and AI integration.

### What We Need

**A co-founder who brings:**

| If Technical | If Business/Growth |
|---|---|
| Own the posting engine reliability | Own go-to-market and first 100 companies |
| Platform API integrations | User acquisition and retention |
| Infrastructure and scaling | Legal, compliance, FTC disclosure |
| AI content quality improvements | Partnerships with platforms and brands |

### Why join now:
- The hard engineering is done — V1 works end-to-end
- Pre-revenue means maximum equity upside
- Clear path to revenue with a working product
- $21B market growing 30% annually
- First-mover in AI-powered micro-influencer marketplace

---

## Slide 13: The Ask

# Join as co-founder and help turn a working product into a real business.

### What's on the table:
- **Equity partnership** in a product that already works
- **Ownership** of your domain (technical or business)
- **A clear 90-day plan:** Ship beta → onboard first 10 companies → validate unit economics

### What you'd be working with:
- A deployed, functional marketplace with AI matching, content generation, automated posting, and billing
- A clear technical architecture that separates concerns (server vs. user app vs. engine)
- A codebase that's documented, version-controlled, and structured for scale
- A founder who ships fast and values speed over perfection

### Next step:
Access the repo, explore the codebase, try the live dashboards. If the vision resonates and the product impresses, let's talk about building this together.

---

*Built with AI. Powered by real people.*
