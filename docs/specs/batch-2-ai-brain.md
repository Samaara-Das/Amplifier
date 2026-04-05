# Batch 2: AI Brain Specifications

**Tasks:** #13 (AI profile scraping), #12 (AI matching), #14 (content agent), #15 (quality gate)

These four features form Amplifier's intelligence layer. Profile scraping feeds matching which feeds content generation. The quality gate ensures campaigns are worth generating content for.

---

## Task #13 — AI Profile Scraping (Per-Platform Detailed Spec)

### What It Does

When a user connects a social media platform, Amplifier scrapes their profile to understand who they are — their niche, audience, posting style, and engagement. This data feeds into:
1. **Matching** — determines which campaigns fit this user
2. **Content generation** — adapts content to the user's voice and audience
3. **User dashboard** — shows the user their own profile stats

### How It Works

1. User connects a platform (Playwright opens browser, user logs in manually)
2. After browser closes, the profile scraper navigates to the user's profile page
3. Takes a full-page screenshot
4. Sends screenshot to Gemini 2.0 Flash Vision API with a platform-specific extraction prompt
5. Parses the structured JSON response
6. Stores the result in `scraped_profile` table (local) and syncs to server `User.scraped_profiles` JSONB

### AI Provider

**Gemini 2.0 Flash** (free tier). ~4 API calls per full scrape (one per platform). Negligible cost.

Fallback: if Gemini API key is not set or call fails, fall back to existing CSS selector-based scraping.

### Per-Platform Data Extraction

The AI must be told specifically what to look for on each platform. Each platform's UI is different and shows different data.

#### X (Twitter)

**Navigate to:** User's profile page (`https://x.com/{username}`)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Large bold text at top | "Mia The mystery girl" |
| Username/handle | Below display name with @ | "@GirlMia9079" |
| Bio | Text below username | "Content creator, dog lover..." |
| Follower count | "Followers" link in profile header | 45.2K |
| Following count | "Following" link in profile header | 892 |
| Post count | Shown in profile header or tab | "3,421 posts" |
| Location | Below bio (if set) | "Los Angeles, CA" |
| Website | Below bio (if set) | "linktr.ee/mia" |
| Join date | Below bio | "Joined March 2019" |
| Verified badge | Blue checkmark next to name | true/false |
| Banner image | Top of profile | URL or description |
| Profile picture | Circular image | URL or description |
| Recent posts (up to 10) | Cards below profile header, each with: |
| - Post text | Main text of the tweet | "When the dog ate the..." |
| - Likes | Heart icon with count | 2,600 |
| - Comments | Speech bubble icon with count | 25 |
| - Reposts | Arrow icon with count | 300 |
| - Views | Bar chart icon with count | 149K |
| - Posted at | Timestamp on tweet | "16h" or "Apr 3" |
| - Has image/video | Whether tweet has media | true/false |

**AI-inferred fields (not directly visible but deducible):**
| Field | How AI infers it |
|-------|-----------------|
| Posting frequency | Count posts with timestamps, estimate posts/day |
| Content niches (1-5) | Classify from bio + post topics (e.g., "entertainment", "animals", "humor") |
| Content quality | low/medium/high based on engagement rates relative to follower count |
| Audience demographics | Estimate from content type, language, engagement patterns |
| Engagement rate | (avg likes + comments + reposts) / followers |

#### LinkedIn

