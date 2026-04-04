"""Admin content review queue routes."""

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.content_screening import ContentScreeningLog
from app.routers.admin import (
    _render, _check_admin, _login_redirect, log_admin_action,
)

router = APIRouter()


@router.get("/review-queue", response_class=HTMLResponse)
async def review_queue_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    tab: str = "pending",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    # Pending (flagged, not reviewed)
    pending = []
    reviewed = []

    try:
        pending_result = await db.execute(
            select(ContentScreeningLog, Campaign, Company)
            .join(Campaign, ContentScreeningLog.campaign_id == Campaign.id)
            .join(Company, Campaign.company_id == Company.id)
            .where(and_(
                ContentScreeningLog.flagged == True,
                ContentScreeningLog.reviewed_by_admin == False,
            ))
            .order_by(ContentScreeningLog.created_at.desc())
        )
        for log, campaign, company in pending_result.all():
            pending.append({
                "campaign_id": campaign.id,
                "company_name": company.name,
                "title": campaign.title,
                "brief": (campaign.brief or "")[:200],
                "flagged_keywords": log.flagged_keywords or [],
                "categories": log.screening_categories or [],
                "created_at": log.created_at,
            })

        # Previously reviewed
        reviewed_result = await db.execute(
            select(ContentScreeningLog, Campaign, Company)
            .join(Campaign, ContentScreeningLog.campaign_id == Campaign.id)
            .join(Company, Campaign.company_id == Company.id)
            .where(ContentScreeningLog.reviewed_by_admin == True)
            .order_by(ContentScreeningLog.created_at.desc())
            .limit(50)
        )
        for log, campaign, company in reviewed_result.all():
            reviewed.append({
                "campaign_id": campaign.id,
                "company_name": company.name,
                "title": campaign.title,
                "result": log.review_result,
                "notes": log.review_notes,
                "created_at": log.created_at,
            })
    except Exception:
        # Table may not exist yet — graceful fallback
        pass

    # Also show campaigns with screening_status == "flagged" that might not have a ContentScreeningLog
    flagged_campaigns_result = await db.execute(
        select(Campaign, Company)
        .join(Company, Campaign.company_id == Company.id)
        .where(Campaign.screening_status == "flagged")
        .order_by(Campaign.created_at.desc())
    )
    flagged_ids = {p["campaign_id"] for p in pending}
    for campaign, company in flagged_campaigns_result.all():
        if campaign.id not in flagged_ids:
            pending.append({
                "campaign_id": campaign.id,
                "company_name": company.name,
                "title": campaign.title,
                "brief": (campaign.brief or "")[:200],
                "flagged_keywords": [],
                "categories": [],
                "created_at": campaign.created_at,
            })

    return _render(
        "admin/review_queue.html",
        active_page="review",
        pending=pending,
        reviewed=reviewed,
        tab=tab,
        pending_count=len(pending),
        reviewed_count=len(reviewed),
    )


@router.post("/review-queue/{campaign_id}/approve")
async def approve_flagged(
    campaign_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    # Update ContentScreeningLog if exists
    try:
        log_result = await db.execute(
            select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
        )
        log = log_result.scalar_one_or_none()
        if log:
            log.reviewed_by_admin = True
            log.review_result = "approved"
    except Exception:
        pass

    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_result.scalar_one_or_none()
    if campaign and campaign.screening_status == "flagged":
        campaign.screening_status = "approved"
        await db.flush()
        await log_admin_action(db, request, "review_approved", "campaign", campaign_id, {"title": campaign.title})

    return RedirectResponse(url="/admin/review-queue", status_code=303)


@router.post("/review-queue/{campaign_id}/reject")
async def reject_flagged(
    campaign_id: int,
    request: Request,
    notes: str = Form("Rejected by admin"),
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    # Update ContentScreeningLog if exists
    try:
        log_result = await db.execute(
            select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
        )
        log = log_result.scalar_one_or_none()
        if log:
            log.reviewed_by_admin = True
            log.review_result = "rejected"
            log.review_notes = notes
    except Exception:
        pass

    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_result.scalar_one_or_none()
    if campaign and campaign.screening_status == "flagged":
        campaign.screening_status = "rejected"
        campaign.status = "cancelled"

        # Refund budget
        company_result = await db.execute(select(Company).where(Company.id == campaign.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company.balance = float(company.balance) + float(campaign.budget_remaining)

        await db.flush()
        await log_admin_action(db, request, "review_rejected", "campaign", campaign_id, {
            "title": campaign.title, "notes": notes,
        })

    return RedirectResponse(url="/admin/review-queue", status_code=303)
