from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_company, get_current_user
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.models.company import Company
from app.schemas.campaign import CampaignCreate, CampaignUpdate, CampaignResponse, CampaignBrief
from app.services.matching import get_matched_campaigns

router = APIRouter()


# ── Company endpoints ──────────────────────────────────────────────


@router.post("/company/campaigns", response_model=CampaignResponse)
async def create_campaign(
    data: CampaignCreate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    if float(company.balance) < data.budget_total:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    campaign = Campaign(
        company_id=company.id,
        title=data.title,
        brief=data.brief,
        assets=data.assets,
        budget_total=data.budget_total,
        budget_remaining=data.budget_total,
        payout_rules=data.payout_rules.model_dump(),
        targeting=data.targeting.model_dump(),
        content_guidance=data.content_guidance,
        penalty_rules=data.penalty_rules,
        start_date=data.start_date,
        end_date=data.end_date,
        status="draft",
    )
    db.add(campaign)

    # Deduct budget from company balance
    company.balance = float(company.balance) - data.budget_total
    await db.flush()

    return campaign


@router.get("/company/campaigns", response_model=list[CampaignResponse])
async def list_company_campaigns(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.company_id == company.id).order_by(Campaign.created_at.desc())
    )
    return result.scalars().all()


@router.get("/company/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_company_campaign(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/company/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate status transitions
    if data.status:
        valid_transitions = {
            "draft": ["active", "cancelled"],
            "active": ["paused", "cancelled"],
            "paused": ["active", "cancelled"],
        }
        allowed = valid_transitions.get(campaign.status, [])
        if data.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {campaign.status} to {data.status}",
            )
        campaign.status = data.status

    if data.title is not None:
        campaign.title = data.title
    if data.brief is not None:
        campaign.brief = data.brief
    if data.assets is not None:
        campaign.assets = data.assets
    if data.content_guidance is not None:
        campaign.content_guidance = data.content_guidance

    await db.flush()
    return campaign


# ── User endpoints ─────────────────────────────────────────────────


@router.get("/campaigns/mine", response_model=list[CampaignBrief])
async def get_my_campaigns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll for campaigns matched to this user. Creates assignments for new matches."""
    return await get_matched_campaigns(user, db)


@router.patch("/campaigns/assignments/{assignment_id}")
async def update_assignment_status(
    assignment_id: int,
    status: str = Query(..., description="New status"),
    content_mode: str | None = Query(None, description="Content mode if changed"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CampaignAssignment).where(
            and_(
                CampaignAssignment.id == assignment_id,
                CampaignAssignment.user_id == user.id,
            )
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    valid_statuses = ["content_generated", "posted", "skipped"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    assignment.status = status

    if content_mode:
        assignment.content_mode = content_mode
        # Update payout multiplier based on content mode
        multipliers = {"repost": 1.0, "ai_generated": 1.5, "user_customized": 2.0}
        assignment.payout_multiplier = multipliers.get(content_mode, 1.5)

    await db.flush()
    return {"status": "updated", "assignment_id": assignment_id}
