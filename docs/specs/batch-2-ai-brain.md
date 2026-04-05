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

1. User connects a platform (browser opens, user logs in manually)
2. After browser closes, the profile scraper navigates to the user's profile page
3. Extracts profile data using the 3-tier pipeline (text first, element queries second, screenshot last resort)
4. Stores the result locally and syncs to the server

### API Key Ownership

All AI operations on the user app use the **user's own API keys** (entered during onboarding). This includes profile scraping, content generation, and image generation. The server uses its own keys for matching and the campaign wizard.

| Operation | Runs on | API key |
|-----------|---------|---------|
| Profile scraping | User app | User's Gemini key |
| Content generation | User app | User's Gemini/Mistral/Groq |
| Image generation | User app | User's Gemini/Cloudflare/Together |
| Campaign matching | Server | Server's Gemini key |
| Campaign wizard | Server | Server's Gemini key |
| Quality gate | Server | No AI needed |

### Token-Efficient Extraction (3-Tier Pipeline)

Screenshots are expensive (~5000+ vision tokens per image). Use a smarter approach that minimizes token usage:

**Tier 1 — Text extraction (cheapest, try first):**
Extract all visible text from the page and send it to a text AI model (not vision). This captures 80%+ of profile data — follower counts, bio, post text, engagement numbers are all in the page text. Cost: ~500-1500 tokens per platform.

**Tier 2 — Targeted element queries (free, supplement tier 1):**
Use browser automation to query specific structured elements that text extraction might miss (e.g., score attributes, hidden metadata). Cost: 0 tokens.

**Tier 3 — Screenshot + Vision (expensive, last resort):**
Only if tier 1+2 fail to find key fields (no follower count, no display name). Take a targeted screenshot of the profile header area (not full page) and send to Gemini Vision. Cost: ~3000-5000+ tokens.

**This pipeline cuts token usage by 60-80%** compared to always sending full-page screenshots.

Fallback: if no API key is set, use CSS selectors only (existing behavior).

### Per-Platform Data Extraction

The AI must be told specifically what to look for on each platform. Each platform's UI is different and shows different data.

#### X (Twitter)

**Navigate to:** User's profile page (`https://x.com/{username}`)

**X profiles have tabs:** Posts, Replies, Highlights, Articles, Media, Likes (some also have Subs). The header shows all key stats. Posts tab has full engagement metrics per tweet.

**Extraction flow:**
1. Load profile — extract header (name, handle, verified, bio, category, website, joined date, following, followers, post count, "Followed by" mutuals)
2. Scroll **Posts tab** — extract recent tweets with all engagement metrics (comments, reposts, likes, views). Note any **Pinned** posts.
3. Click **Media tab** — extract total media count ("3,454 photos & videos") — indicates how visual the creator is
4. Click **Highlights tab** — extract curated/pinned content with engagement (these are their best-performing posts)
5. (Optional) Click **Likes tab** — see what they engage with (reveals interests beyond their own posts)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Large bold text | "Shubham Saboo", "non aesthetic things" |
| Handle | Below name with @ | "@Saboo_Shubham_", "@PicturesFolder" |
| Verified badge | Blue checkmark | true/false |
| Bio | Text below handle | "Senior AI Product Manager @google \| Open Source..." |
| Category/profession | Below bio with icon | "AI Agents & RAG Tutorials →" |
| Website | Link below bio | "theunwindai.com" |
| Location | Below bio (if set) | "San Francisco" |
| Joined date | Below bio | "Joined June 2020" |
| Following count | In stats row | 426 |
| Followers count | In stats row | 113.2K |
| Post count | Small text in header area | "19.5K posts", "5 posts" |
| "Followed by" | Mutual followers shown | "Followed by KK, Daniel Das, and Peter Steinberger" |
| Subscribe button | If premium creator | true/false |
| Banner image | Top of profile | description |
| Profile picture | Circular image | description |
| **Posts tab (default):** | | |
| Tweet text | Main content | "Heard whispers about something that helps level..." |
| Comments count | Speech bubble icon | 15, 25 |
| Reposts count | Arrows icon | 67, 300 |
| Likes count | Heart icon | 298, 2600 |
| Views count | Bar chart icon | 88.3K, 149K |
| Posted at | Timestamp | "Mar 23", "4h", "16h" |
| Has media | Image/video attached | true/false |
| Is pinned | "Pinned" label | true/false |
| Is quote tweet | Embeds another tweet | true/false |
| Paid partnership | "Paid partnership" label | true/false |
| **Media tab:** | Click "Media" tab | |
| Total media count | Header text | "3,454 photos & videos" |
| Media grid | Thumbnails of images/videos | visual assessment |
| **Highlights tab:** | Click "Highlights" tab | |
| Highlighted posts | Curated best content | same fields as Posts |
| Video with view counts | Duration + views | "1:33:21 · 15.8K views" |
| **Articles tab:** | Click "Articles" tab | |
| Article titles | Long-form content | "Best AI PMs in 2026 Will Be Agent Managers" |
| Article engagement | Comments, reposts, likes, views | 17, 23, 190, 48K |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | Post count / account age, or from recent post timestamps |
| Content niches | From bio + category + post topics + hashtags used |
| Content quality | Engagement rates relative to follower count. High views but low likes = viral reach. High likes/views ratio = engaged audience. |
| Audience demographics | From content type, language, "Followed by" mutual accounts |
| Engagement rate | (avg likes + comments + reposts) / followers |
| Content format preference | Ratio of text-only vs image vs video posts from Media tab count vs post count |
| Is premium creator | Subscribe button present, Articles tab has content |
| Influence level | Follower count + verified + "Followed by" notable accounts |

