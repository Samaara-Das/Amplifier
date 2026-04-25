# Amplifier -- User App Development Guide

## Overview

The user app is a local Flask application (port 5222) that runs on the amplifier's (user's) desktop. It handles onboarding, campaign management, content generation, posting, and metric scraping.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/user_app.py` | Flask routes, onboarding, settings, dashboard |
| `scripts/background_agent.py` | Polling loop: campaigns, content gen, posting, metrics |
| `scripts/post.py` | Platform-specific Playwright posting functions |
| `scripts/login_setup.py` | Manual browser login for platform auth |
| `scripts/utils/content_generator.py` | AI content generation (Gemini/Mistral/Groq) |
| `scripts/utils/profile_scraper.py` | Platform profile data extraction |
| `scripts/utils/post_scheduler.py` | Timezone-aware post scheduling |
| `scripts/utils/server_client.py` | HTTP client for Amplifier server API |
| `scripts/utils/local_db.py` | Local SQLite database operations |
| `scripts/utils/tray.py` | System tray icon + desktop notifications |

## Onboarding Flow (5 Steps)

### Step 1: Connect Platforms
- User clicks "Connect" on platform card (X, LinkedIn, Facebook, Reddit)
- `login_setup.py` launches headed Playwright browser to platform home URL
- User logs in manually, closes browser when done
- Browser profile saved to `profiles/{platform}-profile/`
- Auto-scrapes profile in background thread after browser closes
- Reddit always runs headed (blocked by Reddit's network security in headless)

### Step 2: Profile & Niches
- Shows scraped data: display name, followers, engagement rate per platform
- 21 niche checkboxes (same list on company and user side):
  `finance, trading, investing, crypto, technology, ai, business, marketing, lifestyle, education, health, fitness, food, travel, entertainment, gaming, sports, fashion, beauty, parenting, politics`
- Audience region auto-detected from IP (via ipapi.co)

### Step 3: Operating Mode
- Semi-Auto: AI generates, user reviews before posting
- Full Auto: AI generates and posts automatically

### Step 4: API Keys
- Gemini (required), Mistral (optional), Groq (optional)
- Step-by-step instructions per provider
- Test button validates key with a minimal API call
- 429/quota errors treated as valid (quota resets daily)
- Eye toggle to show/hide key
- Next button disabled until at least 1 key entered

### Step 5: Summary + Start
- Reviews all choices
- Saves settings to local SQLite
- Syncs to server: platforms, follower_counts, niche_tags, region, mode, scraped_profiles
- Starts background agent
- Marks onboarding complete

## Background Agent (`background_agent.py`)

Runs as a daemon thread. Main loop every 60 seconds:

| Task | Interval | What it does |
|------|----------|-------------|
| Campaign polling | 10 min | `GET /api/campaigns/invitations` + `GET /api/campaigns/active` |
| Content generation | 2 min check | Generate daily drafts for accepted campaigns |
| Post execution | 60 sec | Check `post_schedule` for due posts, execute via `post.py` |
| Metric scraping | 60 sec | Revisit posts at T+1h, T+6h, T+24h, T+72h |
| Metric submission | After scraping | `POST /api/metrics` (triggers server billing) |
| Session health | 30 min | Verify browser sessions still valid |
| Profile refresh | 7 days | Re-scrape all platform profiles |

## Content Generation Pipeline

### AI Provider Fallback Chain
1. **Gemini** (gemini-2.5-flash > 2.0-flash > 2.5-flash-lite) -- 3 models, separate quotas
2. **Mistral** (mistral-small-latest)
3. **Groq** (llama-3.3-70b-versatile)

### Per-Platform Content Formats
| Platform | Format |
|----------|--------|
| X | 280 chars, hook + hashtags |
| LinkedIn | 500-1500 chars, story format, aggressive line breaks, question + hashtags |
| Facebook | 200-800 chars, conversational, question, 0-2 hashtags |
| Reddit | Title (60-120 chars, non-clickbait) + body (500-1500 chars, genuine) |

### Draft Lifecycle
1. Generated -> stored in `agent_draft`
2. Semi-auto: user reviews in dashboard, approves/rejects/edits
3. Full-auto: auto-approved immediately
4. Approved draft -> scheduled in `post_schedule`
5. Posted -> URL captured -> synced to server

## Posting Engine (`post.py`)

### Per-Platform Gotchas
- **X**: Overlay div intercepts clicks -- use `dispatch_event("click")`. Image via hidden `input[data-testid="fileInput"]`.
- **LinkedIn**: Shadow DOM -- use `page.locator()` (pierces), NOT `page.wait_for_selector()`. Image via file chooser.
- **Facebook**: Image via "Photo/video" button then hidden file input.
- **Reddit**: Shadow DOM (faceplate components) -- Playwright locators pierce automatically.
- **Reddit scraper**: Must run headed (Reddit blocks headless with "network security" error).

### Human Behavior Emulation
- Character-by-character typing (30-80ms per char)
- Random delays between actions (1-5 seconds)
- Feed browsing before/after posting (1-3 seconds)
- Random scroll/mouse movement

### URL Capture
After posting, navigates to profile to find the new post URL:
- Retry logic: 3 attempts with scrolling
- Graceful fallback: `posted_no_url` status if URL not found (post still delivered)

## Profile Scraper

### Data Extracted Per Platform

**X (Twitter)**: display_name, bio, followers, following, profile_pic, up to 30 posts (text + likes, retweets, replies)

**LinkedIn**: display_name, bio, followers, following, profile_pic, about section, experience (jobs), education, profile_viewers, post_impressions, up to 30 posts (text + reactions, comments, reposts)

**Facebook**: display_name, bio, friends count, profile_pic, personal details (location, hometown, relationship, work, education, links, contact), up to 30 posts (text + likes, comments, shares)

**Reddit** (headed only): display_name, followers, karma, contributions, reddit_age, active_communities, profile_pic, up to 30 posts (title, score, comments, views, subreddit)

### Scraping Triggers
- On platform connect (during onboarding)
- Weekly refresh (background agent)
- Manual refresh (user clicks in Settings)

## Post Scheduling

### Timezone Mapping
| Region | Timezone |
|--------|----------|
| us | America/New_York |
| uk | Europe/London |
| india | Asia/Kolkata |
| eu | Europe/Berlin |
| latam | America/Sao_Paulo |
| sea | Asia/Singapore |
| global | America/New_York |

### Constraints
- Min 30 sec between any posts
- Min 60 sec between same-platform posts from different campaigns
- Daily limit: `min(active_campaigns * 4, 20)` posts/day
- 1-15 min random jitter to avoid patterns

## Local Database

SQLite at `data/local.db` with WAL mode. Key tables:

- `settings`: Key-value store (mode, region, API keys, onboarding_done)
- `scraped_profile`: Per-platform profile data (follower_count, bio, recent_posts JSON, profile_data JSON)
- `local_campaign`: Tracked server campaigns (server_id, assignment_id, status)
- `agent_draft`: AI-generated content drafts (campaign_id, platform, text, approved)
- `post_schedule`: Queued posts (campaign_id, platform, scheduled_at, content, status)
- `local_post`: Posted content (post_url, content_hash, synced flag)
- `local_metric`: Scraped engagement data (impressions, likes, reposts, comments)
- `local_notification`: Desktop notification queue

## Server Communication

All API calls go through `scripts/utils/server_client.py`:
- Auth token stored in `config/server_auth.json`
- Auto-retry with exponential backoff (3 attempts, 5s base delay)
- Server URL: `CAMPAIGN_SERVER_URL` env var, default `http://localhost:8000` (production server offline — see `docs/MIGRATION-FROM-VERCEL.md`)

## Config Files

| File | Purpose |
|------|---------|
| `config/platforms.json` | Platform URLs, timeouts, enable flags, proxy, subreddits |
| `config/.env` | Timing params, headless mode, browsing behavior, daily caps |
| `config/server_auth.json` | JWT access token (auto-created on login) |
| `data/local.db` | Local SQLite database (auto-created) |
| `profiles/{platform}-profile/` | Playwright browser profiles (cookies, auth) |
