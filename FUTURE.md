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

## AI Image & Video Generation for UGC

**Status**: Not started
**Why deferred**: Current content generation is text-only. Adding image/video gen is a separate feature layer.

**Goal**: Amplifiers should be able to generate UGC images and videos for their posts — product shots, short-form video, branded visuals — across different platforms (Instagram needs square images, TikTok needs vertical video, etc.).

**Options to evaluate**:
- **Flux 1.0 (STRONG CANDIDATE)** (https://vast.ai/model/flux.1-dev) — high-quality image gen on vast.ai GPU rental. Ultra cheap: ~$0.20-0.30/hour. Produces high-quality content at minimal cost to users. Best balance of quality and price.
- **DALL-E** — OpenAI API, simple but costs per image
- **Nano/Banano** — lightweight models
- **Seedance** — video generation
- **Local LLM on user's desktop** — no cost to amplifier, runs on their GPU. Best option if hardware supports it.

**Pricing model**: Either charge amplifiers a very small fee per generation OR run a local model on their machine for free. Flux 1.0 on vast.ai is the leading option — ultra cheap ($0.20-0.30/hr) with high quality output. Local-first is preferred to keep user costs near zero.

**To implement**:
1. Evaluate which models run locally on consumer GPUs (8GB+ VRAM)
2. Add image/video gen step to the content generation pipeline
3. Platform-specific formats: square for Instagram, vertical for TikTok/Reels, landscape for LinkedIn/Facebook
4. Store generated media in local storage, attach to drafts before posting

## Platform-Specific Content Formats

**Status**: Not started
**Why deferred**: Current posting only supports basic text + single image per platform. Each platform has unique content formats that drive higher engagement.

**Formats to add**:
- **LinkedIn**: Document/carousel uploads (PDF slides), polls, articles
- **X (Twitter)**: Threads (multi-tweet), polls, quote tweets
- **Reddit**: Link posts vs text posts, polls, cross-posting to multiple subreddits
- **Facebook**: Photo albums, polls, events, stories
- **Instagram**: Carousels (multiple images), Reels (short video), Stories
- **TikTok**: Duets, stitches, slideshows

**To implement**:
1. Update content generator to produce format-specific content (e.g., thread = array of tweets, carousel = array of slides)
2. Update `post.py` platform functions to handle each format's upload flow
3. Add format selection to campaign wizard (company can specify preferred formats)
4. AI should pick the best format per platform based on the content and campaign goal