#### LinkedIn

**Navigate to:** User's profile page (`https://www.linkedin.com/in/{username}/`)

**LinkedIn profiles are VERY long** — 7+ scrolls to see everything. Sections are behind "Show all →" arrows and "...more" expand buttons. The scraper must CLICK these, not just scroll.

**Extraction flow (order matters):**
1. Load profile page, extract header text (name, headline, location, followers, connections)
2. Scroll to "About" section → click "...more" if truncated → extract full text
3. Extract "Top skills" visible below About
4. Scroll to "Featured" section → extract featured post titles + engagement (reactions, comments)
5. Scroll to "Activity" section → note follower count shown here → click "Posts" tab → extract recent posts with reactions/comments/reposts
6. Scroll to "Experience" section → click "Show all →" if present → extract all entries
7. Scroll to "Education" section → extract entries
8. Scroll to "Skills" section → click "Show all →" → extract all skills
9. (Optional) Scroll to "Honors & awards", "Interests" sections

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Large text at top | "Rahul Jain" |
| Verified badge | Checkmark next to name | true/false |
| Headline | Below name (used as bio) | "Fund Manager @ Rahul Jain Capital \| Double MBA..." |
| Location | Below headline | "Delhi, India" |
| Follower count | Header area or Activity section | 14,531 |
| Connection count | Header area | "500+ connections" |
| Has Premium | Badge below connections | true/false |
| Website | "Visit my website" button | URL if present |
| About section | "About" card — MUST click "...more" to expand | Full text including awards, description |
| Top skills | Below About | ["Finance", "Stock Market", "Trading", "Investments", "Entrepreneurship"] |
| Featured posts | "Featured" section with thumbnails | |
| - Title | Post preview text | "Featured among '2026's Most Inspiring...'" |
| - Reactions | Number with emoji icons | 79 |
| - Comments | "X comments" text | 18 |
| Activity (recent posts) | "Activity" section → click "Posts" tab | |
| - Post text | First ~100 chars of post | "India almost broke a 7-year oil silence..." |
| - Reactions | Number next to reaction emojis | 98, 301 |
| - Comments | "X comments" text | 15, 21 |
| - Reposts | "X reposts" text | 2, 5 |
| - Posted at | Timestamp | "23h", "1d" |
| - Has image/video | Whether post has media | true/false |
| Experience (all) | "Experience" section → click "Show all →" | |
| - Job title | Bold text | "Investment Partner", "Education Mentor" |
| - Company | Below title | "IVY Growth Associates", "Market Kya Kehti Hai" |
| - Employment type | If shown | "Full-time", "Self-employed" |
| - Duration | Date range | "Aug 2024 - Present · 1 yr 9 mos" |
| - Location | Below duration | "Surat, Gujarat, India" |
| - Associated skills | If shown | "Trading, Stock Market and +9 skills" |
| Education (all) | "Education" section | |
| - School | Bold text | "Harvard Business School" |
| - Degree | Below school | "Finance, Accounting and Finance" |
| - Dates | Below degree | "Jan 2018 – Aug 2018" |
| Skills (all) | "Skills" section → click "Show all →" | |
| - Skill names | Listed entries | ["Entrepreneurship", "Investments", ...] |
| - Skill count | Number in header | 14, 28 |
| Honors & awards | If present — "Show all →" | |
| - Award name | Bold text | "Bharat Business Award 2025" |
| - Issuer | Below name | "Issued by Udyog Bhawan · Jun 2025" |
| Interests | Bottom of profile, has tabs (Companies/Groups/Newsletters/Schools) | |
| - Companies followed | Company names | "Sammaan Capital Limited", "LinkedIn News" |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | Estimate from Activity post timestamps |
| Content niches | From headline + about + skills + post topics |
| Content quality | Based on reactions/comments relative to follower count |
| Industry | From experience companies and headline |
| Seniority level | From job titles (junior, mid, senior, executive, founder) |
| Credibility signals | Awards, premium badge, verified status, follower count |

