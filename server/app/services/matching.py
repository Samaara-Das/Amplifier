"""Campaign-to-user matching with AI-powered relevance scoring.

v2 upgrade: replaces simple niche-overlap scoring with Gemini AI scoring.
Falls back to niche-overlap if AI fails. Caches scores for 24 hours.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.invitation_log import CampaignInvitationLog
from app.models.user import User
from app.schemas.campaign import CampaignBrief

logger = logging.getLogger(__name__)

# Invitation expires 3 days after being sent
INVITATION_TTL = timedelta(days=3)

# Score cache: (campaign_id, user_id) -> (score, cached_at)
SCORE_CACHE_TTL = timedelta(hours=24)
_score_cache: dict[tuple[int, int], tuple[float, datetime]] = {}


# ── Score Caching ─────────────────────────────────────────────────


def get_cached_score(campaign_id: int, user_id: int) -> float | None:
    """Get cached AI score if not stale (< 24h). Returns None on miss."""
    key = (campaign_id, user_id)
    entry = _score_cache.get(key)
    if entry is None:
        return None
    score, cached_at = entry
    if datetime.now(timezone.utc) - cached_at > SCORE_CACHE_TTL:
        # Stale — remove and return miss
        del _score_cache[key]
        return None
    return score


def cache_score(campaign_id: int, user_id: int, score: float):
    """Cache an AI relevance score."""
    _score_cache[(campaign_id, user_id)] = (score, datetime.now(timezone.utc))


def invalidate_cache(
    campaign_id: int | None = None, user_id: int | None = None
):
    """Invalidate cached scores for a campaign edit or user profile refresh.

    If both campaign_id and user_id are given, only the exact pair is removed.
    If only one is given, all entries matching that dimension are removed.
    """
    if campaign_id is not None and user_id is not None:
        _score_cache.pop((campaign_id, user_id), None)
        return

    keys_to_remove = []
    for (cid, uid) in _score_cache:
        if campaign_id is not None and cid == campaign_id:
            keys_to_remove.append((cid, uid))
        elif user_id is not None and uid == user_id:
            keys_to_remove.append((cid, uid))

    for key in keys_to_remove:
        del _score_cache[key]


# ── Gemini API Call ───────────────────────────────────────────────


async def _call_gemini(prompt: str) -> str:
    """Call Gemini API and return raw text response.

    Uses google.genai Client, same pattern as campaign_wizard.py.
    Runs the synchronous SDK call in a thread to avoid blocking the event loop.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    from google import genai

    client = genai.Client(api_key=api_key)

    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
    last_err = None
    for model in models:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            last_err = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                continue
            raise
    raise last_err


# ── AI Relevance Scoring ─────────────────────────────────────────


def _get_user_engagement_rate(user: User) -> float:
    """Calculate average engagement rate across all scraped platforms."""
    profiles = user.scraped_profiles
    if not profiles:
        return 0.0

    rates = []
    for platform_data in profiles.values():
        if isinstance(platform_data, dict):
            rate = platform_data.get("avg_engagement_rate")
            if rate is not None:
                rates.append(float(rate))

    if not rates:
        return 0.0
    return sum(rates) / len(rates)