**Navigate to:** User's profile page (`https://www.linkedin.com/in/{username}/`)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Large text at top | "Savita Pareek" |
| Headline | Below name (used as bio) | "Postdoctoral Associate (MIT Sloan)" |
| About section | "About" section below header | Full text |
| Follower count | Near profile photo or connections | "500+ connections" |
| Connection count | Near follower count | "500+" |
| Location | Below headline | "Cambridge, Massachusetts" |
| Profile picture | Circular photo | URL or description |
| Banner image | Background photo | URL or description |
| Experience (up to 5) | "Experience" section | |
| - Job title | Bold text per entry | "Postdoctoral Associate" |
| - Company | Below job title | "MIT Sloan School of Management" |
| - Duration | Date range | "2024 - Present" |
| Education (up to 3) | "Education" section | |
| - School | Bold text | "Indian Institute of Technology, Bombay" |
| - Degree | Below school | "PhD, Statistics" |
| Skills (up to 10) | "Skills" section | ["Machine Learning", "R", "Python"] |
| Recent posts (up to 5) | "Activity" section or feed | |
| - Post text | Content of the post | "Grateful to return to..." |
| - Reactions count | Number next to reaction icons | 293 |
| - Comments count | "X comments" text | 10 |
| - Reposts count | "X reposts" text | 1 |
| - Posted at | Timestamp | "7h" |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | Estimate from visible post timestamps |
| Content niches | From headline + about + post topics (e.g., "ai", "education", "technology") |
| Content quality | Based on engagement relative to connection count |
| Industry | From experience entries |
| Seniority level | From job titles (junior, mid, senior, executive) |

#### Facebook

**Navigate to:** User's profile page (`https://www.facebook.com/me`)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Large text at top | "Manjuz Editz" |
| Bio/intro | "Intro" section on profile | Short text |
| Friends count | Profile header or About section | "1,234 friends" |
| Follower count | If separate from friends | "5,678 followers" |
| Location (current city) | Intro section | "Lives in San Francisco" |
| Hometown | Intro section | "From New York" |
| Workplace | Intro section | "Works at Google" |
| Education | Intro section | "Studied at MIT" |
| Relationship status | Intro section | "Married" |
| Profile picture | Circular photo | URL or description |
| Cover photo | Banner at top | URL or description |
| Recent posts (up to 5) | Timeline below profile | |
| - Post text | Content | "..." |
| - Likes count | Number next to thumbs-up | 3,900 |
| - Comments count | "X comments" text | 133 |
| - Shares count | "X shares" text | 103 |
| - Posted at | Timestamp | "April 3 at 10:07 PM" |
| - Has image/video | Whether post has media | true/false |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | From post timestamps |
| Content niches | From post topics, bio, workplace |
| Content quality | Engagement relative to friends/followers |
| Privacy level | How much profile info is visible |

#### Reddit

**Navigate to:** User's profile page (`https://www.reddit.com/user/{username}/`)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Username | Profile header | "u/some_user" |
| Display name | If set (optional on Reddit) | "Some User" |
| Bio | Below username (if set) | "Trader, coder, coffee addict" |
| Post karma | Profile stats | 15,234 |
| Comment karma | Profile stats | 48,921 |
| Total karma | Combined | 64,155 |
| Cake day (account age) | Profile stats | "October 15, 2018" |
| Follower count | If visible | 234 |
| Profile picture | Avatar image | URL or description |
| Banner image | If set | URL or description |
| Active subreddits | From recent posts | ["r/wallstreetbets", "r/stocks", "r/daytrading"] |
| Recent posts (up to 10) | Listed on profile | |
| - Title | Post title | "My honest take on..." |
| - Subreddit | Where posted | "r/Daytrading" |
| - Score (upvotes) | Number next to arrows | 756 |
| - Comments | Comment count | 20 |
| - Posted at | Timestamp | "1 day ago" |
| - Post type | Text, image, link, video | "image" |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | From post timestamps |
| Content niches | From subreddits + post topics |
| Content quality | Score-to-subreddit-average ratio |
| Community reputation | Karma + account age |
| Top subreddits | Ranked by post frequency |

### Navigation Strategy

The AI scraper should take **multiple screenshots** if needed to capture all data:

1. **Screenshot 1:** Profile header (name, bio, stats, follower counts)
2. **Screenshot 2:** Scroll down to see recent posts with engagement metrics
3. **For LinkedIn only:** Navigate to "About" section and "Experience" section if not visible on main profile

Implementation: after the initial screenshot, scroll down 1-2 viewport heights, take another screenshot. Send both to Gemini Vision and ask it to merge the data.

### Output Schema

All platforms return the same normalized schema:

```json
{
  "platform": "x",
  "display_name": "Mia The mystery girl",
  "username": "GirlMia9079",
  "bio": "Content creator, dog lover...",
  "follower_count": 45200,
  "following_count": 892,
  "post_count": 3421,
  "location": "Los Angeles, CA",
  "website": "linktr.ee/mia",
  "join_date": "March 2019",
  "verified": false,
  "recent_posts": [
    {
      "text": "When the dog ate the...",
      "likes": 2600,
      "comments": 25,
      "reposts": 300,
      "views": 149000,
      "posted_at": "2026-04-04",
      "subreddit": null,
      "has_media": true
    }
  ],
  "posting_frequency": 2.5,
  "profile_data": {
    "about": "Full about section text...",
    "experience": [{"title": "...", "company": "...", "duration": "..."}],
    "education": [{"school": "...", "degree": "..."}],
    "skills": ["Python", "ML"],
    "karma": null,
    "reddit_age": null,
    "active_subreddits": null,
    "personal_details": {"location": "...", "hometown": "...", "workplace": "..."}
  },
  "ai_detected_niches": ["entertainment", "animals", "humor"],
  "content_quality": "high",
  "audience_demographics_estimate": {
    "age_range": "18-34",
    "interests": ["entertainment", "pets", "memes"]
  },
  "engagement_rate": 0.065
}
```

### Verification

1. Connect X in Playwright. Profile scraper runs. Check `scraped_profile` table: `follower_count > 0`, `display_name` not null, at least 3 `recent_posts` with engagement.
2. Disconnect Gemini key. Scraper falls back to CSS selectors. Still returns data (less rich but functional).
3. Connect LinkedIn. Check: `profile_data.experience` has at least 1 entry, `headline` in bio.
4. Connect Reddit. Check: `karma > 0`, `active_subreddits` has entries, posts have scores.
5. Sync to server. `GET /api/users/me` returns `scraped_profiles` with all 4 platforms.

---

## Task #12 — AI Matching (Detailed Scoring Spec)

### What It Does

When a user polls for campaigns (`GET /api/campaigns/mine`), the server matches them against active campaigns. Matching has two stages:
1. **Hard filters** — pass/fail checks (platforms connected, min followers, region, budget, max users)
2. **AI scoring** — Gemini rates the fit 0-100 based on profile data

### Hard Filters (unchanged — already working)

| Filter | Logic |
|--------|-------|
| Required platforms | User has at least 1 of the campaign's required platforms |
| Min followers | Per-platform follower minimums met |
| Target regions | User's region matches campaign targets |
| Min engagement | User's avg engagement rate meets minimum |
| Max users | Campaign hasn't reached its user cap |
| Budget remaining | Campaign has money left |
| Not already assigned | User doesn't already have this campaign |
| Tier campaign limit | User hasn't hit their tier's max active campaigns |

### AI Scoring — What Needs Improvement

The current prompt is decent but has gaps. Here's what the improved scoring should consider:

#### Scoring Criteria (weighted)

| Criterion | Weight | What AI evaluates |
|-----------|--------|-------------------|
| **Topic relevance** | 40% | Do the user's posts, bio, and niches relate to the campaign's product/niche? A finance creator is a great match for a trading indicator campaign. A food blogger is not. |
| **Audience fit** | 25% | Would the user's followers care about this product? A tech-savvy audience cares about AI tools. A fitness audience doesn't. Use the user's engagement patterns and niche to infer audience interests. |
| **Authenticity fit** | 20% | Would promoting this product feel natural for this creator? A user who posts about cooking recommending a kitchen gadget feels natural. The same user recommending enterprise software feels forced. |
| **Content quality** | 15% | Does the user produce content that would represent the brand well? Look at writing quality, engagement rates, consistency. Low-effort reposts vs original thoughtful content. |

#### What the AI Sees

The prompt provides:
- Full campaign brief (title, brief, content guidance, target niches, target regions)
- Full user profile per platform (from scraping):
  - Display name, bio, followers, following, posting frequency
  - Up to 8 recent posts with full engagement metrics
  - Extended profile (about section, experience, education, skills)
  - AI-detected niches, content quality assessment, audience demographics
