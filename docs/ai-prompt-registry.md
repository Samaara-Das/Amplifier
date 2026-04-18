# AI Prompt Registry

Every AI prompt used across the Amplifier codebase — where it lives, what model it targets, what it expects back.

---

## 1. Content Generation (Legacy Single-Prompt Fallback)

**Purpose:** Generate per-platform UGC-style social media posts for campaign content. Used as fallback when the 4-phase ContentAgent pipeline fails.

**File:** `scripts/utils/content_generator.py` → `ContentGenerator.generate()`
**Model:** Gemini 2.5-flash → 2.0-flash → 2.5-flash-lite (via AiManager) → Mistral → Groq
**Runs on:** User's device (user's API keys)

**Prompt summary:**
```
You are a UGC creator posting on behalf of a brand campaign. Create content
that feels like a REAL PERSON genuinely recommending a product — not an ad,
not corporate marketing, not influencer cringe.
```

**Inputs injected:**
- Campaign title, brief, content guidance
- Product links/assets, hashtags, brand guidelines
- Must-include / must-avoid phrases
- Previous draft hooks (anti-repetition, last 12)
- Day number (for daily variation)
- Research from scraped company URLs (via webcrawler)

**Expected output (JSON):**
```json
{
  "x": "tweet text (max 280 chars)",
  "linkedin": "post text (500-1500 chars, story format)",
  "facebook": "post text (200-800 chars, conversational)",
  "reddit": {"title": "60-120 chars", "body": "500-1500 chars"},
  "image_prompt": "1 sentence lifestyle image description"
}
```

**Key rules in prompt:**
- No AI voice ("game-changer", "synergy", "dive in", "innovative solution")
- Each platform version must be genuinely different
- Include a minor caveat ("I wish it had X") to sound real
- Reddit: no hashtags, no emojis, no self-promo

---

## 1a. Phase 1 — Research (4-Phase ContentAgent)

**Purpose:** Synthesize deep product knowledge from campaign brief + scraped URLs into a structured research context. Also fetches recent niche news and analyzes product images.

**File:** `scripts/utils/content_agent.py` → `_run_research()`
**Model:** Gemini (text synthesis) + Gemini Search grounding (news) + Gemini Vision (images)
**Runs on:** User's device
**Cache:** 7 days per campaign (stored in `agent_research` table, `research_type="full_research"`)

**Prompt summary (text synthesis):**
```
Analyze this campaign and provide a structured research brief.
CAMPAIGN TITLE / BRIEF / GUIDANCE / GOAL / TONE + scraped URL content
→ Return JSON with: product_summary, key_features, target_audience,
  competitive_angle, content_angles, emotional_hooks, pricing, testimonials
```

**Inputs injected:**
- Campaign title, brief, content guidance, goal, tone
- Up to 3 scraped company URLs (full text via `_scrape_url_deep`)
- Campaign assets (product images for vision analysis)

**Expected output (JSON):**
```json
{
  "product_summary": "1-2 sentence product description",
  "key_features": ["feature 1", "feature 2", "feature 3"],
  "target_audience": "who would benefit",
  "competitive_angle": "what makes it different",
  "content_angles": ["angle 1", "angle 2", "angle 3", "angle 4", "angle 5"],
  "emotional_hooks": ["trigger 1", "trigger 2", "trigger 3"],
  "pricing": "pricing info or empty string",
  "testimonials": ["testimonial 1", "testimonial 2"],
  "recent_niche_news": ["headline 1", "headline 2", "headline 3"],
  "image_analysis": "visual description of product photos"
}
```

**Additional calls:**
- `generate_with_search()` for 3-5 niche news headlines (Gemini grounded, 1 call/week)
- `generate_with_vision()` for product image analysis if local image files present (1 call/week)

---

## 1b. Phase 2 — Strategy Refinement (4-Phase ContentAgent)

**Purpose:** AI refines the base static GOAL_STRATEGY dict based on creator profile, campaign research, and performance insights. Adds creator_voice_notes per platform.

**File:** `scripts/utils/content_agent.py` → `_refine_strategy_with_ai()`
**Model:** Gemini → Mistral → Groq (via AiManager)
**Runs on:** User's device
**Cache:** 7 days per campaign (stored in `agent_research` table, `research_type="strategy"`)