def _build_scoring_prompt(campaign: Campaign, user: User) -> str:
    """Build a detailed prompt for AI relevance scoring.

    Uses the full scraped profile data to help AI understand the creator's
    content style, audience, expertise, and fit for the campaign.
    """
    targeting = campaign.targeting or {}

    # Build detailed creator profile from scraped data
    profile_sections = []
    profiles = user.scraped_profiles or {}
    for platform, data in profiles.items():
        if not isinstance(data, dict):
            continue
        section = f"\n--- {platform.upper()} ---"
        bio = data.get("bio", "")
        if bio:
            section += f"\nBio: {bio}"
        followers = data.get("follower_count", 0)
        if followers:
            section += f"\nFollowers: {followers}"
        engagement = data.get("avg_engagement_rate", 0)
        if engagement:
            section += f"\nEngagement rate: {engagement:.3f}"

        # Include recent post content for style analysis
        posts = data.get("recent_posts", [])
        if posts:
            section += f"\nRecent posts ({len(posts)}):"
            for p in posts[:5]:
                if isinstance(p, dict):
                    text = p.get("text", p.get("title", ""))
                    if text:
                        section += f"\n  - {text[:150]}"
                elif isinstance(p, str):
                    section += f"\n  - {p[:150]}"

        # Include extended profile data if available
        profile_data = data.get("profile_data", {})
        if isinstance(profile_data, dict):
            about = profile_data.get("about", "")
            if about:
                section += f"\nAbout: {about[:300]}"
            experience = profile_data.get("experience", [])
            if experience:
                section += f"\nExperience: {experience[:3]}"

        profile_sections.append(section)

    creator_profile = "\n".join(profile_sections) if profile_sections else "No scraped profile data available"

    engagement_rate = _get_user_engagement_rate(user)
    connected_platforms = [
        k for k, v in (user.platforms or {}).items()
        if isinstance(v, dict) and v.get("connected")
    ]

    return f"""You are an expert campaign-to-creator matching system. Analyze the creator's FULL profile and determine how well they fit this campaign.

== CAMPAIGN ==
Title: {campaign.title}
Brief: {campaign.brief[:1000]}
Content guidance: {campaign.content_guidance or 'None'}
Target niches: {targeting.get('niche_tags', [])}
Target regions: {targeting.get('target_regions', [])}
Required platforms: {targeting.get('required_platforms', [])}

== CREATOR ==
Self-selected niches: {user.niche_tags or []}
Connected platforms: {connected_platforms}
Overall engagement rate: {engagement_rate:.4f}
Region: {user.audience_region or 'global'}

{creator_profile}

== SCORING CRITERIA ==
Rate 0-100 based on:
1. Content alignment: Does the creator's posting history match the campaign topic? (40 pts)
2. Audience fit: Does the creator's audience (based on their content + platform) match who the campaign targets? (25 pts)
3. Quality signals: Engagement rate, posting consistency, profile completeness (20 pts)
4. Platform match: Does the creator post on the platforms the campaign needs? (15 pts)

A score of 70+ means strong fit. 40-70 means moderate fit. Below 40 means poor fit.

Return ONLY a number between 0 and 100."""


def _parse_score(text: str) -> float:
    """Extract a numeric score from AI response text.

    Handles responses like "85", "85.5", "Score: 78", "78/100", "-10", etc.
    """
    # Find the first number (possibly negative) in the response
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if match:
        score = float(match.group(1))
        return max(0.0, min(100.0, score))
    raise ValueError(f"Could not parse score from: {text!r}")


async def ai_score_relevance(campaign: Campaign, user: User) -> float:
    """Score how relevant a campaign is for a user using AI.

    Returns a float 0-100 on success, or -1.0 if AI fails (sentinel for
    fallback to niche-overlap scoring).

    Checks the score cache first; on cache hit, skips the AI call entirely.
    """
    # Check cache first
    cached = get_cached_score(campaign.id, user.id)
    if cached is not None:
        return cached

    try:
        prompt = _build_scoring_prompt(campaign, user)
        response_text = await _call_gemini(prompt)
        score = _parse_score(response_text)
        cache_score(campaign.id, user.id, score)
        return score
    except Exception as exc:
        logger.warning(
            "AI scoring failed for campaign=%d user=%d: %s",
            campaign.id, user.id, exc,
        )
        return -1.0  # sentinel: caller should fall back


# ── Combined Scoring ──────────────────────────────────────────────


def calculate_combined_score(
    ai_score: float, trust_score: int, engagement_rate: float
) -> float:
    """Combine AI relevance, trust, and engagement into a final score.

    Formula:
        final = ai_score * 0.6 + trust_score * 0.2 + min(engagement_rate * 1000, 20)

    All components are capped so the maximum final score is 100.
    """
    trust_bonus = (trust_score or 0) * 0.2  # 0-20
    engagement_bonus = min(engagement_rate * 1000, 20)  # 0-20
    return ai_score * 0.6 + trust_bonus + engagement_bonus


