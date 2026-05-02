from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.schemas.user import UserProfileUpdate, UserProfileResponse, PayoutRequest

router = APIRouter()
settings = get_settings()


@router.get("/me", response_model=UserProfileResponse)
async def get_profile(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.platforms is not None:
        user.platforms = data.platforms
    if data.follower_counts is not None:
        user.follower_counts = data.follower_counts
    if data.niche_tags is not None:
        user.niche_tags = data.niche_tags
    if data.audience_region is not None:
        user.audience_region = data.audience_region
    if data.mode is not None:
        if data.mode not in ("full_auto", "semi_auto", "manual"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        user.mode = data.mode
    if data.device_fingerprint is not None:
        user.device_fingerprint = data.device_fingerprint
    if data.scraped_profiles is not None:
        user.scraped_profiles = data.scraped_profiles
        user.last_scraped_at = datetime.now(timezone.utc)
    if data.ai_detected_niches is not None:
        user.ai_detected_niches = data.ai_detected_niches
    if data.subscription_tier is not None:
        if data.subscription_tier not in ("free", "pro"):
            raise HTTPException(status_code=400, detail="Invalid subscription tier")
        user.subscription_tier = data.subscription_tier
    if data.zip_code is not None:
        user.zip_code = data.zip_code
    if data.state is not None:
        user.state = data.state

    await db.flush()
    return user


@router.get("/me/earnings")
async def get_earnings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's earnings summary with real breakdowns.

    - total_earned / current_balance: from user model
    - pending: estimated earnings from non-final metrics (not yet billed)
    - per_campaign: aggregated from payout records, grouped by campaign
    - per_platform: aggregated from payout breakdown JSON
    - payout_history: withdrawal records (breakdown.withdrawal=true)
    """
    # ── Pending: sum of payouts in 7-day hold ──────────────────────
    pending = await _calculate_pending(db, user.id)

    # ── Available: sum of payouts past the hold period ────────────
    available = await _calculate_available(db, user.id)

    # ── Per-campaign breakdown from payouts ───────────────────────
    per_campaign = await _build_per_campaign(db, user.id)

    # ── Per-platform breakdown from payout breakdown JSON ─────────
    per_platform = await _build_per_platform(db, user.id)

    # ── Payout history (withdrawal records) ───────────────────────
    payout_history = await _build_payout_history(db, user.id)

    return {
        "total_earned": float(user.total_earned),
        "current_balance": float(user.earnings_balance),
        "available_balance": available,
        "pending": pending,
        "per_campaign": per_campaign,
        "per_platform": per_platform,
        "payout_history": payout_history,
    }


@router.post("/me/payout")
async def request_payout(
    data: PayoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request a payout withdrawal from the user's earnings balance."""
    balance = float(user.earnings_balance)
    amount = data.amount

    # Validation
    if not user.stripe_account_id:
        raise HTTPException(
            status_code=400,
            detail="Stripe Connect bank account not linked. Please complete onboarding to enable payouts.",
        )
    if amount < 10.0:
        raise HTTPException(
            status_code=400,
            detail="Insufficient balance. Minimum withdrawal is $10.00",
        )
    if balance < 10.0:
        raise HTTPException(
            status_code=400,
            detail="Insufficient balance. Minimum withdrawal is $10.00",
        )
    if amount > balance:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. You have ${balance:.2f} available.",
        )

    # Create payout record
    now = datetime.now(timezone.utc)
    amount_cents = int(amount * 100)
    payout = Payout(
        user_id=user.id,
        campaign_id=None,
        amount=amount,
        amount_cents=amount_cents,
        period_start=now,
        period_end=now,
        status="processing",
        breakdown={"withdrawal": True, "requested_via": "user_withdraw"},
    )
    db.add(payout)

    # Deduct from balance (both float and cents columns)
    user.earnings_balance = balance - amount
    user.earnings_balance_cents = max(0, (user.earnings_balance_cents or 0) - amount_cents)

    await db.flush()

    return {
        "payout_id": payout.id,
        "amount": float(payout.amount),
        "status": payout.status,
        "new_balance": float(user.earnings_balance),
    }


# ── Helper functions ──────────────────────────────────────────────


async def _calculate_pending(db: AsyncSession, user_id: int) -> float:
    """Sum of pending payouts (within 7-day hold period, not yet available).

    Uses actual payout records rather than re-estimating from metrics.
    Billing runs on every metric submission, so payouts are always up-to-date.
    """
    total = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0))
        .where(
            and_(
                Payout.user_id == user_id,
                Payout.status == "pending",
                Payout.campaign_id.isnot(None),
            )
        )
    )
    return round(float(total), 2)


