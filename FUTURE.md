# Amplifier — Future Features

Deferred features that are designed but not yet implemented. The backend/model support exists — just needs UI and tracking integration.

## AI-Powered Profile Scraping (MAJOR)

**Status**: Not started
**Priority**: High — this is a foundational upgrade

**Current problem**: Profile scrapers use CSS selectors and regex to extract data from social media pages. These break constantly when platforms change their DOM. The scraper misses data, picks up wrong text (e.g., group names instead of post content), and can't understand context.

**Goal**: Replace brittle selector-based scraping with AI-powered extraction. Send a screenshot or page text to a vision LLM (Gemini, GPT-4V) and ask it to extract structured profile data. This makes scraping:
- **Robust**: No selectors to break. AI reads the page like a human.
- **Insightful**: AI can understand the person's content style, niche, audience, tone — not just follower counts.
- **Adaptive**: Works even when platforms change their UI.

**Approach**:
1. Navigate to each profile page with Playwright
2. Take a screenshot or extract body text
3. Send to Gemini Vision API: "Extract this person's profile data: name, bio, followers, recent posts with engagement, content themes, audience demographics"
4. Parse the structured JSON response
5. AI can also classify niches, detect content quality, estimate audience demographics

**Cost consideration**: Gemini 2.0 Flash has free tier. One API call per platform per scrape. ~4 calls per onboarding = negligible cost.

## Per-Click Payout Rate

**Status**: Backend ready, UI removed
**Why deferred**: Can't track link clicks. Metric scraping reads public engagement counts (impressions, likes, reposts, comments) via Playwright. Click data requires platform analytics API access or UTM link tracking.

**What exists**:
- `Campaign.payout_rules["rate_per_click"]` field in the model (defaults to $0.10)
- Billing calculation includes clicks: `clicks * rate_per_click`
- Form parameter `rate_per_click` accepted on campaign create/edit

**To enable**:
1. Generate UTM-tracked short links for each campaign + creator combo
2. Host a redirect service (or use Bitly/short.io API) to count clicks
3. Report click counts in metric scraping
4. Re-add "Per Click ($)" field to campaign wizard Step 4

## Flux.1 Image & Video Generation

**Status**: Not started
**Priority**: High — first media generation feature to ship
**Cost to user**: ~$0.30 per session (vast.ai GPU rental)

**What it does**: Users opt in to Flux.1 image generation for their campaign posts. Flux.1 runs on vast.ai rented GPUs, generates high-quality UGC images (product shots, lifestyle images, branded visuals) tailored to each campaign and platform. Users pay ~$0.30 per generation session — ultra cheap for professional-quality content that drives real engagement.

**Why Flux.1 first**:
- Best quality-to-cost ratio available right now
- vast.ai GPU rental is ~$0.20-0.30/hour — one session generates multiple images
- High-quality output that looks like real UGC, not AI slop
- Open-weight model — no vendor lock-in

**User experience**:
1. During content generation, user sees option: "Generate images for this post ($0.30)"
2. If opted in: Flux.1 generates platform-specific images (landscape for LinkedIn/Facebook, square for Instagram, vertical for TikTok)
3. Images attached to draft alongside the AI-generated text
4. User can preview, swap, or remove images before approving
5. Posting pipeline uploads the image along with text

**What changes when this ships**:
- Content generation pipeline: add image gen step after text gen
- Draft model: drafts need an `images` field (list of local file paths)
- Posting pipeline: each platform's post function needs to handle image uploads (most already do — X, LinkedIn, Facebook, Reddit all have image upload code in post.py)
- Campaign wizard: companies can specify if they want image content
- User settings: opt-in toggle + vast.ai billing setup

**Future expansion** (not part of this task):
- Video generation via LTX + TTS, Seedance, MakeUGC
- Meme generation via Supermeme.ai, CapCut
- Local GPU inference for users with capable hardware (zero cost)
- LoRA training per-user for face/style consistency
- DALL-E, Nano Banana, Ideogram as alternative providers