- User's self-selected niches and connected platforms

#### Scoring Scale

| Score | Meaning | Action |
|-------|---------|--------|
| 80-100 | Strong fit — creator's content aligns closely with campaign | Invite with priority |
| 60-79 | Good fit — reasonable overlap, promotion would feel natural | Invite |
| 40-59 | Possible fit — some relevance but not obvious | Invite (low priority) |
| 20-39 | Weak fit — minimal overlap | Skip |
| 0-19 | No fit — completely unrelated | Skip |

Minimum score to create an invitation: **40** (changed from 0 — no point inviting users with zero relevance).

#### Prompt Improvements

The current prompt says "DO NOT penalize for low follower counts" which is correct. Additional instructions to add:

1. **Brand safety check:** If the user's recent posts contain controversial, offensive, or politically divisive content, score lower (20-40 range) even if topic is relevant. Companies don't want their brand associated with controversy.

2. **Engagement quality check:** 10 likes from real people is better than 1000 likes from bots. If engagement patterns look unnatural (very high likes but zero comments), note it but don't hard-reject.

3. **Cross-platform consistency:** If a user posts about finance on X but food on LinkedIn, the score should reflect which platform(s) are relevant to the campaign, not average across all.

4. **Niche specificity:** A user who posts exclusively about "day trading" is a BETTER match for a trading indicator campaign than a user who posts about "finance" broadly. Reward niche depth over breadth.

#### Fallback (when AI fails)

If all Gemini models fail, use niche overlap scoring:
- Each overlapping niche between user and campaign = +25 points
- No niche targeting on campaign = base score of 50
- Minimum score: 10

#### Caching

- Cache key: `(campaign_id, user_id)`
- TTL: 24 hours
- Invalidated on: campaign edit, user profile refresh

### Verification

1. User with finance niche, recent posts about trading. Campaign for trading indicator. Expect: score > 75.
2. User with cooking niche, recent posts about recipes. Same trading campaign. Expect: score < 30.
3. User posts about finance on X but food on Facebook. Campaign requires X. Expect: score reflects X content (>70), not Facebook content.
4. Gemini fails. Expect: fallback niche overlap scoring, no crash.
5. Same user + campaign scored twice within 24h. Expect: second call uses cache (no API call).

---

## Task #14 — 4-Phase Content Agent (Detailed Spec)

### What It Does

Generates campaign content across 4 platforms that feels like a real person recommending a product. The content should be platform-native, goal-driven, and adapt over time.

### The 4 Phases

#### Phase 1: Research (runs weekly per campaign, cached)

**Purpose:** Understand the product deeply so content is specific and credible, not generic.

**What it does:**
1. Scrape company URLs from campaign `assets.company_urls` (up to 3 URLs via webcrawler CLI)
2. Extract: product name, features, benefits, pricing, testimonials, competitors
3. Analyze campaign images (if any) via Gemini Vision — what does the product look like?
4. Synthesize into a structured research context

**Research output:**
```json
{
  "product_summary": "1-2 sentence description of what the product is",
  "key_features": ["feature 1", "feature 2", "feature 3"],
  "target_audience": "who benefits from this product",
  "competitive_angle": "what makes this different from alternatives",
  "content_angles": ["angle 1", "angle 2", "angle 3", "angle 4", "angle 5"],
  "emotional_hooks": ["emotional trigger 1", "trigger 2", "trigger 3"],
  "pricing_info": "if found on the website",
  "testimonials": ["quote 1", "quote 2"]
}
```

**Cached in:** `agent_research` table. Refreshed weekly or when campaign brief changes.

#### Phase 2: Strategy (built per campaign, refreshed weekly)

**Purpose:** Determine WHAT to post, WHEN to post, and HOW to post based on the campaign goal.

**Strategy is driven by `campaign_goal`:**

