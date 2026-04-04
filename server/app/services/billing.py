"""Billing engine — calculates earnings from metrics and processes payouts.

v2/v3 upgrade: earnings use integer cents, 7-day hold period before payout.
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.post import Post
from app.models.metric import Metric
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.models.payout import Payout, EARNING_HOLD_DAYS

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Reputation Tiers (v2/v3 upgrade) ──────────────────────────────────────

TIER_CONFIG = {
    "seedling": {"max_campaigns": 3, "spot_check_pct": 30, "cpm_multiplier": 1.0,
                 "auto_post_allowed": False},
    "grower":   {"max_campaigns": 10, "spot_check_pct": 10, "cpm_multiplier": 1.0,
                 "auto_post_allowed": True},
    "amplifier": {"max_campaigns": 999, "spot_check_pct": 5, "cpm_multiplier": 2.0,
                  "auto_post_allowed": True},
}


# ── Subscription Tiers (orthogonal to reputation tiers) ─────────────────

SUBSCRIPTION_TIERS = {
    "free": {
        "max_campaigns_override": None,  # uses reputation tier limit
        "image_gen_enabled": False,
        "advanced_analytics": False,
        "priority_matching": False,
        "max_posts_per_day": 4,
        "price_cents_monthly": 0,
    },
    "pro": {
        "max_campaigns_override": 20,  # overrides reputation tier if higher
        "image_gen_enabled": True,
        "advanced_analytics": True,
        "priority_matching": True,
        "max_posts_per_day": 20,
        "price_cents_monthly": 1999,  # $19.99/mo
    },
}


def get_effective_max_campaigns(user) -> int:
    """Get effective max campaigns combining reputation + subscription tiers."""
    rep_tier = getattr(user, "tier", "seedling") or "seedling"
    sub_tier = getattr(user, "subscription_tier", "free") or "free"
    rep_max = TIER_CONFIG.get(rep_tier, TIER_CONFIG["seedling"])["max_campaigns"]
    sub_override = SUBSCRIPTION_TIERS.get(sub_tier, SUBSCRIPTION_TIERS["free"])["max_campaigns_override"]
    if sub_override is not None:
        return max(rep_max, sub_override)
    return rep_max


def get_tier_config(tier: str) -> dict:
    """Get configuration for a user's reputation tier."""
    return TIER_CONFIG.get(tier, TIER_CONFIG["seedling"])


def _check_tier_promotion(user) -> None:
    """Promote user to a higher tier if they meet the criteria.

    Seedling → Grower: 20 successful posts
    Grower → Amplifier: 100 successful posts + trust_score >= 80
    """
    current = getattr(user, "tier", "seedling") or "seedling"
    posts = getattr(user, "successful_post_count", 0) or 0
    trust = getattr(user, "trust_score", 50) or 50

    if current == "seedling" and posts >= 20:
        user.tier = "grower"
        logger.info("User %d promoted to GROWER (%d posts)", user.id, posts)
    elif current == "grower" and posts >= 100 and trust >= 80:
        user.tier = "amplifier"
        logger.info("User %d promoted to AMPLIFIER (%d posts, trust=%d)", user.id, posts, trust)


def get_cpm_multiplier(user) -> float:
    """Get CPM multiplier for a user's tier. Amplifier gets 2x."""
    tier = getattr(user, "tier", "seedling") or "seedling"
    return TIER_CONFIG.get(tier, TIER_CONFIG["seedling"])["cpm_multiplier"]


