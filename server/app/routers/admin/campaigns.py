"""Admin campaign management routes."""

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.models.user import User
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate,
    log_admin_action, build_query_string,
)

router = APIRouter()


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    search: str = "",
    status: str = "",
    sort: str = "created_at",
    order: str = "desc",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    query = select(Campaign, Company).join(Company, Campaign.company_id == Company.id)
    count_query = select(func.count()).select_from(Campaign)

    if search:
        query = query.where(Campaign.title.ilike(f"%{search}%"))
        count_query = count_query.where(Campaign.title.ilike(f"%{search}%"))
    if status:
        query = query.where(Campaign.status == status)
        count_query = count_query.where(Campaign.status == status)

    sort_col = {
        "budget_total": Campaign.budget_total,
        "budget_remaining": Campaign.budget_remaining,
        "title": Campaign.title,
    }.get(sort, Campaign.created_at)

    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pagination = await paginate(db, query, count_query, page, per_page=25)

    campaigns_list = []
    for campaign, company in pagination["items"]:
        user_count = await db.scalar(
            select(func.count(func.distinct(CampaignAssignment.user_id)))
            .where(CampaignAssignment.campaign_id == campaign.id)
        ) or 0
        post_count = await db.scalar(
            select(func.count(Post.id))
            .select_from(Post)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == campaign.id)
        ) or 0

        campaigns_list.append({
            "id": campaign.id,
            "company_name": company.name,
            "company_id": company.id,
            "title": campaign.title,
            "status": campaign.status,
            "screening_status": campaign.screening_status,
            "budget_total": float(campaign.budget_total),
            "budget_remaining": float(campaign.budget_remaining),
            "user_count": user_count,
            "post_count": post_count,
            "created_at": campaign.created_at,
        })

    qs = build_query_string(search=search, status=status, sort=sort, order=order)

    return _render(
        "admin/campaigns.html",
        active_page="campaigns",
        campaigns=campaigns_list,
        pagination=pagination,
        search=search,
        current_status=status,
        sort=sort,
        order=order,
        qs=qs,
    )


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(
    campaign_id: int,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    result = await db.execute(
        select(Campaign, Company)
        .join(Company, Campaign.company_id == Company.id)
        .where(Campaign.id == campaign_id)
    )
    row = result.one_or_none()
    if not row:
        return RedirectResponse(url="/admin/campaigns", status_code=303)
    campaign, company = row

    # Assigned users
    assign_result = await db.execute(
        select(CampaignAssignment, User)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
        .order_by(CampaignAssignment.assigned_at.desc())
    )
    assignments = []
    for a, u in assign_result.all():
        assignments.append({
            "id": a.id,
            "user_id": u.id,
            "user_email": u.email,
            "status": a.status,
            "content_mode": a.content_mode,
            "assigned_at": a.assigned_at,
        })

    # Posts with metrics
    post_result = await db.execute(
        select(Post, CampaignAssignment, User)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
        .order_by(Post.posted_at.desc())
    )
    posts = []
    total_impressions = 0
    total_engagement = 0
    for p, a, u in post_result.all():
        metric_result = await db.execute(
            select(Metric).where(Metric.post_id == p.id).order_by(Metric.created_at.desc()).limit(1)
        )
        metric = metric_result.scalar_one_or_none()
        imp = metric.impressions if metric else 0
        eng = (metric.likes + metric.reposts + metric.comments) if metric else 0
        total_impressions += imp
        total_engagement += eng
        posts.append({
            "id": p.id,
            "user_email": u.email,
            "platform": p.platform,
            "post_url": p.post_url,
            "status": p.status,
            "posted_at": p.posted_at,
            "impressions": imp,
            "likes": metric.likes if metric else 0,
            "reposts": metric.reposts if metric else 0,
            "comments": metric.comments if metric else 0,
        })

    budget_pct = 0
    if float(campaign.budget_total) > 0:
        budget_pct = round((1 - float(campaign.budget_remaining) / float(campaign.budget_total)) * 100, 1)

    return _render(
        "admin/campaign_detail.html",
        active_page="campaigns",
        campaign={
            "id": campaign.id,
            "title": campaign.title,
            "brief": campaign.brief,
            "status": campaign.status,
            "screening_status": campaign.screening_status,
            "budget_total": float(campaign.budget_total),
            "budget_remaining": float(campaign.budget_remaining),
            "budget_pct": budget_pct,
            "payout_rules": campaign.payout_rules or {},
            "targeting": campaign.targeting or {},
            "content_guidance": campaign.content_guidance,
            "penalty_rules": campaign.penalty_rules or {},
            "assets": campaign.assets or {},
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "max_users": campaign.max_users,
            "created_at": campaign.created_at,
        },
        company={"id": company.id, "name": company.name, "email": company.email},
        assignments=assignments,
        posts=posts,
        total_impressions=total_impressions,
        total_engagement=total_engagement,
    )


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign and campaign.status == "active":
        campaign.status = "paused"
        await db.flush()
        await log_admin_action(db, request, "campaign_paused", "campaign", campaign_id, {"title": campaign.title})
    return RedirectResponse(url=f"/admin/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(campaign_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign and campaign.status == "paused":
        campaign.status = "active"
        await db.flush()
        await log_admin_action(db, request, "campaign_resumed", "campaign", campaign_id, {"title": campaign.title})
    return RedirectResponse(url=f"/admin/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign and campaign.status in ("active", "paused", "draft"):
        campaign.status = "cancelled"
        # Refund remaining budget
        comp_result = await db.execute(select(Company).where(Company.id == campaign.company_id))
        company = comp_result.scalar_one_or_none()
        refund = float(campaign.budget_remaining)
        if company and refund > 0:
            company.balance = float(company.balance) + refund
            campaign.budget_remaining = 0
        await db.flush()
        await log_admin_action(db, request, "campaign_cancelled", "campaign", campaign_id, {
            "title": campaign.title, "refunded": refund,
        })
    return RedirectResponse(url=f"/admin/campaigns/{campaign_id}", status_code=303)
