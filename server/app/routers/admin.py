from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.campaign import Campaign
from app.models.post import Post
from app.models.payout import Payout

router = APIRouter()

# TODO: Add admin auth dependency (separate from user/company auth)
# For MVP, these endpoints exist but need proper admin authentication


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