## Platform-Specific Content Formats + Posting System Upgrade

**Status**: Not started
**Why deferred**: Current posting only supports basic text + single image per platform. Each platform has unique content formats that drive higher engagement. The posting system (`post.py`) must be updated to handle all common formats.

**All 6 platforms must be supported**: X, LinkedIn, Facebook, Reddit, TikTok, Instagram.

**Formats to add per platform** (most-used formats that the posting system must handle):

**X (Twitter)**:
- Text-only tweet
- Image + text tweet
- Multi-image tweet (up to 4 images)
- Thread posts (multi-tweet, linked together)
- Polls
- Quote tweets

**LinkedIn**:
- Text-only post
- Image + text post
- Document/carousel uploads (PDF slides — high engagement format)
- Polls
- Articles (long-form)
- Video posts

**Facebook**:
- Text-only post
- Image + text post
- Photo albums (multiple images)
- Polls
- Video posts
- Stories

**Reddit**:
- Text posts (title + body)
- Link posts (title + URL)
- Image posts
- Polls
- Cross-posting to multiple subreddits

**Instagram** (currently disabled — re-enable):
- Single image + caption
- Carousels (multiple images/slides)
- Reels (short video)
- Stories

**TikTok** (currently disabled — re-enable):
- Video posts
- Slideshows (image sequence as video)
- Duets
- Stitches

**To implement**:
1. Update content generator to produce format-specific content (e.g., thread = array of tweets, carousel = array of slides)
2. Update `post.py` platform functions to handle each format's upload flow
3. Add format selection to campaign wizard (company can specify preferred formats)
4. AI should pick the best format per platform based on the content and campaign goal

## Sophisticated AI Content Generation (MAJOR)

**Status**: Not started
**Priority**: Critical — this is the core value proposition of Amplifier

**Current problem**: Content generation produces basic text posts. To drive real campaign results (viral views, lead gen, brand awareness, FOMO, hype), Amplifier needs to generate rich media UGC — memes, short-form videos, photorealistic product shots, carousels, talking-head videos — all tailored to the campaign goal.

**Campaign goal → content strategy mapping**:
- **Viral views**: Memes, short-form video, controversial takes, trend-jacking
- **Lead generation**: Carousels with CTAs, comparison graphics, before/after
- **Brand awareness**: Lifestyle product shots, UGC-style "real person using product"
- **FOMO/Hype**: Countdown graphics, limited-offer visuals, social proof collages
- **Engagement**: Polls, questions overlaid on images, interactive carousels

### Image Generation Tools (ranked by cost-effectiveness)

| Tool | Pricing | Best For |
|------|---------|----------|
| **FLUX.2 (local via ComfyUI)** | Near-zero (run locally) | High-volume personalized images, LoRAs for brand consistency |
| **Google Nano Banana Pro** | Free tier + $20/mo Pro | Photorealism, text rendering, character consistency across images |
| **ChatGPT (GPT-Image 1.5/4o)** | Free tier + $20/mo | Conversational editing ("make more casual, add product") |
| **Canva Magic Media** | Free tier + $13/mo Pro | Quick social graphics, beginners |
| **Ideogram** | Free tier | Best text-in-images (logos, quotes, carousels) |
| **Stable Diffusion (FLUX variants)** | Free (local) | Infinite generations, LoRAs for faces/products |
| **InternVL-U (4B model)** | Free open-source | Image gen + editing + reasoning in one model |

### Meme Generation Tools

| Tool | Pricing | Best For |
|------|---------|----------|
| **Supermeme.ai** | Free tier + affordable Pro | Text-to-meme, 1000+ templates, multilingual, GIFs |
| **CapCut** | Free | AI meme templates, effects, captions, TikTok/IG export |
| **Viggle AI** | Free tier | Animated/video memes |
| **Imgflip** | Free | Classic meme templates |

### Video Generation Tools (UGC ads, talking-head, product demos)

