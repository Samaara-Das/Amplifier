import os
from typing import Optional

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.campaign import Campaign
from app.models.company import Company
from app.models.post import Post
from app.models.payout import Payout
from app.models.penalty import Penalty

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


async def require_admin(admin_token: str | None = Cookie(None)):
    """Verify admin authentication via cookie (same as admin pages)."""
    if not admin_token or admin_token != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Admin authentication required")


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/users")
async def list_users(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    if status:
        query = query.where(User.status == status)
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "trust_score": u.trust_score,
            "mode": u.mode,
            "total_earned": float(u.total_earned),
            "status": u.status,
            "platforms": u.platforms,
            "follower_counts": u.follower_counts,
        }
        for u in users
    ]


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "suspended"
    await db.flush()
    return {"status": "suspended", "user_id": user_id}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "suspended":
        raise HTTPException(status_code=400, detail="User is not suspended")
    user.status = "active"
    await db.flush()
    return {"status": "active", "user_id": user_id}


@router.get("/stats")
async def system_stats(db: AsyncSession = Depends(get_db)):
    user_count = await db.scalar(select(func.count()).select_from(User))
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.status == "active")
    )
    campaign_count = await db.scalar(select(func.count()).select_from(Campaign))
    active_campaigns = await db.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.status == "active")
    )
    total_posts = await db.scalar(select(func.count()).select_from(Post))
    total_payouts = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0)).select_from(Payout)
    )

    return {
        "users": {"total": user_count, "active": active_users},
        "campaigns": {"total": campaign_count, "active": active_campaigns},
        "posts": {"total": total_posts},
        "payouts": {"total": float(total_payouts)},
    }


# ── Flagged campaign review endpoints ────────────────────────────


@router.get("/flagged-campaigns")
async def list_flagged_campaigns(
    status: str = Query("pending_review", description="Filter: pending_review, approved, rejected"),
    db: AsyncSession = Depends(get_db),
):
    """List campaigns flagged by automated content screening."""
    if status == "pending_review":
        query = (
            select(ContentScreeningLog, Campaign, Company)
            .join(Campaign, ContentScreeningLog.campaign_id == Campaign.id)
            .join(Company, Campaign.company_id == Company.id)
            .where(
                and_(
                    ContentScreeningLog.flagged == True,
                    ContentScreeningLog.reviewed_by_admin == False,
                )
            )
            .order_by(ContentScreeningLog.created_at.desc())
        )
    elif status == "approved":
        query = (
            select(ContentScreeningLog, Campaign, Company)
            .join(Campaign, ContentScreeningLog.campaign_id == Campaign.id)
            .join(Company, Campaign.company_id == Company.id)
            .where(ContentScreeningLog.review_result == "approved")
            .order_by(ContentScreeningLog.created_at.desc())
        )
    elif status == "rejected":
        query = (
            select(ContentScreeningLog, Campaign, Company)
            .join(Campaign, ContentScreeningLog.campaign_id == Campaign.id)
            .join(Company, Campaign.company_id == Company.id)
            .where(ContentScreeningLog.review_result == "rejected")
            .order_by(ContentScreeningLog.created_at.desc())
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid status filter")

    result = await db.execute(query)
    items = []
    for log, campaign, company in result.all():
        items.append({
            "campaign_id": campaign.id,
            "company_id": company.id,
            "company_name": company.name,
            "title": campaign.title,
            "brief": campaign.brief,
            "screening_flags": [
                {
                    "category": cat,
                    "matched_phrases": [
                        kw for kw in (log.flagged_keywords or [])
                        if kw in _keywords_for_category(cat)
                    ],
                }
                for cat in (log.screening_categories or [])
            ],
            "screening_status": campaign.screening_status,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return items


@router.post("/flagged-campaigns/{campaign_id}/approve")
async def approve_flagged_campaign(
    campaign_id: int,
    notes: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
):
    """Approve a flagged campaign, allowing activation."""
    result = await db.execute(
        select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Campaign not found or not screened")

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.screening_status != "flagged":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is not in flagged screening status (current: {campaign.screening_status})",
        )

    log.reviewed_by_admin = True
    log.review_result = "approved"
    log.review_notes = notes

    campaign.screening_status = "approved"
    await db.flush()

    return {
        "campaign_id": campaign_id,
        "screening_status": "approved",
        "message": "Campaign approved for activation.",
    }


@router.post("/flagged-campaigns/{campaign_id}/reject")
async def reject_flagged_campaign(
    campaign_id: int,
    reason: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
):
    """Reject a flagged campaign. Sets campaign status to cancelled and refunds budget."""
    result = await db.execute(
        select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Campaign not found or not screened")

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.screening_status != "flagged":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is not in flagged screening status (current: {campaign.screening_status})",
        )

    log.reviewed_by_admin = True
    log.review_result = "rejected"
    log.review_notes = reason

    campaign.screening_status = "rejected"
    campaign.status = "cancelled"

    # Refund budget to company
    company_result = await db.execute(
        select(Company).where(Company.id == campaign.company_id)
    )
    company = company_result.scalar_one_or_none()
    if company:
        company.balance = float(company.balance) + float(campaign.budget_remaining)

    await db.flush()

    return {
        "campaign_id": campaign_id,
        "screening_status": "rejected",
        "message": "Campaign rejected. Company will be notified.",
    }


def _keywords_for_category(category: str) -> list[str]:
    """Helper to get keyword list for a screening category."""
    from app.services.content_screening import PROHIBITED_KEYWORDS
    return PROHIBITED_KEYWORDS.get(category, [])
