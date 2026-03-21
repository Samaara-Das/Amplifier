"""Billing engine — calculates earnings from metrics and processes payouts."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.post import Post
from app.models.metric import Metric
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.models.payout import Payout

logger = logging.getLogger(__name__)
settings = get_settings()


async def calculate_post_earnings(post: Post, metric: Metric, assignment: CampaignAssignment,
                                  campaign: Campaign) -> float:
    """Calculate earnings for a single post based on its final metrics and payout rules."""
    rules = campaign.payout_rules or {}
    multiplier = float(assignment.payout_multiplier or 1.0)

    rate_per_1k_imp = rules.get("rate_per_1k_impressions", 0)
    rate_per_like = rules.get("rate_per_like", 0)
    rate_per_repost = rules.get("rate_per_repost", 0)
    rate_per_click = rules.get("rate_per_click", 0)

    raw_earning = (
        (metric.impressions / 1000.0 * rate_per_1k_imp) +
        (metric.likes * rate_per_like) +
        (metric.reposts * rate_per_repost) +
        (metric.clicks * rate_per_click)
    )

    # Apply content mode multiplier
    earning = raw_earning * multiplier

    # Apply platform cut
    platform_cut = settings.platform_cut_percent / 100.0
    user_earning = earning * (1 - platform_cut)

    return round(user_earning, 2)


async def run_billing_cycle(db: AsyncSession) -> dict:
    """Process all posts with final metrics that haven't been billed yet.

    Returns summary: {posts_processed, total_earned, total_deducted_from_budgets}
    """
    # Find final metrics that haven't been billed yet
    # A metric is "billed" if a payout record references it in the breakdown
    # We track billed metric IDs via a JSON field in the payout breakdown
    result = await db.execute(
        select(Metric, Post, CampaignAssignment, Campaign)
        .join(Post, Metric.post_id == Post.id)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .where(
            and_(
                Metric.is_final == True,
                Post.status == "live",
            )
        )
    )
    rows = result.all()

    # Get all existing payout metric IDs to skip already-billed metrics
    existing_payouts = await db.execute(select(Payout))
    billed_metric_ids = set()
    for p in existing_payouts.scalars().all():
        breakdown = p.breakdown or {}
        if "metric_id" in breakdown:
            billed_metric_ids.add(breakdown["metric_id"])

    posts_processed = 0
    total_earned = 0.0
    total_budget_deducted = 0.0

    for metric, post, assignment, campaign in rows:
        # Check if this specific metric was already billed
        if metric.id in billed_metric_ids:
            continue

        # Check campaign budget
        if float(campaign.budget_remaining) <= 0:
            continue

        earning = await calculate_post_earnings(post, metric, assignment, campaign)
        if earning <= 0:
            continue

        # Cap earning to remaining budget
        budget_cost = earning / (1 - settings.platform_cut_percent / 100.0)
        if budget_cost > float(campaign.budget_remaining):
            budget_cost = float(campaign.budget_remaining)
            earning = budget_cost * (1 - settings.platform_cut_percent / 100.0)

        # Credit user
        user_result = await db.execute(
            select(User).where(User.id == assignment.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        user.earnings_balance = float(user.earnings_balance) + earning
        user.total_earned = float(user.total_earned) + earning

        # Deduct from campaign budget
        campaign.budget_remaining = float(campaign.budget_remaining) - budget_cost

        # Auto-pause campaign if budget is low
        if float(campaign.budget_remaining) < 1.0:
            campaign.status = "completed"

        # Create payout record
        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=assignment.user_id,
            campaign_id=campaign.id,
            amount=earning,
            period_start=post.posted_at,
            period_end=now,
            status="pending",
            breakdown={
                "metric_id": metric.id,
                "post_id": post.id,
                "platform": post.platform,
                "impressions": metric.impressions,
                "likes": metric.likes,
                "reposts": metric.reposts,
                "clicks": metric.clicks,
                "multiplier": float(assignment.payout_multiplier),
                "platform_cut_pct": settings.platform_cut_percent,
            },
        )
        db.add(payout)

        # Update assignment status
        assignment.status = "paid"

        posts_processed += 1
        total_earned += earning
        total_budget_deducted += budget_cost

    await db.flush()

    logger.info(
        "Billing cycle complete: %d posts, $%.2f earned, $%.2f deducted from budgets",
        posts_processed, total_earned, total_budget_deducted,
    )

    return {
        "posts_processed": posts_processed,
        "total_earned": total_earned,
        "total_budget_deducted": total_budget_deducted,
    }
