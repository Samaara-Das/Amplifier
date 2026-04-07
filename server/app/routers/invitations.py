"""Campaign invitation endpoints — user-facing.

Replaces the old auto-assign model with an explicit invitation flow:
  - GET  /invitations          — pending invitations for current user
  - POST /invitations/{id}/accept
  - POST /invitations/{id}/reject
  - GET  /active               — user's active (accepted) campaigns
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.assignment import CampaignAssignment
from app.models.campaign import Campaign
from app.models.invitation_log import CampaignInvitationLog
from app.models.user import User

router = APIRouter()

# Statuses considered "active" for the 5-campaign cap
ACTIVE_STATUSES = ("accepted", "content_generated", "posted", "metrics_collected")
MAX_ACTIVE_CAMPAIGNS = 3


# ── Helpers ───────────────────────────────────────────────────────


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (for SQLite compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_expired(expires_at: datetime | None) -> bool:
    """Check if an expiry timestamp has passed (handles both naive and aware)."""
    if expires_at is None:
        return False
    now = _utcnow()
    # Strip tzinfo for comparison if needed (SQLite returns naive datetimes)
    exp = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
    return exp < now


async def _expire_stale_invitations(user_id: int, db: AsyncSession) -> None:
    """Auto-expire any pending invitations whose expires_at has passed.

    Updates each expired assignment's status and increments the campaign's
    expired_count counter.
    """
    now = _utcnow()
    result = await db.execute(
        select(CampaignAssignment).where(
            and_(
                CampaignAssignment.user_id == user_id,
                CampaignAssignment.status == "pending_invitation",
                CampaignAssignment.expires_at != None,  # noqa: E711
                CampaignAssignment.expires_at < now,
            )
        )
    )
    stale = result.scalars().all()

    for assignment in stale:
        assignment.status = "expired"

        # Increment campaign counter
        camp_result = await db.execute(
            select(Campaign).where(Campaign.id == assignment.campaign_id)
        )
        campaign = camp_result.scalar_one_or_none()
        if campaign:
            campaign.expired_count = (campaign.expired_count or 0) + 1

        # Log the event
        db.add(CampaignInvitationLog(
            campaign_id=assignment.campaign_id,
            user_id=user_id,
            event="expired",
        ))

    if stale:
        await db.flush()


async def _get_assignment_for_user(
    assignment_id: int, user_id: int, db: AsyncSession
) -> CampaignAssignment:
    """Fetch an assignment that belongs to *this* user, or raise 404."""
    result = await db.execute(
        select(CampaignAssignment).where(
            and_(
                CampaignAssignment.id == assignment_id,
                CampaignAssignment.user_id == user_id,
            )
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return assignment


async def _count_active_campaigns(user_id: int, db: AsyncSession) -> int:
    """Count how many campaigns the user currently has in active statuses."""
    result = await db.execute(
        select(CampaignAssignment).where(
            and_(
                CampaignAssignment.user_id == user_id,
                CampaignAssignment.status.in_(ACTIVE_STATUSES),
            )
        )
    )
    return len(result.scalars().all())


# ── GET /invitations ──────────────────────────────────────────────


@router.get("/invitations")
async def get_invitations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return pending campaign invitations for the current user.

    Side-effect: auto-expires any past-due invitations before returning.
    """
    await _expire_stale_invitations(user.id, db)

    now = _utcnow()
    # Return both pending AND recently expired invitations (expired shown dimmed at bottom)
    result = await db.execute(
        select(CampaignAssignment)
        .join(Campaign)
        .options(selectinload(CampaignAssignment.campaign).selectinload(Campaign.company))
        .where(
            and_(
                CampaignAssignment.user_id == user.id,
                or_(
                    and_(CampaignAssignment.status == "pending_invitation", CampaignAssignment.expires_at > now),
                    CampaignAssignment.status == "expired",
                ),
            )
        )
    )
    assignments = result.scalars().all()

    invitations = []
    for a in assignments:
        campaign = a.campaign
        targeting = campaign.targeting or {}
        invitations.append({
            "assignment_id": a.id,
            "campaign_id": campaign.id,
            "status": a.status,
            "title": campaign.title,
            "brief": campaign.brief,
            "content_guidance": campaign.content_guidance,
            "payout_rules": campaign.payout_rules,
            "platforms_required": targeting.get("required_platforms", []),
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "invited_at": a.invited_at.isoformat() if a.invited_at else None,
            "company_name": campaign.company.name if campaign.company else None,
        })

    return invitations


# ── POST /invitations/{assignment_id}/accept ──────────────────────


