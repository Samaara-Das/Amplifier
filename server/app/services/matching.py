from sqlalchemy import select, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.schemas.campaign import CampaignBrief


async def get_matched_campaigns(user: User, db: AsyncSession) -> list[CampaignBrief]:
    """Match active campaigns to a user and return briefs for assigned campaigns."""

    # Get campaigns already assigned to this user
    existing_result = await db.execute(
        select(CampaignAssignment.campaign_id).where(
            CampaignAssignment.user_id == user.id
        )
    )
    existing_campaign_ids = set(existing_result.scalars().all())

    # Get all active campaigns
    result = await db.execute(
        select(Campaign).where(Campaign.status == "active")
    )
    active_campaigns = result.scalars().all()

    # Score and filter campaigns for this user
    matched = []
    for campaign in active_campaigns:
        if campaign.id in existing_campaign_ids:
            continue  # Already assigned

        if float(campaign.budget_remaining) <= 0:
            continue

        score = _calculate_match_score(campaign, user)
        if score > 0:
            matched.append((campaign, score))

    # Sort by score descending, take top 10
    matched.sort(key=lambda x: x[1], reverse=True)
    matched = matched[:10]

    # Create assignments for new matches
    new_assignments = []
    for campaign, score in matched:
        # Determine payout multiplier based on user mode
        mode_multipliers = {
            "full_auto": 1.5,  # AI generated
            "semi_auto": 2.0,  # User customized
            "manual": 2.0,     # User customized
        }
        multiplier = mode_multipliers.get(user.mode, 1.5)
        content_mode = "ai_generated" if user.mode == "full_auto" else "user_customized"

        assignment = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user.id,
            content_mode=content_mode,
            payout_multiplier=multiplier,
        )
        db.add(assignment)
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
                payout_multiplier=multiplier,
            )
        )

    # Also return existing non-completed assignments
    existing_result = await db.execute(
        select(CampaignAssignment)
        .join(Campaign)
        .where(
            and_(
                CampaignAssignment.user_id == user.id,
                CampaignAssignment.status.in_(["assigned", "content_generated"]),
                Campaign.status == "active",
            )
        )
    )
    existing_assignments = existing_result.scalars().all()

    for assignment in existing_assignments:
        campaign = assignment.campaign
        new_assignments.append(
            CampaignBrief(
                campaign_id=campaign.id,
                assignment_id=assignment.id,
                title=campaign.title,
                brief=campaign.brief,
                assets=campaign.assets,
                content_guidance=campaign.content_guidance,
                payout_rules=campaign.payout_rules,
                payout_multiplier=float(assignment.payout_multiplier),
            )
        )

    return new_assignments


def _calculate_match_score(campaign: Campaign, user: User) -> int:
    """Score a campaign against a user profile. Returns 0 if hard filter fails."""
    targeting = campaign.targeting or {}
    score = 0

    # Hard filter: required platforms
    required_platforms = targeting.get("required_platforms", [])
    if required_platforms:
        user_platforms = set(
            k for k, v in (user.platforms or {}).items()
            if isinstance(v, dict) and v.get("connected")
        )
        if not set(required_platforms).issubset(user_platforms):
            return 0

    # Hard filter: minimum follower counts
    min_followers = targeting.get("min_followers", {})
    user_followers = user.follower_counts or {}
    for platform, minimum in min_followers.items():
        if user_followers.get(platform, 0) < minimum:
            return 0

    # Soft: niche overlap
    target_niches = set(targeting.get("niche_tags", []))
    user_niches = set(user.niche_tags or [])
    niche_overlap = len(target_niches & user_niches)
    score += niche_overlap * 30

    # If no niche targeting, give a base score so everyone can participate
    if not target_niches:
        score += 10

    # Soft: trust score
    score += (user.trust_score or 50) * 0.5

    # Ensure minimum score of 1 if hard filters passed
    return max(score, 1)