| Goal | Content Focus | Tone | CTA Style |
|------|--------------|------|-----------|
| **brand_awareness** | Lifestyle association, consistent presence, "I use this" | Natural, storytelling | Mention product naturally, no hard sell |
| **leads** | Problem-solution, product links, conversion hooks | Direct, benefit-focused | Link in bio, "check it out", clear CTA |
| **virality** | Emotional triggers, surprising content, shareable | Bold, provocative, edgy | "Share if you agree", "Tag someone who needs this" |
| **engagement** | Questions, polls, discussion starters, hot takes | Conversational, opinionated | "What do you think?", "Reply below" |

**Strategy also determines per-platform:**
- Posts per day (fractional: 0.5 = every other day)
- What time to post (EST, US audience aligned)
- Whether to include an image (probability 0-1)
- Preferred hook types (from content_angles)

**The strategy is NOT just a static dict.** It should use the AI to reason about the BEST approach given:
- The campaign goal and tone
- The research context (what's the product, who's the audience)
- The user's profile (what tone does this user typically post in)
- Past performance data (if available — which hooks worked best)

**Strategy prompt to AI:**
```
Given this campaign (goal: {goal}, tone: {tone}, product: {product_summary})
and this creator (niches: {niches}, typical tone: {typical_tone}, 
engagement rate: {engagement_rate}):

1. What content angles will resonate with this creator's audience?
2. How many posts per day per platform? (X can handle 2-3, LinkedIn 1, Reddit <1)
3. Should posts include images? (depends on the product and platform)
4. What hook styles should we use? (question, story, stat, contrarian, etc.)
5. What time of day works best for this creator's audience region?

Return a JSON strategy plan.
```

#### Phase 3: Creation (runs daily)

**Purpose:** Generate actual post content for each platform following the strategy.

**What the creation prompt needs:**
1. Campaign context (title, brief, guidance, research)
2. Strategy for today (which platforms, which hooks, which angles)
3. Previous posts (to avoid repetition — last 8 hooks used)
4. Platform-specific rules:

| Platform | Rules |
|----------|-------|
| **X** | Max 280 chars. One punchy hook + key benefit. 1-3 hashtags naturally placed. First line must stop the scroll. |
| **LinkedIn** | 500-1500 chars. Story format. First 2 lines visible before "see more" — make them count. End with a question. 3-5 hashtags at bottom. Aggressive line breaks. |
| **Facebook** | 200-800 chars. Conversational, like telling friends. Ask a question for comments. 0-2 hashtags max. |
| **Reddit** | Title: 60-120 chars (descriptive, NOT clickbait). Body: 500-1500 chars. Write like a community member sharing a genuine find. No hashtags, no emojis, no self-promotion tone. Include both positives AND negatives about the product. |

**Anti-AI language rules (critical):**
- NEVER use: "game-changer", "unlock your potential", "leverage", "dive in", "let's explore", "in today's fast-paced world", "synergy", "innovative solution", "cutting-edge"
- Each platform MUST be genuinely different — different angle, different hook, different structure
- Content must feel like a real person, not a brand

**FTC disclosure:** Automatically appended after generation. The AI should NOT include it in the content body.

**Image decision:** If the strategy says to include an image for this platform/post:
- Use campaign product photos (img2img via Gemini) if available
- Otherwise generate from AI image prompt (txt2img)
- If no image needed, skip entirely (text-only post)

#### Phase 4: Review

**Semi-auto mode:** Store drafts in `agent_draft`, notify user, wait for approval.
**Full-auto mode:** Auto-approve and schedule immediately using strategy's posting times.

### Content Quality Checks

Before storing a draft, verify:
1. X content is within 280 chars (after FTC disclosure)
2. Reddit has both title and body
3. No AI-banned phrases are present
4. Content is different from the last 3 days' posts (cosine similarity < 0.8)

### Fallback

If any phase fails, fall back to the existing single-prompt `ContentGenerator.generate()`. This ensures content is always produced, even if the AI pipeline has issues.

### Verification

