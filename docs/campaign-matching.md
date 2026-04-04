# Amplifier -- Campaign Matching Deep Dive

**File:** `server/app/services/matching.py`

## Overview

When a user polls for campaigns, the server runs a multi-stage pipeline:
1. Hard filters (pass/fail)
2. AI relevance scoring (Gemini)
3. Sort by score, create invitations for ALL passing candidates

The matching is fully AI-driven -- no hardcoded scoring formula.

## Hard Filters (All Must Pass)

| Filter | Logic | Details |
|--------|-------|---------|
| Required platforms | `set(required) & user_platforms` | User must have AT LEAST 1 of the required platforms |
| Min followers | Per-platform check | `user_followers[platform] >= minimum` for each specified platform |
| Target regions | Region match | User region must be in campaign's target_regions, or user is "global" |
| Min engagement | Avg engagement check | User's average engagement rate across platforms >= campaign minimum |
| Max users | Cap check | `campaign.accepted_count < max_users` |
| Budget remaining | `> 0` | Campaign still has money |
| Already assigned | Dedup check | Skip if user already has this campaign |
| Tier-based campaign limit | Active count vs tier cap | User at or above their tier's max active campaigns skips matching |

**Tier-based campaign limits** (from `get_tier_config()` in `billing.py`):

| Tier | Max Active Campaigns |
|------|---------------------|
| Seedling | 3 |
| Grower | 10 |
| Amplifier | Unlimited |

Active statuses for campaign limit: `accepted, content_generated, posted, metrics_collected`

## AI Relevance Scoring

### What the AI Sees

The prompt includes ALL raw scraped data per platform:

**Per platform:**
- Display name, bio
- Followers count, following count
- Posting frequency (posts/day)
- Up to 8 recent posts with FULL engagement metrics:
  - Text content (first 200 chars)
  - likes, comments, replies, retweets, reposts, shares, score, views
  - Subreddit (Reddit), posted_at timestamp

**Extended fields (when available):**
- LinkedIn: about section, work experience (3 entries), education, profile_viewers (90-day), post_impressions (90-day)
- Reddit: karma, contributions, reddit_age, active_communities
- Facebook: personal_details (location, hometown, relationship, work, education, links, contact)

### The AI Prompt

```
You are matching creators to brand campaigns on Amplifier, a platform where
everyday social media users earn money by posting about products.

== CAMPAIGN ==
Title, Brief (1500 chars), Content guidance, Target niches, Target regions, Required platforms

== CREATOR ==
Self-selected niches, Connected platforms, Region
[Full scraped profile data per platform]

== IMPORTANT CONTEXT ==
Most creators on Amplifier are NORMAL PEOPLE, not influencers. They typically have:
- Fewer than 1,000 followers
- Infrequent posting (a few times per month, not daily)
- Low engagement numbers (single digits of likes/comments is normal)

DO NOT penalize for low follower counts, infrequent posting, or low engagement numbers.

== SCORING ==
Judge ONLY on:
1. TOPIC RELEVANCE (does their content relate to the campaign?)
2. AUDIENCE FIT (would their connections care about this product?)
3. AUTHENTICITY (would this feel natural or forced?)

Score 70-100: Good fit
Score 40-69: Possible fit
Score 10-39: Weak fit
Score 0-9: No fit

Return ONLY a number between 0 and 100.
```

### Model Fallback Chain
1. `gemini-2.5-flash`
2. `gemini-2.0-flash`
3. `gemini-2.5-flash-lite`

On 429/RESOURCE_EXHAUSTED: continues to next model. On other errors: raises.

### Fallback Scoring (When AI Fails)

If all Gemini models fail, uses simple niche-overlap:
- Each overlapping niche = +30 points
- No niche targeting = +10 base score
- Minimum: 1.0

## Score Caching

- Cache: in-memory dict `(campaign_id, user_id) -> (score, timestamp)`
- TTL: 24 hours
- Invalidation: on campaign edit or user profile refresh

## Invitation Creation

After scoring:
1. Sort by score descending
2. Create `CampaignAssignment` for every candidate with score > 0:
   - status: `pending_invitation`
   - content_mode: `ai_generated` (full_auto) or `user_customized` (semi_auto)
   - expires_at: 3 days from now
   - payout_multiplier: 1.0 (fixed in v2)
4. Increment `campaign.invitation_count`
5. Log event in `campaign_invitation_log`
6. Return: new invitations + existing non-completed assignments

## 21 Unified Niches

Both company wizard and user onboarding use the same list:
```
finance, trading, investing, crypto, technology, ai, business, marketing,
lifestyle, education, health, fitness, food, travel, entertainment, gaming,
sports, fashion, beauty, parenting, politics
```