#### Facebook

**Navigate to:** User's profile page (`https://www.facebook.com/me`)

**Facebook profiles have tabs:** All (default), About, Friends, Photos, Reels, More ▼ (Check-ins, Likes). The "All" tab shows a personal details sidebar on the left and posts on the right.

**Extraction flow (must click each tab and sub-tab):**
1. Load profile (All tab) — extract header (name, friends count, subtitle, location) + personal details sidebar + scroll for posts
2. Click **"About" tab** — then click EACH sub-tab on the left sidebar:
   - Personal details → extract hometown, birthday, gender, relationship, family, language
   - Contact info → extract phone, email, social links, Instagram
   - Work → extract full work history
   - Education → extract all schools/degrees
   - Links → extract any linked websites
   - Names → extract alternate names
3. Click **"Reels" tab** — extract reel view counts (engagement signal)
4. Click **"More ▼" dropdown** — then click EACH option and scrape that page:
   - **Check-ins** → extract locations visited with dates
   - **Likes** → extract pages followed (categorized: All Likes, TV Shows, Artists, Sports Teams, Athletes, Apps and Games) — each sub-tab reveals different interests
   - **Events** → extract events attended (shows interests)
   - **Reviews given** → extract reviews (shows what products/businesses they care about)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Display name | Header, large text | "Ogbeka Golden" |
| Friends count | Below name | "4K friends" or "55 friends · 1 mutual" |
| Subtitle | Below name (job or school) | "Software Engineer" |
| Location | Header or personal details | "Lagos" |
| Instagram handle | Header (if linked) | "@goldenogbeka" |
| Cover photo | Banner at top | description |
| Profile picture | Circular photo | description |
| **Personal details sidebar (All tab):** | | |
| Current city | "Lives in..." | "Lives in Lagos, Nigeria" |
| Hometown | "From..." | "From Owerri, Imo" |
| Birthday | Date | "January 6, 1980" |
| Gender | If shown | "Male", "Female" |
| Relationship status | If shown | "Single", "Married" |
| Family members | Names + relationship | "Lilian Oragbakosi - Sister" |
| Language | If shown | "English language" |
| **Work (from sidebar or About tab):** | | |
| Job title | Bold text | "Frontend Engineer" |
| Company | Below title | "Alerzo" |
| Duration | Date range | "Oct 2022 - Present · 2 years 5 months" |
| **Education (from sidebar or About tab):** | | |
| School | School name | "Covenant University" |
| Degree | If shown | "MBA - Master in Business Administration" |
| **About tab sub-sections:** | Click "About" tab | |
| Personal details | Full details page | Hometown, birthday, gender |
| Contact info | Phone, email, social links | Instagram, website |
| Work history | Full employment history | Multiple entries |
| Education history | All schools | College, high school |
| **Recent posts (All tab, right column):** | | |
| Post text | Content of post | "India almost broke a 7-year oil silence..." |
| Likes count | Number next to thumbs-up | 3,900 |
| Comments count | "X comments" | 133 |
| Shares count | "X shares" | 103 |
| Posted at | Timestamp | "March 25 at 5:54 PM" |
| Has image/video | Whether post has media | true/false |
| **Reels tab:** | Click "Reels" tab | |
| Reel view counts | Numbers on thumbnails | 301, 67, 94, 139 |
| **More → Likes:** | Click "More ▼" → Likes | |
| Pages followed | Categorized: All, TV Shows, Artists, Sports Teams, Apps | "Silverpips", "UIX DSGNR" |
| Likes categories | Tab names indicate interests | Which categories have most likes |

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | From post timestamps on All tab |
| Content niches | From posts + work + liked pages + education |
| Content quality | Engagement (likes+comments+shares) relative to friends count |
| Privacy level | How much profile info is visible (some profiles very private) |
| Active on Reels? | Whether Reels tab has content (indicates video content interest) |
| Interests depth | From Likes tab categories — what types of pages they follow |