@router.post("/invitations/{assignment_id}/accept")
async def accept_invitation(
    assignment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await _get_assignment_for_user(assignment_id, user.id, db)

    # Must be pending
    if assignment.status != "pending_invitation":
        raise HTTPException(
            status_code=400,
            detail=f"Invitation is not pending (current status: {assignment.status})",
        )

    # Check expiry
    if _is_expired(assignment.expires_at):
        # Auto-expire it
        assignment.status = "expired"
        camp_result = await db.execute(
            select(Campaign).where(Campaign.id == assignment.campaign_id)
        )
        campaign = camp_result.scalar_one_or_none()
        if campaign:
            campaign.expired_count = (campaign.expired_count or 0) + 1
        db.add(CampaignInvitationLog(
            campaign_id=assignment.campaign_id,
            user_id=user.id,
            event="expired",
        ))
        await db.flush()
        raise HTTPException(status_code=400, detail="Invitation has expired")

    # Enforce max 5 active campaigns
    active_count = await _count_active_campaigns(user.id, db)
    if active_count >= MAX_ACTIVE_CAMPAIGNS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_ACTIVE_CAMPAIGNS} active campaigns reached. "
                   "Complete or drop a campaign before accepting a new one.",
        )

    # Accept
    now = _utcnow()
    assignment.status = "accepted"
    assignment.responded_at = now

    # Increment campaign counter
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == assignment.campaign_id)
    )
    campaign = camp_result.scalar_one_or_none()
    if campaign:
        campaign.accepted_count = (campaign.accepted_count or 0) + 1

    # Log
    db.add(CampaignInvitationLog(
        campaign_id=assignment.campaign_id,
        user_id=user.id,
        event="accepted",
    ))
    await db.flush()

    return {
        "status": "accepted",
        "assignment_id": assignment.id,
        "campaign_id": assignment.campaign_id,
        "message": "Campaign accepted. Content generation will begin shortly.",
    }


# ── POST /invitations/{assignment_id}/reject ──────────────────────


class RejectBody(BaseModel):
    reason: str | None = None


@router.post("/invitations/{assignment_id}/reject")
async def reject_invitation(
    assignment_id: int,
    body: RejectBody | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    assignment = await _get_assignment_for_user(assignment_id, user.id, db)

    # Must be pending
    if assignment.status != "pending_invitation":
        raise HTTPException(
            status_code=400,
            detail=f"Invitation is not pending (current status: {assignment.status})",
        )

    # Check expiry
    if _is_expired(assignment.expires_at):
        assignment.status = "expired"
        camp_result = await db.execute(
            select(Campaign).where(Campaign.id == assignment.campaign_id)
        )
        campaign = camp_result.scalar_one_or_none()
        if campaign:
            campaign.expired_count = (campaign.expired_count or 0) + 1
        db.add(CampaignInvitationLog(
            campaign_id=assignment.campaign_id,
            user_id=user.id,
            event="expired",
        ))
        await db.flush()
        raise HTTPException(status_code=400, detail="Invitation has expired")

    # Reject
    now = _utcnow()
    assignment.status = "rejected"
    assignment.responded_at = now
    if body and body.reason:
        assignment.decline_reason = body.reason

    # Increment campaign counter
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == assignment.campaign_id)
    )
    campaign = camp_result.scalar_one_or_none()
    if campaign:
        campaign.rejected_count = (campaign.rejected_count or 0) + 1

    # Log
    decline_reason = (body.reason if body and body.reason else None)
    db.add(CampaignInvitationLog(
        campaign_id=assignment.campaign_id,
        user_id=user.id,
        event="rejected",
        event_metadata={"decline_reason": decline_reason} if decline_reason else None,
    ))
    await db.flush()

    return {
        "status": "rejected",
        "assignment_id": assignment.id,
        "campaign_id": assignment.campaign_id,
        "message": "Campaign rejected.",
    }


# ── GET /active ───────────────────────────────────────────────────


@router.get("/active")
async def get_active_campaigns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user's active campaigns (accepted, content_generated, posted, metrics_collected)."""
    result = await db.execute(
        select(CampaignAssignment)
        .join(Campaign)
        .options(selectinload(CampaignAssignment.campaign))
        .where(
            and_(
                CampaignAssignment.user_id == user.id,
                CampaignAssignment.status.in_(ACTIVE_STATUSES),
            )
        )
    )
    assignments = result.scalars().all()

    campaigns_out = []
    for a in assignments:
        campaign = a.campaign
        campaigns_out.append({
            "assignment_id": a.id,
            "campaign_id": campaign.id,
            "title": campaign.title,
            "brief": campaign.brief,
            "assets": campaign.assets,
            "content_guidance": campaign.content_guidance,
            "payout_rules": campaign.payout_rules,
            "assignment_status": a.status,
            "campaign_status": campaign.status,
            "campaign_updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
            "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
            "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
        })

    return campaigns_out