# ── Niche-Overlap Fallback Scoring ────────────────────────────────


def _fallback_niche_score(campaign: Campaign, user: User) -> float:
    """Original v1 niche-overlap scoring. Used when AI fails."""
    targeting = campaign.targeting or {}
    score = 0.0

    target_niches = set(targeting.get("niche_tags", []))
    # Use AI-detected niches if available, fall back to self-reported
    user_niches = set(user.ai_detected_niches or user.niche_tags or [])
    niche_overlap = len(target_niches & user_niches)
    score += niche_overlap * 30

    # If no niche targeting, give a base score so everyone can participate
    if not target_niches:
        score += 10

    return max(score, 1.0)


# ── Hard Filters ──────────────────────────────────────────────────


def _passes_hard_filters(campaign: Campaign, user: User) -> bool:
    """Check hard filters. Returns True if user is eligible for the campaign."""
    targeting = campaign.targeting or {}

    # Required platforms — user must have AT LEAST ONE of the required platforms
    required_platforms = targeting.get("required_platforms", [])
    if required_platforms:
        user_platforms = set(
            k for k, v in (user.platforms or {}).items()
            if isinstance(v, dict) and v.get("connected")
        )
        if not set(required_platforms) & user_platforms:
            return False

    # Minimum follower counts
    min_followers = targeting.get("min_followers", {})
    user_followers = user.follower_counts or {}
    for platform, minimum in min_followers.items():
        if user_followers.get(platform, 0) < minimum:
            return False

    # Target regions
    target_regions = targeting.get("target_regions", [])
    if target_regions:
        user_region = getattr(user, "audience_region", "global") or "global"
        if user_region != "global" and user_region not in target_regions:
            return False

    # Minimum engagement rate
    min_engagement = targeting.get("min_engagement", 0)
    if min_engagement > 0:
        user_engagement = _get_user_engagement_rate(user)
        if user_engagement < min_engagement:
            return False

    # Max users cap
    max_users = getattr(campaign, "max_users", None)
    if max_users is not None:
        if (campaign.accepted_count or 0) >= max_users:
            return False

    return True


# ── Helper: return existing assignments ───────────────────────────


async def _get_existing_assignments(
    user: User, db: AsyncSession, exclude_ids: set[int]
) -> list[CampaignBrief]:
    """Return existing non-completed assignments for a user."""
    existing_query = (
        select(CampaignAssignment)
        .join(Campaign)
        .where(
            and_(
                CampaignAssignment.user_id == user.id,
                CampaignAssignment.status.in_(
                    ["pending_invitation", "accepted", "content_generated"]
                ),
                Campaign.status == "active",
            )
        )
    )
    existing_result = await db.execute(existing_query)
    existing_assignments = existing_result.scalars().all()

    result = []
    for assignment in existing_assignments:
        if assignment.id in exclude_ids:
            continue
        campaign = assignment.campaign
        result.append(
            CampaignBrief(
                campaign_id=campaign.id,
                assignment_id=assignment.id,
                title=campaign.title,
                brief=campaign.brief,
                assets=campaign.assets,
                content_guidance=campaign.content_guidance,
                payout_rules=campaign.payout_rules,
                payout_multiplier=1.0,
            )
        )
    return result


# ── Main Matching Function ────────────────────────────────────────