#### Reddit

**Navigate to:** User's profile page (`https://www.reddit.com/user/{username}/`)

**Reddit profiles have tabs:** Overview, Posts, Comments (and private-only: Saved, History, Hidden, Upvoted, Downvoted). The right sidebar shows stats and achievements. Some profiles are **private** ("likes to keep their posts hidden").

**Extraction flow:**
1. Load Overview tab — extract header (username, display name, avatar) + right sidebar stats (karma, age, followers, achievements, trophy case)
2. Click **"Posts" tab** — extract recent posts with title, subreddit, score, comments, timestamp
3. Click **"Comments" tab** — extract recent comments with subreddit context, text, upvotes (reveals which communities they're active in)

**What to extract:**
| Field | Where to find it | Example |
|-------|-----------------|---------|
| Username | Profile header with u/ prefix | "u/SamaaraDas" |
| Display name | Above username (if custom set) | "SamaaraDas" or custom like "mujhe kya mein toh foolgobhi hu" |
| Bio | Below username (if set) | "Trader, coder, coffee addict" |
| Avatar | Profile picture | description |
| Banner | If customized | description |
| **Right sidebar stats:** | | |
| Total karma | Sidebar stat | 223 |
| Post karma / Comment karma | If shown separately | split values |
| Contributions count | Sidebar stat | 17 |
| Account age | Sidebar stat | "6y" or "new to Reddit" |
| Follower count | Sidebar stat | 0, 1.83K |
| **Achievements section:** | Right sidebar | |
| Achievement badges | Named badges with icons | "30 Day Streak", "Nice Post", "Banana Baby" |
| Achievement count | Total + "View All" link | "+16 more" |
| **Trophy Case:** | Right sidebar (below achievements) | |
| Trophies | Named awards | "Six-Year Club", "Verified Email", "First Place '22" |
| **Posts tab:** | Click "Posts" tab | |
| Post title | Bold text | "My honest take on the 'Smart Money Indicator Beta'..." |
| Subreddit | r/ prefix above post | "r/IndianStockMarket" |
| Score (upvotes) | Number with up/down arrows | 2, 5, 21 |
| Comments count | Number next to comment icon | 2, 3 |
| Shares count | If shown | 3 |
| Views count | Shown for own posts | "21 views", "330 views" |
| Posted at | Timestamp | "1 yr ago", "10 days ago" |
| Post status | If removed | "[removed]" by moderators |
| Has media | Image/video/link | true/false |
| **Comments tab:** | Click "Comments" tab | |
| Comment text | The user's comment | "What I would do: find high value skills..." |
| Parent subreddit | r/ prefix | "r/IndianStockMarket" |
| Parent post title | Post they commented on | "Just turned 18 what should I invest in..." |
| Comment upvotes | Number | 4, 1 |
| Comment views | If shown (own comments) | 330, 1 |
| Comment timestamp | When posted | "10 days ago" |

**Handling private profiles:** If the Overview shows "likes to keep their posts hidden" with a Welcome mascot, the profile is private. Extract only sidebar stats (karma, age, achievements). Mark `profile_privacy = "private"` in the output.

**AI-inferred fields:**
| Field | How |
|-------|-----|
| Posting frequency | From post timestamps on Posts tab |
| Content niches | From subreddit names (posts + comments) — if they post in r/daytrading, r/stocks, r/IndianStockMarket → niche is "trading", "finance" |
| Content quality | Post scores relative to subreddit norms |
| Community reputation | Karma + account age + trophy case badges |
| Active subreddits | Ranked by frequency from both Posts and Comments tabs |
| Engagement style | Ratio of posts vs comments — heavy commenter vs heavy poster |
| Expertise signals | Trophy case (verified email, year clubs), achievements (streaks), karma level |

### Navigation Strategy

The scraper navigates, scrolls, AND clicks to capture all data. Just scrolling is NOT enough — LinkedIn, Facebook, and others hide data behind "Show all →" arrows and "...more" expand buttons.

**General flow per platform:**
1. Navigate to profile page. Wait for page load.
2. Click all expand buttons visible: "...more", "Show all →", "See more" — these reveal hidden content.
3. Extract all visible page text.
4. Scroll down 2-3 viewport heights to load below-fold content.
5. Click more expand buttons that appeared after scrolling.
6. Extract page text again — captures posts, experience, skills, etc.
7. Repeat scrolling + clicking until reaching the bottom of the profile.
8. Combine all text extractions and send to AI for structured data extraction.
9. Only if text extraction fails (key fields missing), fall back to targeted screenshot + Vision.

**Platform-specific clicks needed:**
- **LinkedIn:** Click "...more" on About, "Show all →" on Skills/Experience/Awards, "Posts" tab in Activity section
- **X:** Scroll to load more tweets (infinite scroll)
- **Facebook:** Click "See more" on bio, scroll timeline
- **Reddit:** Click "Posts" tab if not default, scroll to load posts

This approach gets richer data than screenshots while using text tokens instead of image tokens.

### Normalized Output (all platforms)

All platforms return the same normalized structure containing:

| Field | Type | Description |
|-------|------|-------------|
| platform | text | Which platform (x, linkedin, facebook, reddit) |
| display_name | text | User's display name |
| username | text | Handle/username |
| bio | text | Bio, headline, or description |
| follower_count | number | Followers (or friends on Facebook, karma on Reddit) |
| following_count | number | Following count |
| post_count | number | Total posts if visible |
| location | text | Location if shown |
| website | text | Website if shown |
| join_date | text | Account creation date |
| verified | boolean | Verified badge present |
| recent_posts | list | Up to 10 recent posts with: text, likes, comments, reposts, views, timestamp, subreddit (Reddit), has_media |
| posting_frequency | number | Estimated posts per day |
| profile_data | object | Extended data: about section, experience, education, skills, karma, active subreddits, personal details |
| ai_detected_niches | list | AI-classified content niches (1-5) |
| content_quality | text | "low", "medium", or "high" |
| audience_demographics_estimate | object | Estimated age range and interests |
| engagement_rate | number | Average (likes + comments + reposts) / followers |

### Acceptance Criteria

1. Connect X. Profile scraper runs. Result includes: follower count > 0, display name, at least 3 recent posts with engagement metrics.
2. Disconnect AI key. Scraper falls back to element-based extraction. Still returns data (less rich but functional).
3. Connect LinkedIn. Result includes: at least 1 work experience entry, headline.
4. Connect Reddit. Result includes: karma > 0, active subreddits, posts with scores.
5. All 4 platform profiles sync to the server successfully.
6. Token usage for text-first extraction is under 2000 tokens per platform (no vision calls for normal profiles).

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


3. **Cross-platform consistency:** If a user posts about finance on X but food on LinkedIn, the score should reflect which platform(s) are relevant to the campaign, not average across all.

4. **Niche specificity:** A user who posts exclusively about "day trading" is a BETTER match for a trading indicator campaign than a user who posts about "finance" broadly. Reward niche depth over breadth.

5. **Self-selected niches override profile analysis:** Users select their own niches during onboarding. If a tech person selects "lifestyle" and "food" as niches, they SHOULD receive lifestyle and food campaigns — even if their profile is all tech. The user knows what they want to post about. Self-selected niches should be weighted EQUALLY to profile-detected niches in the scoring prompt. The AI should be told: "The creator has chosen to post about these niches: {self_selected_niches}. Respect this — they may want to expand into new topics."

#### Fallback (when AI fails)

If all Gemini models fail, use niche overlap scoring:
- Each overlapping niche between user and campaign = +25 points
- No niche targeting on campaign = base score of 50
- Minimum score: 10

#### Caching

- Cache key: `(campaign_id, user_id)`
- TTL: 24 hours
- Invalidated on: campaign edit, user profile refresh

### Acceptance Criteria

1. A finance creator with trading posts matched against a trading indicator campaign scores above 75 (strong fit).
2. A cooking creator with recipe posts matched against the same trading campaign scores below 30 (weak fit).
3. A user who posts about finance on X but food on Facebook, matched against an X-only campaign, scores based on their X content (>70), not averaged with Facebook.
4. A tech creator who self-selected "lifestyle" and "food" niches receives lifestyle and food campaign invitations — self-selected niches are respected.
5. When all AI models fail, fallback niche-overlap scoring produces a reasonable score without crashing.
6. The same user + campaign combination scored twice within 24 hours uses the cached score (no duplicate API call).
7. The minimum score to create an invitation is 40 — users scoring below 40 are not invited.

---

## Task #14 — 4-Phase Content Agent (Detailed Spec)

### What It Does

Generates campaign content across 4 platforms that feels like a real person recommending a product. The content should be platform-native, goal-driven, and adapt over time.

### The 4 Phases

#### Phase 1: Research (runs weekly per campaign, cached)

**Purpose:** Understand the product deeply so content is specific and credible, not generic.

**What it does:**
1. Scrape company URLs from the campaign (up to 3 URLs) to understand the product deeply
2. Extract: product name, features, benefits, pricing, testimonials, competitors
3. Analyze campaign images (if any) via AI vision — what does the product look like?
4. **Search for recent niche news** — search the web for 3-5 recent news headlines in the campaign's niche. This gives the content agent current events to reference, making posts feel timely and authentic instead of generic. (1 search per weekly refresh — minimal cost.)
5. Synthesize all findings into a structured research context

**Research output includes:**
- Product summary (1-2 sentences)
- Key features (3-5 bullet points)
- Target audience description
- Competitive angle (what makes this different)
- Content angles (5 different approaches for posts)
- Emotional hooks (3 triggers to use in content)
- Pricing info (if found on company website)
- Testimonials (if found)
- Recent niche news (3-5 headlines from web search — makes content timely)

**Cached for 7 days.** Refreshed weekly or when the campaign brief changes.

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

**The AI strategy prompt should reason about:**
1. What content angles will resonate with this creator's audience?
2. How many posts per day per platform? (X can handle 2-3, LinkedIn 1, Reddit less than 1)
3. Should posts include images? (depends on the product and platform)
4. What hook styles should we use? (question, story, stat, contrarian, etc.)
5. What time of day works best for this creator's audience region?

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

**Timeliness rule (makes content feel real):**
- If `recent_niche_news` is available from the research phase, the AI SHOULD reference current events when relevant. Example: instead of "this indicator shows institutional flow" → "after yesterday's Fed decision, this indicator lit up showing institutions were buying the dip." Not every post needs a news reference — use it when it naturally fits the hook or angle.

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

**Semi-auto mode:** Store drafts, send desktop notification, wait for user to review and approve.
**Full-auto mode:** Auto-approve and schedule immediately using strategy's posting times.

### Content Quality Checks

Before storing a draft, verify:
1. X content is within 280 chars (after FTC disclosure)
2. Reddit has both title and body
3. No AI-banned phrases are present
4. Content is different from the last 3 days' posts (cosine similarity < 0.8)

### Fallback

If any phase fails, fall back to the existing single-prompt `ContentGenerator.generate()`. This ensures content is always produced, even if the AI pipeline has issues.

### Acceptance Criteria

1. A virality campaign with edgy tone produces X content using contrarian or surprising hooks — not gentle storytelling.
2. A leads campaign produces posts that mention the product and include a clear call-to-action on every platform.
3. Content for the same campaign on day 1 vs day 5 is genuinely different — different angle, different hook, different structure.
4. Reddit posts include both positives AND a caveat or negative about the product (authentic tone).
5. X posts are under 280 characters including the FTC disclosure that gets appended.
6. A brand_awareness strategy generates 1 post/day on X but only every other day on Reddit.
7. If the AI provider fails entirely, content falls back to the basic single-prompt generator. No crash, still produces content.
8. Research phase includes recent niche news headlines. At least one post per week references a current event when relevant.
9. The strategy adapts based on the creator's profile — a casual creator gets casual tone, a professional creator gets professional tone.

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

### Feedback

When a campaign fails, the system returns:
- **Overall score** (0-100) and pass/fail status
- **Per-criterion score breakdown** (how many points each criterion earned)
- **Actionable feedback messages** for each failed criterion, telling the company exactly what to fix. Examples:
  - "Brief is too short (89 chars). Describe your product, its key features, and who it's for. Aim for 300+ characters."
  - "No content guidance provided. Add tone instructions, must-include phrases, or content examples."
  - "No product images or company URLs provided. Add at least one image or website link."
  - "Budget is below recommended minimum. Campaigns under $100 reach fewer creators."

### Two-Layer Scoring: Mechanical Rubric + AI Review

**Layer 1 — Mechanical rubric (instant, no API call):** The 8-criterion scoring table above. Fast, deterministic, catches obvious gaps.

**Layer 2 — AI review (server-side Gemini call):** After the rubric passes (score >= 85), run a Gemini AI review that catches what rules can't. Uses the **server's API keys** (not user's). Low volume — only runs on campaign activation, not per-post.

**The AI review checks for:**
1. Is the brief coherent and specific? Or is it vague filler text?
2. Are the payout rates competitive for this niche? (finance campaigns should pay more than lifestyle)
3. Does the content guidance contain anything harmful? (attacking competitors, misleading claims, asking for fake reviews)
4. Does the targeting make sense for the product? (finance product targeting fashion niche = mismatch)
5. Is this a legitimate product or does it look like a scam/spam?

**AI review returns:**
- Pass/fail decision
- List of specific concerns (if any)
- Niche rate assessment: competitive, below average, or too low
- Brand safety rating: safe, caution, or reject

**Actions based on AI review:**
- **"reject" brand safety** → block activation, show AI's concerns as feedback
- **"caution" brand safety** → flag for admin review but allow activation
- **AI passes** → campaign can go live

### When It Runs

1. **On activation attempt** — company clicks "Activate" or changes status to `active`. Run mechanical rubric first (instant). If passes, run AI review (1-2 second API call).
2. **On campaign detail page** — show current score and feedback as a pre-flight check (mechanical rubric only — informational, not blocking)
3. **After AI wizard generates** — score the wizard output and warn if low

### Special Cases

- **Repost campaigns** (`campaign_type = "repost"`): Don't require content_guidance (company provides the exact content). Do require the repost content to be filled in.
- **Wizard-generated campaigns**: Usually score high (85+) because the wizard produces comprehensive briefs. The gate mainly catches manually-created campaigns with minimal info.

### Acceptance Criteria

1. A campaign with a 16-character brief, no guidance, no assets, $25 budget scores below 50 and is blocked. Feedback includes: "Brief is too short", "No content guidance", "No assets", "Budget below minimum."
2. A campaign created via the AI wizard scores >= 85 and passes automatically.
3. A campaign with a great brief but $0 payout rates fails on the payout rates criterion with specific feedback.
4. After fixing all issues from test 1 (longer brief, guidance added, image uploaded, budget increased), re-activation succeeds.
5. A repost campaign with no content guidance but repost content filled in passes — the guidance criterion does not penalize repost campaigns.
6. A campaign with a coherent brief but harmful content guidance ("write fake negative reviews of competitor X") is caught by the AI review layer and blocked with a brand safety concern.
7. A campaign targeting "fashion" but whose brief describes a financial product is caught by the AI review as a targeting mismatch.
