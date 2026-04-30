"""Creator earnings page."""

from collections import defaultdict

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.payout import Payout
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.routers.user import _render, _login_redirect, get_user_from_cookie

router = APIRouter()


@router.get("/earnings", response_class=HTMLResponse)
async def earnings_page(
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    # Pending (in 7-day hold)
    pending_cents = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount_cents), 0)).where(
            and_(
                Payout.user_id == user.id,
                Payout.status == "pending",
                Payout.campaign_id.isnot(None),
            )
        )
    ) or 0

    # Available for withdrawal
    available_cents = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount_cents), 0)).where(
            and_(
                Payout.user_id == user.id,
                Payout.status == "available",
                Payout.campaign_id.isnot(None),
            )
        )
    ) or 0

    # Per-campaign breakdown
    campaign_breakdown = await _build_campaign_breakdown(db, user.id)

    # Payout history (withdrawals)
    payout_history = await _build_payout_history(db, user.id)

    return _render(
        "user/earnings.html",
        user=user,
        active_page="earnings",
        total_earned_cents=user.total_earned_cents,
        available_cents=available_cents,
        pending_cents=pending_cents,
        campaign_breakdown=campaign_breakdown,
        payout_history=payout_history,
    )


async def _build_campaign_breakdown(db, user_id):
    result = await db.execute(
        select(Payout, Campaign)
        .join(Campaign, Payout.campaign_id == Campaign.id)
        .where(
            and_(
                Payout.user_id == user_id,
                Payout.campaign_id.isnot(None),
            )
        )
    )
    rows = result.all()

    campaign_data: dict[int, dict] = {}
    for payout, campaign in rows:
        cid = campaign.id
        if cid not in campaign_data:
            campaign_data[cid] = {
                "campaign_id": cid,
                "campaign_title": campaign.title,
                "earned_cents": 0,
                "status": payout.status,
            }
        campaign_data[cid]["earned_cents"] += payout.amount_cents
        if payout.status == "paid":
            campaign_data[cid]["status"] = "paid"

    return list(campaign_data.values())


async def _build_payout_history(db, user_id):
    result = await db.execute(
        select(Payout).where(Payout.user_id == user_id).order_by(Payout.created_at.desc())
    )
    payouts = result.scalars().all()
    history = []
    for p in payouts:
        breakdown = p.breakdown or {}
        if breakdown.get("withdrawal"):
            history.append({
                "id": p.id,
                "amount_cents": p.amount_cents,
                "status": p.status,
                "requested_at": p.created_at,
            })
    return history