async def _calculate_available(db: AsyncSession, user_id: int) -> float:
    """Sum of available payouts (past the 7-day hold, ready for withdrawal)."""
    total = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0))
        .where(
            and_(
                Payout.user_id == user_id,
                Payout.status == "available",
                Payout.campaign_id.isnot(None),
            )
        )
    )
    return round(float(total), 2)


async def _build_per_campaign(db: AsyncSession, user_id: int) -> list[dict]:
    """Aggregate payout records by campaign, joining with Campaign for title.

    Only includes payouts with a campaign_id (excludes withdrawals).
    """
    result = await db.execute(
        select(Payout, Campaign)
        .join(Campaign, Payout.campaign_id == Campaign.id)
        .where(
            and_(
                Payout.user_id == user_id,
                Payout.campaign_id.is_not(None),
            )
        )
    )
    rows = result.all()

    # Group by campaign_id
    campaign_data: dict[int, dict] = {}
    for payout, campaign in rows:
        cid = campaign.id
        if cid not in campaign_data:
            campaign_data[cid] = {
                "campaign_id": cid,
                "campaign_title": campaign.title,
                "posts": 0,
                "impressions": 0,
                "engagement": 0,
                "earned": 0.0,
                "status": "pending",
            }

        breakdown = payout.breakdown or {}
        campaign_data[cid]["posts"] += 1
        campaign_data[cid]["impressions"] += breakdown.get("impressions", 0)
        # engagement = likes + reposts + clicks
        campaign_data[cid]["engagement"] += (
            breakdown.get("likes", 0) +
            breakdown.get("reposts", 0) +
            breakdown.get("clicks", 0)
        )
        campaign_data[cid]["earned"] += float(payout.amount)

        # Status: "paid" if any payout is paid, otherwise keep as pending/calculated
        if payout.status == "paid":
            campaign_data[cid]["status"] = "paid"

    # Round earned amounts
    for cid in campaign_data:
        campaign_data[cid]["earned"] = round(campaign_data[cid]["earned"], 2)

    # Also check assignment status for status field
    if campaign_data:
        assign_result = await db.execute(
            select(CampaignAssignment)
            .where(
                and_(
                    CampaignAssignment.user_id == user_id,
                    CampaignAssignment.campaign_id.in_(campaign_data.keys()),
                )
            )
        )
        for assignment in assign_result.scalars().all():
            cid = assignment.campaign_id
            if cid in campaign_data:
                if assignment.status == "paid":
                    campaign_data[cid]["status"] = "paid"
                elif assignment.status == "posted" and campaign_data[cid]["status"] != "paid":
                    campaign_data[cid]["status"] = "calculated"

    return list(campaign_data.values())


async def _build_per_platform(db: AsyncSession, user_id: int) -> dict[str, float]:
    """Sum earned per platform from payout breakdown JSON.

    Only includes payouts with a 'platform' key in breakdown (excludes withdrawals).
    """
    result = await db.execute(
        select(Payout).where(Payout.user_id == user_id)
    )
    payouts = result.scalars().all()

    platform_totals: dict[str, float] = defaultdict(float)
    for payout in payouts:
        breakdown = payout.breakdown or {}
        platform = breakdown.get("platform")
        if platform:
            platform_totals[platform] += float(payout.amount)

    # Round values
    return {k: round(v, 2) for k, v in platform_totals.items()}


async def _build_payout_history(db: AsyncSession, user_id: int) -> list[dict]:
    """Return withdrawal payout records (breakdown.withdrawal=true)."""
    result = await db.execute(
        select(Payout).where(Payout.user_id == user_id)
    )
    payouts = result.scalars().all()

    history = []
    for payout in payouts:
        breakdown = payout.breakdown or {}
        if breakdown.get("withdrawal"):
            history.append({
                "id": payout.id,
                "amount": float(payout.amount),
                "status": payout.status,
                "requested_at": payout.created_at.isoformat() if payout.created_at else None,
            })

    return history