def calculate_post_earnings_cents(metric: Metric, campaign: Campaign) -> int:
    """Calculate earnings for a single post in integer cents.

    Returns user's share in cents (after platform cut).
    v2 pattern: all money math in cents to eliminate float rounding.
    """
    rules = campaign.payout_rules or {}

    # Rates are stored as dollars (float) in campaign — convert to cents for math
    rate_per_1k_imp_cents = int(rules.get("rate_per_1k_impressions", 0) * 100)
    rate_per_like_cents = int(rules.get("rate_per_like", 0) * 100)
    rate_per_repost_cents = int(rules.get("rate_per_repost", 0) * 100)
    rate_per_click_cents = int(rules.get("rate_per_click", 0) * 100)

    raw_cents = (
        (metric.impressions * rate_per_1k_imp_cents // 1000) +
        (metric.likes * rate_per_like_cents) +
        (metric.reposts * rate_per_repost_cents) +
        (metric.clicks * rate_per_click_cents)
    )

    # Apply platform cut
    platform_cut_pct = settings.platform_cut_percent  # e.g. 20
    user_cents = raw_cents * (100 - platform_cut_pct) // 100

    return user_cents


async def calculate_post_earnings(post: Post, metric: Metric, assignment: CampaignAssignment,
                                  campaign: Campaign) -> float:
    """Calculate earnings for a single post. Returns dollars (float) for backward compat.

    Internally uses cents for precision, converts to float for legacy callers.
    """
    cents = calculate_post_earnings_cents(metric, campaign)
    return cents / 100.0


async def run_billing_cycle(db: AsyncSession) -> dict:
    """Process all posts with final metrics that haven't been billed yet.

    Returns summary: {posts_processed, total_earned, total_deducted_from_budgets}
    """
    # Find metrics that haven't been billed yet.
    # Billing is incremental: each metric submission gets billed based on the
    # latest engagement numbers. We track billed metric IDs to avoid double-billing.
    result = await db.execute(
        select(Metric, Post, CampaignAssignment, Campaign)
        .join(Post, Metric.post_id == Post.id)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
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

        # Load user first (needed for CPM multiplier)
        user_result = await db.execute(
            select(User).where(User.id == assignment.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        # Compute in cents for precision
        earning_cents = calculate_post_earnings_cents(metric, campaign)

        # Apply tier CPM multiplier (amplifier tier gets 2x)
        cpm_mult = get_cpm_multiplier(user)
        earning_cents = int(earning_cents * cpm_mult)

        earning = earning_cents / 100.0
        if earning_cents <= 0:
            continue

        # Cap earning to remaining budget (in cents)
        budget_remaining_cents = int(float(campaign.budget_remaining) * 100)
        platform_cut_pct = settings.platform_cut_percent
        budget_cost_cents = earning_cents * 100 // (100 - platform_cut_pct)
        if budget_cost_cents > budget_remaining_cents:
            budget_cost_cents = budget_remaining_cents
            earning_cents = budget_cost_cents * (100 - platform_cut_pct) // 100
            earning = earning_cents / 100.0

        budget_cost = budget_cost_cents / 100.0

        user.earnings_balance = float(user.earnings_balance) + earning
        user.earnings_balance_cents = (user.earnings_balance_cents or 0) + earning_cents
        user.total_earned = float(user.total_earned) + earning
        user.total_earned_cents = (user.total_earned_cents or 0) + earning_cents

        # Deduct from campaign budget
        campaign.budget_remaining = float(campaign.budget_remaining) - budget_cost

        # Budget exhaustion: auto_pause vs auto_complete
        if float(campaign.budget_remaining) < 1.0:
            action = getattr(campaign, "budget_exhaustion_action", "auto_complete") or "auto_complete"
            if action == "auto_pause":
                campaign.status = "paused"
            else:
                campaign.status = "completed"

        # 80% budget alert: flag when remaining < 20% of total
        budget_total = float(campaign.budget_total) if campaign.budget_total else 0
        if budget_total > 0 and not getattr(campaign, "budget_alert_sent", True):
            if float(campaign.budget_remaining) < 0.2 * budget_total:
                campaign.budget_alert_sent = True

        # Create payout record with hold period (v2 pattern)
        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=assignment.user_id,
            campaign_id=campaign.id,
            amount=earning,
            amount_cents=earning_cents,
            period_start=post.posted_at,
            period_end=now,
            status="pending",
            available_at=now + timedelta(days=EARNING_HOLD_DAYS),
            breakdown={
                "metric_id": metric.id,
                "post_id": post.id,
                "platform": post.platform,
                "impressions": metric.impressions,
                "likes": metric.likes,
                "reposts": metric.reposts,
                "clicks": metric.clicks,
                "platform_cut_pct": settings.platform_cut_percent,
                "earning_cents": earning_cents,
                "budget_cost_cents": budget_cost_cents,
            },
        )
        db.add(payout)

        # Update assignment status
        assignment.status = "paid"

        # Increment successful post count and check tier promotion
        user.successful_post_count = (user.successful_post_count or 0) + 1
        _check_tier_promotion(user)

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


async def promote_pending_earnings(db: AsyncSession) -> int:
    """Move 'pending' earnings to 'available' after hold period expires.

    v2 pattern: runs periodically (every 10 min via background task).
    Returns count of promoted payouts.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Payout).where(
            and_(
                Payout.status == "pending",
                Payout.available_at <= now,
            )
        )
    )
    payouts = result.scalars().all()

    for payout in payouts:
        payout.status = "available"

    if payouts:
        await db.flush()
        logger.info("Promoted %d pending earnings to available", len(payouts))

    return len(payouts)


async def void_earnings_for_post(db: AsyncSession, post_id: int) -> int:
    """Void pending earnings for a post (fraud detected during hold period).

    Returns funds to campaign budget. Only affects 'pending' payouts — if the
    hold period already passed, the earning is available and can't be voided.
    """
    result = await db.execute(
        select(Payout).where(Payout.status == "pending")
    )
    voided = 0
    for payout in result.scalars().all():
        breakdown = payout.breakdown or {}
        if breakdown.get("post_id") == post_id:
            payout.status = "voided"

            # Return funds to campaign budget
            if payout.campaign_id:
                camp_result = await db.execute(
                    select(Campaign).where(Campaign.id == payout.campaign_id)
                )
                campaign = camp_result.scalar_one_or_none()
                if campaign:
                    budget_cost_cents = breakdown.get("budget_cost_cents", 0)
                    campaign.budget_remaining = float(campaign.budget_remaining) + (budget_cost_cents / 100.0)

            # Deduct from user balance
            user_result = await db.execute(
                select(User).where(User.id == payout.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                earning = payout.amount_cents / 100.0 if payout.amount_cents else float(payout.amount)
                user.earnings_balance = max(0, float(user.earnings_balance) - earning)
                user.total_earned = max(0, float(user.total_earned) - earning)

            voided += 1
            logger.info("Voided payout %d for post %d ($%.2f)", payout.id, post_id, float(payout.amount))

    if voided:
        await db.flush()

    return voided
