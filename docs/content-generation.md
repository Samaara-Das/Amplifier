# Amplifier -- Content Generation Pipeline

**File:** `scripts/utils/content_generator.py`

## Overview

Content generation creates UGC-style posts for campaigns across platforms. Uses free AI APIs with a fallback chain.

## AI Provider Fallback Chain

### Text Generation (AiManager -- `scripts/ai/manager.py`)
| Order | Provider | Model | Free Tier |
|-------|----------|-------|-----------|
| 1 | Gemini | gemini-2.5-flash > 2.0-flash > 2.5-flash-lite | 20 req/day/model = 60/day |
| 2 | Mistral | mistral-small-latest | Free tier available |
| 3 | Groq | llama-3.3-70b-versatile | Free tier available |

Rate limit handling: on 429/RESOURCE_EXHAUSTED, skips to next model/provider.

### Image Generation (ImageManager -- `scripts/ai/image_manager.py`)

Three generation modes:
- **txt2img**: Generate an image from an AI-written prompt (default when no product photo is available)
- **img2img**: Transform a campaign product photo into a UGC-style scene via Gemini (preferred when product photos exist)
- **txt2txt**: Text-only generation (no image) -- used when image generation is disabled or all providers fail

| Order | Provider | Model | Notes |
|-------|----------|-------|-------|
| 1 | **Gemini Flash Image** | gemini-2.0-flash-exp (imagen) | **PRIMARY**. 500 free/day. Supports img2img. |
| 2 | Cloudflare Workers AI | FLUX-1-schnell | Requires CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN |
| 3 | Together AI | FLUX.1-schnell-Free | Requires TOGETHER_API_KEY |
| 4 | Pollinations | turbo | No key required, 90s timeout |
| 5 | PIL template | N/A | Dark background + white text fallback (always available) |

### UGC Post-Processing Pipeline (`scripts/ai/image_postprocess.py`)

All generated images pass through a post-processing pipeline that makes them look like real phone photos rather than AI-generated:

1. **Desaturation** -- slight reduction in color vibrancy
2. **Color cast** -- subtle warm/cool tint
3. **Film grain** -- noise layer for analog feel
4. **Vignetting** -- darkened edges
5. **JPEG compression** -- lossy re-encode to match phone camera output
6. **EXIF injection** -- fake camera metadata (model, GPS, timestamp)

### img2img Workflow (Campaign Product Photos)

When a campaign includes product images in `assets.image_urls`:

1. Background agent downloads ALL product images from the campaign
2. `_pick_daily_image()` rotates through the product photo list based on `day_number` (deterministic daily rotation)
3. Gemini img2img transforms the product photo into a UGC-style scene using an 8-category photorealism prompt framework
4. Post-processing pipeline runs on the result
5. `agent_draft.image_path` stores the local path to the generated image
6. When scheduled, `_schedule_draft()` passes `image_path` through to `post_schedule`

Fallback: if no product photos exist or img2img fails, falls back to txt2img using the AI-generated `image_prompt`.

## The Content Generation Prompt

```
You are a UGC creator posting on behalf of a brand campaign. Create content
that feels like a REAL PERSON genuinely recommending a product -- not an ad,
not corporate marketing, not influencer cringe.

CAMPAIGN:
Title, Brief, Content Guidance, Product Links/Assets

HOOK (first 1-2 sentences) -- must stop the scroll:
- Problem-solution: "I used to [problem]. Then I found [product]."
- Surprising result: "I didn't expect [product] to actually [benefit]..."
- Social proof: "Everyone's been talking about [product]..."
- Curiosity gap: "There's a reason [claim] -- most people don't know..."
- Contrarian: "Unpopular opinion: [common belief] is wrong..."

BODY:
- Share specific, personal-feeling experience
- 1-2 concrete features/benefits from campaign brief
- Include a minor caveat ("I wish it had X") to sound real
- Natural call-to-action (not salesy)
- Simple, conversational language

HARD RULES:
- NEVER sound like AI (no "game-changer", "unlock potential", "leverage",
  "dive in", "let's explore", "synergy", "innovative solution", "cutting-edge",
  "In today's fast-paced world")
- Each platform version must be GENUINELY DIFFERENT
- Must-include phrases woven naturally (not forced into every post)
- Must-avoid items never appear
```

## Per-Platform Output Formats

| Platform | Format | Specs |
|----------|--------|-------|
| **X** | Tweet | Max 280 chars. One punchy hook + key benefit. 1-3 hashtags naturally placed. |
| **LinkedIn** | Story post | 500-1500 chars. Personal experience format. Aggressive line breaks (first 2 lines = all people see before "see more"). Ends with question. 3-5 hashtags at end. |
| **Facebook** | Conversational | 200-800 chars. Like telling friends. Ask question for comments. 0-2 hashtags. |
| **Reddit** | Title + body | Title: 60-120 chars (descriptive, NOT clickbait). Body: 500-1500 chars. Community member sharing a genuine find. No hashtags, no emojis, no self-promo. Include what you liked AND didn't. |
| **image_prompt** | Description | 1 sentence. Vivid, lifestyle-oriented, scroll-stopping. |

## Research Phase (Webcrawler Integration)

Before generating content, the generator can deep-research campaign URLs:

1. Extract URLs from campaign `assets.company_urls`
2. Limit to max 3 unique URLs
3. Call webcrawler: `python C:/Users/dassa/Work/webcrawler/crawl.py --json fetch {url}` (hardcoded path in `WEBCRAWLER_PATH`)
4. Build research brief from scraped content (max 3000 chars total)
5. Inject into prompt as `"RESEARCH (scraped from company URLs)"`

Per-URL data: page title, URL, OG description, first 800 chars of content.

Fallback: if no URLs or all scrapes fail, generates without research.

## Daily Variation

When `day_number > 1`, injects into prompt:
```
This is day {N} of this campaign. You MUST write completely fresh content.
Previous posts started with:
  - {hook1}
  - {hook2}
Write something COMPLETELY DIFFERENT. Different angle, hook, structure.
Do NOT repeat or rephrase any of the above openings.
```

## Content Sources (from Campaign)

The AI uses ALL available sources:
1. **Product descriptions**: name, description, features, brief, content guidance
2. **Deep-scraped knowledge**: full site content from BFS crawling company URLs
3. **Uploaded files**: extracted text from PDFs/DOCXs the company uploaded
4. **Product images**: company-uploaded images (referenced in posts)
5. **Must-include**: hashtags, phrases, links -- woven naturally where relevant (NOT every post)
6. **Must-avoid**: topics, phrases, claims -- never appear in any post

## Free API Credit Management

Content generation must stay within free-tier limits:
- Gemini: 3 models with separate quotas = ~60 requests/day
- Mistral + Groq: additional free-tier capacity
- When one provider's quota is exhausted, automatically falls back to next
- Design: pipeline stays within free-tier limits for daily use

## Draft Lifecycle

```
Generated -> stored in agent_draft (local SQLite)
                |
    Semi-auto: user reviews/edits/approves
    Full-auto: auto-approved immediately
                |
    Approved -> scheduled in post_schedule
                |
    Posted -> URL captured -> synced to server
```

## JSON Response Parsing

AI responses are parsed:
1. Strip whitespace
2. Remove markdown code fences (`\`\`\`json ... \`\`\``)
3. `json.loads()` on cleaned text
4. Fallback: regex search for `{...}` JSON object pattern
5. Raises ValueError if no valid JSON found