**Prompt summary:**
```
You are a social media strategist for Amplifier.
Given campaign goal, tone, research summary, creator profiles, and base strategy JSON:
→ Refine the base strategy. Output same JSON structure but adapted to creator voice.
→ Add "creator_voice_notes" per platform (1-2 sentences on how to match creator's tone).
```

**Inputs injected:**
- Campaign goal + tone
- Research summary (product_summary, target_audience, top 3 content_angles)
- User profiles (platform, follower_count, bio, style_notes, niches, recent posts — up to 300 chars)
- Base strategy JSON (from GOAL_STRATEGY + performance insights)

**Expected output:** Same JSON structure as base strategy + `creator_voice_notes` field per platform entry.

**Fallback:** If AI call fails or output is invalid, returns base strategy unchanged.

---

## 1c. Phase 3 — Creation (4-Phase ContentAgent)

**Purpose:** Generate actual per-platform post text following the refined strategy. Platform-native, hook-driven, goal-aligned.

**File:** `scripts/utils/content_agent.py` → `_run_creation()`
**Model:** Gemini → Mistral → Groq (via AiManager)
**Runs on:** User's device

**Prompt summary:**
```
You are a UGC creator posting on behalf of a brand campaign...
[Campaign context + Research + Strategy + Platform instructions + Hook style +
 Daily variation + Recent news (if available) + Hard rules]
```

**Inputs injected:**
- All Phase 1 research fields
- Phase 2 refined strategy (goal, tone, content angle, hook, creator_voice_notes per platform)
- Day number + previous hooks (anti-repetition)
- `recent_niche_news` injected as "── RECENT NEWS ──" section (soft instruction to reference if naturally fits)
- Per-platform creator_voice_notes appended to platform instruction lines

**Platform-specific rules in prompt:**
| Platform | Rules |
|---|---|
| X | Max 280 chars, punchy hook + key benefit, 1-3 hashtags |
| LinkedIn | 500-1500 chars, story format, aggressive line breaks, end with question |
| Facebook | 200-800 chars, conversational, ask a question, 0-2 hashtags |
| Reddit | Title 60-120 chars + Body 500-1500 chars, MANDATORY caveat/limitation (non-negotiable for authenticity) |

**Expected output (JSON):** Same as legacy generator. FTC disclosure appended automatically after generation.

**Post-generation validation** (via `content_quality.validate_content()`):
- X ≤ 280 chars (post-FTC)
- Reddit has valid title + body
- No banned phrases (case-insensitive substring)
- Diversity vs last 3 days (cosine < 0.8 via embeddings; SequenceMatcher < 0.85 fallback)
- Retries once with expanded previous_hooks if validation fails; raises RuntimeError if still invalid

---

## 2. Campaign Wizard

**Purpose:** Generate a comprehensive campaign brief from scraped company URLs.