| Tool | Pricing | Best For |
|------|---------|----------|
| **MakeUGC** | ~$1/video | High-volume UGC ads (hundreds/day) |
| **Arcads AI** | Premium | Ultra-realistic AI UGC ads with consistent characters |
| **HeyGen** | Subscription | Talking-avatar videos, multilingual, 1000+ avatars |
| **Creatify** | Subscription | Product URL → ready UGC ad |
| **Viralco.co** | ~1/10th Arcads price | Autonomous: product link → edited video in inbox daily |
| **LTX-2.3 + Qwen TTS** | Near-zero (local) | Fast customizable talking-head videos |

### Headshot & Realistic Photo Tools

| Tool | Pricing | Best For |
|------|---------|----------|
| **Nano Banana Pro / Gemini** | Free-$20/mo | Consistent characters across scenes |
| **FLUX.2 + ControlNet/IP-Adapter** | Free (local) | Generate realistic variations from reference photo |
| **HeadshotPro** | $39-79 one-time | Professional headshot packs |
| **Canva AI Headshot** | Free | Quick studio-quality headshots |

### Text Overlay & Effects Tools

| Tool | Best For |
|------|----------|
| **Canva** | Easiest — upload → add text, effects, animations |
| **CapCut / Photoroom** | Mobile/web, AI auto-captions |
| **Leonardo AI Canvas** | Edit AI images, add text overlays |
| **Adobe Firefly** | Commercial-safe, generative fill |

### Recommended Pipeline for Amplifier

**Ultra-cheap at scale** (for the user app):
1. **Image**: FLUX.2 locally (near-zero cost) or Nano Banana Pro (free tier)
2. **Video**: LTX + Qwen TTS locally OR MakeUGC at ~$1/video
3. **Memes**: Supermeme.ai API or CapCut
4. **Polish**: Canva API or CapCut for text overlays, branding, effects
5. **Headshots/UGC poses**: FLUX.2 + LoRAs trained on user's photos + product images

**Key principle**: Local-first (FLUX, LTX, Stable Diffusion) for zero marginal cost. Cloud APIs (Nano Banana, Kling, Veo) as premium fallbacks for higher quality.

**IMPORTANT: Do NOT lock in tools now.** The AI image/video landscape changes every 2-3 months. Tools listed above are a snapshot as of March 2026. Before implementing:
1. Re-research the best tools at implementation time — what's cheapest, fastest, highest quality
2. **Build for where models will be in 3-6 months**, not where they are today. Trends:
   - Models are getting dramatically cheaper and faster every quarter
   - On-device inference is coming — some models already run on phones (Gemini Nano, Phi-3, FLUX Schnell quantized)
   - Local GPU inference costs will approach zero as consumer GPUs get better
   - Cloud API costs will drop 5-10x in the next 6 months (competition between Google, OpenAI, Meta, Stability)
3. Design the architecture to be **model-agnostic** — swap providers without changing the content pipeline
4. Prefer models with open weights that can run locally over proprietary APIs

**Implementation approach**:
1. Add media type selection to campaign creation (image, video, meme, carousel)
2. Content generator picks the right tool based on campaign goal + platform
3. Generated media stored locally, attached to drafts before posting
4. Train LoRAs per-user for face/style consistency (one-time, runs locally)
5. Abstract the model layer — pluggable providers so we can swap in better/cheaper models as they emerge

## Social Media Platform APIs for Profile Data

**Status**: Not started
**Why**: Currently scraping profiles via Playwright (brittle, gets blocked). Official APIs provide structured data reliably.

Use official platform APIs (X API v2, LinkedIn API, Reddit API, Facebook Graph API) to access user profile data: posts, engagement metrics, followers, following, content themes, audience demographics. Feed all data to AI for deep user understanding. This replaces or supplements Playwright scraping.

**Benefits**: More data, more reliable, no anti-bot blocks, real-time metrics, audience insights not visible on the page.

**Note**: Most APIs require app review/approval. Some have costs. Evaluate per-platform.

