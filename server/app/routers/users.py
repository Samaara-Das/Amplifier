from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserProfileUpdate, UserProfileResponse

router = APIRouter()


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
    if data.mode is not None:
        if data.mode not in ("full_auto", "semi_auto", "manual"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid mode")
        user.mode = data.mode
    if data.device_fingerprint is not None:
        user.device_fingerprint = data.device_fingerprint

    await db.flush()
    return user


@router.get("/me/earnings")
async def get_earnings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Simple summary — will be enriched when billing engine is built
    return {
        "total_earned": float(user.total_earned),
        "current_balance": float(user.earnings_balance),
        "pending": 0.0,  # TODO: calculate from unpaid metrics
        "per_campaign": [],  # TODO: aggregate from payouts
    }