**File:** `server/app/services/campaign_wizard.py` → `run_campaign_wizard()`
**Model:** Gemini 2.5-flash → 2.0-flash → 2.5-flash-lite
**Runs on:** Server (server's Gemini key)

**Prompt summary:**
```
You are a campaign strategist for Amplifier. Generate a COMPREHENSIVE,
DETAILED campaign brief that will be the SOLE source of information for
creators. The brief must contain EVERYTHING a creator needs to write
authentic posts.
```

**Inputs injected:**
- Company product description, features, goal
- Scraped URL content (BFS, up to 10 pages, max 3 URLs)
- Extracted text from uploaded PDFs/DOCXs
- Target niches, regions, platforms

**Expected output (JSON):**
```json
{
  "title": "campaign title (max 60 chars)",
  "brief": "comprehensive brief (500-1000 words)",
  "content_guidance": "creator instructions (200-400 words)",
  "payout_rules": {
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10
  },
  "suggested_budget": 200
}
```

**Payout rate suggestions by niche:**

| Niche | Impressions/1K | Per Like | Per Repost | Per Click |
|---|---|---|---|---|
| High-value (finance, crypto, AI, tech) | $1.00 | $0.02 | $0.10 | $0.15 |
| Engagement (beauty, fashion, fitness) | $0.30 | $0.015 | $0.08 | $0.10 |
| Default | $0.50 | $0.01 | $0.05 | $0.10 |

---

## 3. AI Matching (Relevance Scoring)

**Purpose:** Score how well a user's profile matches a campaign brief (0-100).

**File:** `server/app/services/matching.py` → `ai_score_relevance()`
**Model:** Gemini 2.5-flash → 2.0-flash → 2.5-flash-lite
**Runs on:** Server (server's Gemini key)
**Cache:** 24 hours per (campaign_id, user_id) pair

**Prompt summary:**
```
You are matching creators to brand campaigns on Amplifier. Judge ONLY on:
1. TOPIC RELEVANCE (does their content relate to the campaign?)
2. AUDIENCE FIT (would their connections care about this product?)
3. AUTHENTICITY (would this feel natural or forced?)

Most creators are NORMAL PEOPLE, not influencers. Low followers or
infrequent posting should NOT be penalized.

Return ONLY a number between 0 and 100.
```

**Inputs injected:**
- Campaign: title, brief (1500 chars), content guidance, target niches, target regions
- Creator: self-selected niches, connected platforms, region
- Full scraped profile per platform: bio, followers, following, up to 8 recent posts with full engagement metrics
- Extended fields: LinkedIn experience/education, Reddit karma/communities, Facebook personal details

**Expected output:** Single integer 0-100
- 70-100: Good fit
- 40-69: Possible fit
- 10-39: Weak fit
- 0-9: No fit

**Fallback (when all Gemini models fail):** Niche-overlap scoring: each overlapping niche = +30 points, no targeting = +10 base.

---

## 4. Content Screening

**Purpose:** Check campaign content for safety violations before activation.

**File:** `server/app/services/campaign_wizard.py` → `screen_campaign()`
**Model:** Gemini
**Runs on:** Server

**Prompt summary:**
```
Review this campaign for content safety. Flag any of: violence, hate speech,
explicit content, misinformation, misleading financial claims, health claims.
```

**Inputs:** Campaign brief, content guidance, assets
**Expected output:** `{flagged: bool, flagged_keywords: [], categories: []}`

Flagged campaigns enter the admin review queue (`screening_status: "flagged"`).

---

## 5. Profile Extraction (AI Vision)

**Purpose:** Extract structured profile data from social media pages using text + optional vision.

**File:** `scripts/utils/profile_scraper.py` (AI-enhanced paths)
**Model:** Gemini 2.0-flash (text mode primary, vision fallback)
**Runs on:** User's device (user's Gemini key)

**3-tier extraction pipeline:**

1. **Tier 1 — Text extraction (cheapest):** Extract all visible text from page → send to text AI → parse structured data. Captures 80%+ of profile data. ~500-1500 tokens.

2. **Tier 2 — Targeted element queries (free):** Browser automation queries specific elements (attributes, metadata) that text extraction might miss. 0 tokens.

3. **Tier 3 — Screenshot + Vision (expensive, last resort):** Only if tiers 1+2 miss key fields. Take targeted screenshot of profile header → Gemini Vision. ~3000-5000 tokens.

**Platform-specific hints in prompt:**
- **X:** Look for tweets with likes/retweets/replies/views, followers count
- **LinkedIn:** Connections, work experience, posts with reactions/comments
- **Facebook:** Friends count, bio sections, posts with engagement
- **Reddit:** Karma, cake day, subreddits, upvotes/comments

**Expected output (JSON):**
```json
{
  "display_name": "Name",
  "bio": "bio text",
  "follower_count": 1500,
  "following_count": 200,
  "recent_posts": [
    {"text": "...", "likes": 10, "comments": 2, "reposts": 1, "views": 500}
  ],
  "posting_frequency": 0.5,
  "ai_detected_niches": ["finance", "tech"],
  "content_quality": "medium",
  "profile_data": {"about": "...", "experience": [...]}
}
```

---

## 6. Niche Classification

**Purpose:** Classify a user's content niches from their scraped posts.

**File:** `scripts/utils/niche_classifier.py` → `classify_niches()`
**Model:** Gemini 2.5-flash-lite
**Runs on:** User's device

**Prompt summary:**
```
Based on these social media posts by a single user, classify their content
niches. Choose 1-4 niches from this list ONLY: finance, trading, investing,
crypto, technology, ai, business, marketing, lifestyle, education, health,
fitness, food, travel, entertainment, gaming, sports, fashion, beauty,
parenting, politics
```

**Inputs:** Up to 30 recent posts (text content)
**Expected output:** JSON array: `["finance", "tech"]` (1-4 niches)

---

## 7. Image Generation Prompts

**Purpose:** Generate photorealistic UGC-style images that look like phone photos.

**File:** `scripts/ai/image_prompts.py`
**Models:** Gemini Flash Image (primary) → Cloudflare FLUX.1 → Together FLUX.1 → Pollinations → PIL
**Runs on:** User's device

### txt2img — `build_simple_prompt(base_prompt)`

Enhances a base image prompt with an 8-category UGC photorealism framework:

1. **Realism trigger:** "raw unedited phone photo", "candid snapshot"
2. **Camera:** Random from pool: "iPhone 15 Pro", "Samsung Galaxy S24 Ultra", "Google Pixel 8 Pro"
3. **Lighting:** Random: "natural window light", "warm golden hour", "overcast daylight"
4. **Texture:** "visible skin pores", "natural fabric grain", "real hair texture"
5. **Color:** "slightly muted colors", "natural palette", "warm tones"
6. **Composition:** "slightly off-center framing", "product at natural angle", "cluttered desk"
7. **Quality:** "slight motion blur", "natural bokeh", "very slight tilt"

**Negative prompt (always appended):**
```
stock photo, commercial lighting, studio backdrop, professional model,
perfect skin, symmetrical composition, HDR, oversaturated, AI-generated,
digital art, illustration, 3D render, watermark, text overlay
```

### img2img — `build_img2img_prompt(product_name, scene_description)`

Transforms a campaign product photo into a UGC lifestyle scene:
```
Transform this product photo into a casual, authentic-looking scene.
Make it look like someone took this photo with their phone while using
the product in their daily life. [scene_description]. Keep the product
recognizable but make everything else look natural and lived-in.
```

### Post-processing pipeline (`scripts/ai/image_postprocess.py`)

Applied to ALL generated images regardless of provider:

| Step | Effect | Parameter |
|---|---|---|
| Desaturation | Reduce color vibrancy | 13% reduction |
| Color cast | Subtle warm/cool tint | Random warm or cool |
| Film grain | Gaussian noise overlay | sigma=8 |
| Vignetting | Darkened edges | 25% |
| JPEG compression | Lossy re-encode | quality=80 |
| EXIF injection | Fake phone camera metadata | Random: iPhone/Samsung/Pixel, GPS coords, timestamp |

---

## Summary

| Prompt | File | Model | Runs On | Tokens/Call |
|---|---|---|---|---|
| Content generation (fallback) | content_generator.py | Gemini/Mistral/Groq | User device | ~2000-4000 |
| Phase 1 — Research | content_agent.py `_run_research` | Gemini | User device | ~1500-3000 |
| Phase 1 — Niche news | content_agent.py `_run_research` | Gemini (search grounded) | User device | ~500-1000 |
| Phase 1 — Image analysis | content_agent.py `_run_research` | Gemini Vision | User device | ~500-1000 |
| Phase 2 — Strategy refinement | content_agent.py `_refine_strategy_with_ai` | Gemini/Mistral/Groq | User device | ~1000-2000 |
| Phase 3 — Creation | content_agent.py `_run_creation` | Gemini/Mistral/Groq | User device | ~2000-4000 |
| Campaign wizard | campaign_wizard.py | Gemini | Server | ~3000-5000 |
| AI matching | matching.py | Gemini | Server | ~1500-3000 |
| Content screening | campaign_wizard.py | Gemini | Server | ~1000-2000 |
| Profile extraction | profile_scraper.py | Gemini | User device | ~500-5000 |
| Niche classification | niche_classifier.py | Gemini | User device | ~500-1000 |
| Image prompts | image_prompts.py | Various | User device | N/A (image gen) |