1. Campaign with `goal=virality`, `tone=edgy`. X content should use contrarian/surprising hooks, not gentle storytelling.
2. Campaign with `goal=leads`. Every post should mention the product and have a CTA.
3. Same campaign, day 1 vs day 5. Content must be genuinely different (different angle, different hook).
4. Reddit post includes both positives and a caveat/negative about the product.
5. X post is under 280 chars including the FTC disclosure.
6. Strategy for brand_awareness generates 1 post/day on X but only every other day on Reddit.
7. Gemini fails. Content falls back to basic generator. No crash, still produces content.

---

## Task #15 — AI Campaign Quality Gate (Detailed Spec)

### What It Does

When a company tries to activate a campaign (change status from `draft` to `active`), the quality gate scores it. Campaigns scoring below 85/100 are blocked with specific feedback on what to fix.

### Why It Matters

Low-quality campaigns waste user time and produce bad content. If a brief says "promote my product" with no details, the content generator has nothing to work with. The quality gate protects users from receiving garbage campaigns AND helps companies create better briefs.

### Scoring Rubric

| Criterion | Weight | Full Score | Partial Score | Zero Score |
|-----------|--------|-----------|---------------|-----------|
| **Brief completeness** | 25 | 300+ chars, mentions product name, features, audience | 100-300 chars | <100 chars or missing key elements |
| **Content guidance** | 15 | 50+ chars with tone, must-include, or examples | 20-50 chars | Empty or <20 chars |
| **Payout rates** | 15 | rate_per_like >= $0.01 AND at least 2 rate types set | 1 rate type set, reasonable amount | All rates $0 or only 1 rate <$0.005 |
| **Targeting** | 10 | At least 1 niche tag AND at least 1 required platform | Partial (niche OR platform) | No targeting at all |
| **Assets provided** | 10 | Product images or company URLs provided | Only company name | No assets at all |
| **Title quality** | 10 | 15-80 chars, descriptive of product/offer | 10-14 or 81-100 chars | <10 chars or >100 chars |
| **Dates valid** | 5 | Start date in future (or today), end after start, duration 7-90 days | Duration 1-6 days or 91-365 days | Start in past, or end before start |
| **Budget sufficient** | 10 | $100+ budget | $50-99 budget | <$50 budget |

**Activation threshold: 85/100**

### Feedback Format

When a campaign fails, return specific, actionable feedback per criterion:

```json
{
  "score": 62,
  "passed": false,
  "feedback": [
    "Brief is too short (89 chars). Describe your product, its key features, and who it's for. Aim for 300+ characters.",
    "No content guidance provided. Add tone instructions (casual/professional), must-include phrases (hashtags, links), or content examples.",
    "No product images or company URLs provided. Add at least one image or website link so creators can see and research your product.",
    "Budget is below recommended minimum. Campaigns under $100 reach fewer creators."
  ],
  "breakdown": {
    "brief_completeness": 5,
    "content_guidance": 0,
    "payout_rates": 12,
    "targeting": 10,
    "assets_provided": 0,
    "title_quality": 10,
    "dates_valid": 5,
    "budget_sufficient": 5
  }
}
```

### When It Runs

1. **On activation attempt** — company clicks "Activate" or changes status to `active`
2. **On campaign detail page** — show current score and feedback as a pre-flight check (informational, not blocking)
3. **After AI wizard generates** — score the wizard output and warn if low

### Special Cases

- **Repost campaigns** (`campaign_type = "repost"`): Don't require content_guidance (company provides the exact content). Do require the repost content to be filled in.
- **Wizard-generated campaigns**: Usually score high (85+) because the wizard produces comprehensive briefs. The gate mainly catches manually-created campaigns with minimal info.

### Verification

1. Campaign with brief "Buy our product" (16 chars), no guidance, no assets, $25 budget. Expect: score < 50, blocked, feedback says "Brief is too short", "No content guidance", "No assets", "Budget below minimum".
2. Campaign created via AI wizard. Expect: score >= 85, passes.
3. Campaign with great brief but $0 payout rates. Expect: score fails on payout rates, feedback says "Set payout rates".
4. Fix the issues from test 1 (lengthen brief, add guidance, add image, increase budget). Re-attempt activation. Expect: passes.
5. Repost campaign with no content_guidance but repost content filled in. Expect: guidance criterion doesn't penalize.