## AI Campaign Quality Gate

**Status**: Not started — needs further discussion
**Why**: Bad campaigns = bad posts = bad user experience. Garbage in, garbage out.

Before a company can activate a campaign, an AI checks it for completeness and quality. The campaign must score 85%+ on a quality rubric:
- Does the brief explain what the product actually is?
- Are there enough details for a creator to write authentic content?
- Are payout rates reasonable for the niche?
- Are must-include items clear and achievable?
- Does the content guidance give useful direction?

Campaigns below 85% get specific feedback ("Add more product details", "Your brief is too vague") and cannot be activated until fixed.

**Open question**: Should this block creation entirely, or just warn? Should the threshold be configurable? Discuss before implementing.

## AI-Powered Profile Scraping with Browser Agents

**Status**: Not started
**Why**: Fixed CSS selector scraping breaks constantly. AI-based browsing is more robust and extracts deeper insights.

Use AI browser agents (like browser-use, or Gemini Vision on screenshots) to explore user social media profiles. The AI navigates the profile like a human — scrolling through posts, reading bios, understanding content themes, extracting engagement patterns. Much deeper understanding than fixed selectors.

**Advantages over current scraping**:
- Robust: no selectors to break when platforms update their UI
- Deeper: AI understands context, tone, audience, not just numbers
- Better anti-detection: AI browsing patterns look more human
- More data: extracts insights that selectors can't (content quality, posting style, audience sentiment)

**Tools to evaluate**: browser-use, Playwright + Gemini Vision, AgentQL, Skyvern, or custom Playwright + LLM pipeline.

## Metrics Accuracy for Billing

**Status**: Not started — critical dependency
**Why**: Earnings and billing HEAVILY depend on accurate metrics. Wrong metrics = wrong payouts = lost trust.

Ensure metric scraping is accurate and reliable:
- Cross-validate scraped metrics against platform analytics (where available)
- Handle edge cases: deleted posts, private accounts, rate-limited scraping
- Consider using official APIs (X API, Reddit API) for metrics instead of scraping
- Add metric sanity checks: flag anomalies (sudden 100x engagement spike = probably fake)
- Audit trail: log every metric scrape with timestamp, source, raw values

**Priority**: Must be rock-solid before scaling. One billing error destroys trust.

## Self-Learning Content Generation

**Status**: Not started
**Why**: Content quality improves over time when the AI learns from results.

The content generation AI should learn and improve:

1. **Learn from others**: Study what competitors, industry leaders, and trending creators post in the same niche. Understand what formats, hooks, and topics get engagement.

2. **Learn from own performance**: Track which posts got high engagement vs low. Identify patterns: which hooks worked, which platforms performed best, which posting times converted.

3. **Experiment + double down**: Try different content styles (stories, lists, questions, controversial takes). Measure results. Do more of what works, stop doing what doesn't.

4. **Trend awareness**: Monitor social/political/cultural trends and incorporate relevant ones into content. Timely content outperforms evergreen content.

**Implementation**: Store post performance data in `agent_content_insights` table (already exists). Build a feedback loop: generate → post → measure → learn → generate better.

## 4-Phase AI Content Agent (MAJOR REBUILD)

**Status**: Not started — requirements fully defined in Task #23
**Priority**: Critical — this is the core value Amplifier delivers to companies

Replace the current single-prompt content generator with a sophisticated 4-phase AI agent system.

### Phase 1 — Research (weekly per campaign)
- Deep-dive into the product using ALL campaign sources (brief, scraped URLs, uploaded files, images)
- Competitor research: what are competitors posting? What content formats work in this niche?
- Trend research: what's trending in this niche/industry right now?
- Image intelligence: analyze campaign images via vision API (Gemini Vision), understand what each shows
- Results cached and reused daily, refreshed weekly