async def get_matched_campaigns(
    user: User, db: AsyncSession
) -> list[CampaignBrief]:
    """Match active campaigns to a user and return briefs for assigned campaigns.

    New matches are created with status ``pending_invitation`` (v2 invitation
    model).  Existing non-completed assignments are also returned so the user
    app has a single list of everything relevant.

    Scoring pipeline:
    1. Hard filters (required platforms, followers, region, budget, not already invited)
    2. AI relevance scoring via Gemini (cached for 24h)
    3. Combined score = AI * 0.6 + trust * 0.2 + engagement bonus (capped at 20)
    4. Fallback to niche-overlap if AI fails for a given user
    5. Sort by score, take top 10, create invitations
    """

    # Check if user already has 3+ active campaigns — skip matching if so
    MAX_ACTIVE_FOR_MATCHING = 3
    active_statuses = ("accepted", "content_generated", "posted", "metrics_collected")
    active_count_result = await db.execute(
        select(func.count(CampaignAssignment.id)).where(
            and_(
                CampaignAssignment.user_id == user.id,
                CampaignAssignment.status.in_(active_statuses),
            )
        )
    )
    active_campaign_count = active_count_result.scalar() or 0

    # Get campaigns already assigned to this user
    existing_result = await db.execute(
        select(CampaignAssignment.campaign_id).where(
            CampaignAssignment.user_id == user.id
        )
    )
    existing_campaign_ids = set(existing_result.scalars().all())

    # If at max active campaigns, skip new matching — only return existing
    if active_campaign_count >= MAX_ACTIVE_FOR_MATCHING:
        logger.info("User %d has %d active campaigns (max %d), skipping matching",
                     user.id, active_campaign_count, MAX_ACTIVE_FOR_MATCHING)
        # Jump to returning existing assignments only
        return await _get_existing_assignments(user, db, set())

    # Get all active campaigns
    result = await db.execute(
        select(Campaign).where(Campaign.status == "active")
    )
    active_campaigns = result.scalars().all()

    # Stage 1: Hard filters
    candidates = []
    for campaign in active_campaigns:
        if campaign.id in existing_campaign_ids:
            continue  # Already assigned/invited

        if float(campaign.budget_remaining) <= 0:
            continue

        if not _passes_hard_filters(campaign, user):
            continue

        candidates.append(campaign)

    # Stage 2 + 3: AI scoring + combined score
    engagement_rate = _get_user_engagement_rate(user)
    scored = []

    for campaign in candidates:
        ai_score = await ai_score_relevance(campaign, user)

        if ai_score < 0:
            # AI failed — use fallback niche-overlap scoring
            fallback = _fallback_niche_score(campaign, user)
            final_score = calculate_combined_score(
                ai_score=fallback,
                trust_score=user.trust_score or 50,
                engagement_rate=engagement_rate,
            )
        else:
            final_score = calculate_combined_score(
                ai_score=ai_score,
                trust_score=user.trust_score or 50,
                engagement_rate=engagement_rate,
            )

        if final_score > 0:
            scored.append((campaign, final_score))

    # Sort by score descending, take top 10
    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:10]

    # Create invitation assignments for new matches
    now = datetime.now(timezone.utc)
    new_assignments = []
    for campaign, score in scored:
        content_mode = (
            "ai_generated" if user.mode == "full_auto" else "user_customized"
        )

        assignment = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user.id,
            status="pending_invitation",
            content_mode=content_mode,
            invited_at=now,
            expires_at=now + INVITATION_TTL,
            # payout_multiplier defaults to 1.0 — no longer mode-dependent (v2)
        )
        db.add(assignment)
        await db.flush()

        # Increment campaign invitation counter
        campaign.invitation_count = (campaign.invitation_count or 0) + 1

        # Log the event
        db.add(
            CampaignInvitationLog(
                campaign_id=campaign.id,
                user_id=user.id,
                event="sent",
            )
        )
        await db.flush()

        new_assignments.append(
            CampaignBrief(
                campaign_id=campaign.id,
                assignment_id=assignment.id,
                title=campaign.title,
                brief=campaign.brief,
                assets=campaign.assets,
                content_guidance=campaign.content_guidance,
                payout_rules=campaign.payout_rules,
                payout_multiplier=1.0,
            )
        )

    # Also return existing non-completed assignments (exclude ones we just created)
    newly_created_ids = {a.assignment_id for a in new_assignments}
    existing = await _get_existing_assignments(user, db, newly_created_ids)
    new_assignments.extend(existing)

    return new_assignments