### Phase 2 — Strategy (per campaign, refreshed weekly)
Campaign goal drives everything:
- **LEADS**: links to product, strong CTAs, landing page mentions, conversion-focused
- **VIRALITY**: emotionally triggering, images/videos, high posting frequency, shareable hooks
- **BRAND AWARENESS**: natural product mentions, lifestyle content, consistent presence
- **ENGAGEMENT**: questions, polls, controversial takes, discussion starters

Decides per-platform: post type (text/image/video), posting frequency, tone, scheduling.

### Phase 3 — Content Creation (daily)
- Platform-native UGC that looks REAL (not polished marketing)
- Hooks: emotional triggers, curiosity gaps, contrarian takes, real-life scenarios, stories
- Imperfect language (casual, not corporate-perfect)
- Each platform has its own style (X: punchy, LinkedIn: story, Reddit: genuine, Facebook: conversational)
- NOT compulsory to use all assets/hashtags in every draft
- Images matched to posts by content relevance (not blindly attached)
- Content types: text-only, image-only, image+text

### Phase 4 — Review (per draft)
- Semi-auto: drafts shown to user with per-campaign desktop notification
- Full-auto: auto-approved and scheduled immediately

### Build vs Buy Decision
**IMPORTANT**: Before building a custom 4-phase agent, research existing AI tools/frameworks/products that could handle this:
- **AI content platforms**: Jasper, Copy.ai, Lately.ai, Predis.ai — do they have APIs that could be integrated?
- **AI agent frameworks**: CrewAI, AutoGen, LangGraph, Composio — could these orchestrate the 4 phases?
- **Social media AI tools**: FeedHive, Publer, ContentStudio — do they offer white-label or API access?

The goal is **leverage** — if an existing tool does 80% of what we need, integrate it rather than building from scratch. However, if no tool fits (most are designed for single users, not a marketplace), build a custom agent using the Gemini/Mistral/Groq APIs with the 4-phase architecture.

**Evaluate criteria**: cost per generation, quality of output, platform-native formatting, API availability, customizability, supports campaign-goal-driven content.

### Technical Architecture (if building custom)
```
ContentAgent
├── ResearchPhase (weekly)
│   ├── product_deep_dive(campaign) → product_knowledge
│   ├── competitor_scan(niche) → competitor_insights
│   ├── trend_scan(niche) → trending_topics
│   └── image_analysis(images) → image_descriptions
├── StrategyPhase (weekly, uses research)
│   ├── goal_strategy(campaign_goal) → content_strategy
│   ├── platform_plan(platforms) → per_platform_config
│   └── scheduling_plan(region, platforms) → posting_schedule
├── CreationPhase (daily, uses strategy + research)
│   ├── generate_drafts(strategy, research) → drafts[]
│   ├── match_images(drafts, images) → drafts_with_images[]
│   └── quality_check(drafts) → filtered_drafts[]
└── ReviewPhase (per draft)
    ├── semi_auto → show to user, notify
    └── full_auto → approve + schedule
```

## Free and Paid Tiers

**Status**: Not started
**Why**: Amplifier needs a sustainable business model. Free tier drives adoption, paid tier drives revenue.

Design a tiered pricing model for amplifiers (users):

**Free Tier** (default):
- Limited number of active campaigns (e.g., 1-2)
- Basic content generation (text-only, standard AI models)
- Standard posting frequency
- Basic metrics dashboard
- Community support

**Paid Tier** (subscription or per-feature):
- Unlimited active campaigns (or higher cap)
- Advanced content generation (image+text, video, AI image gen via FLUX)
- Higher posting frequency
- Priority campaign matching (higher visibility to companies)
- Advanced analytics and insights
- Faster metric scraping intervals
- Priority support

**Implementation considerations**:
- Tier stored on user model (server-side)
- Feature gates checked at: campaign acceptance, content generation, posting frequency
- Stripe subscription for paid tier (monthly billing)
- Free tier must be genuinely useful — not crippled. Users should earn real money on free tier.
- Paid tier unlocks scale and premium features, not basic functionality
- Companies may also have tiers (more campaigns, higher budgets, priority matching)
