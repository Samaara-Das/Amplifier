"""Admin company management routes."""

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate_scalars,
    log_admin_action, build_query_string,
)

router = APIRouter()


@router.get("/companies", response_class=HTMLResponse)
async def companies_page(
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

    query = select(Company)
    count_query = select(func.count()).select_from(Company)

    if search:
        query = query.where(
            Company.name.ilike(f"%{search}%") | Company.email.ilike(f"%{search}%")
        )
        count_query = count_query.where(
            Company.name.ilike(f"%{search}%") | Company.email.ilike(f"%{search}%")
        )
    if status:
        query = query.where(Company.status == status)
        count_query = count_query.where(Company.status == status)

    sort_col = {
        "balance": Company.balance,
        "name": Company.name,
    }.get(sort, Company.created_at)

    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pagination = await paginate_scalars(db, query, count_query, page, per_page=25)

    companies_list = []
    for c in pagination["items"]:
        campaign_count = await db.scalar(
            select(func.count()).select_from(Campaign).where(Campaign.company_id == c.id)
        ) or 0
        total_spent = float(
            await db.scalar(
                select(func.coalesce(func.sum(Campaign.budget_total - Campaign.budget_remaining), 0))
                .select_from(Campaign).where(Campaign.company_id == c.id)
            ) or 0
        )
        companies_list.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "balance": float(c.balance),
            "status": getattr(c, "status", "active"),
            "campaign_count": campaign_count,
            "total_spent": total_spent,
            "created_at": c.created_at,
        })

    qs = build_query_string(search=search, status=status, sort=sort, order=order)

    return _render(
        "admin/companies.html",
        active_page="companies",
        companies=companies_list,
        pagination=pagination,
        search=search,
        current_status=status,
        sort=sort,
        order=order,
        qs=qs,
    )


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_detail(
    company_id: int,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return RedirectResponse(url="/admin/companies", status_code=303)

    # Get campaigns
    camp_result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company_id)
        .order_by(Campaign.created_at.desc())
        .limit(50)
    )
    campaigns = []
    for c in camp_result.scalars().all():
        campaigns.append({
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "budget_total": float(c.budget_total),
            "budget_remaining": float(c.budget_remaining),
            "created_at": c.created_at,
        })

    # Summary stats
    total_campaigns = len(campaigns)
    active_campaigns = len([c for c in campaigns if c["status"] == "active"])
    total_budget = sum(c["budget_total"] for c in campaigns)
    total_spent = sum(c["budget_total"] - c["budget_remaining"] for c in campaigns)

    return _render(
        "admin/company_detail.html",
        active_page="companies",
        company={
            "id": company.id,
            "name": company.name,
            "email": company.email,
            "balance": float(company.balance),
            "status": getattr(company, "status", "active"),
            "created_at": company.created_at,
        },
        campaigns=campaigns,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_budget=total_budget,
        total_spent=total_spent,
    )


@router.post("/companies/{company_id}/add-funds")
async def add_funds(
    company_id: int,
    request: Request,
    amount: float = Form(...),
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company and amount > 0:
        company.balance = float(company.balance) + amount
        await db.flush()
        await log_admin_action(db, request, "company_funds_added", "company", company_id, {
            "name": company.name, "amount": amount, "new_balance": float(company.balance),
        })
    return RedirectResponse(url=f"/admin/companies/{company_id}", status_code=303)


@router.post("/companies/{company_id}/deduct-funds")
async def deduct_funds(
    company_id: int,
    request: Request,
    amount: float = Form(...),
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company and amount > 0:
        company.balance = max(0, float(company.balance) - amount)
        await db.flush()
        await log_admin_action(db, request, "company_funds_deducted", "company", company_id, {
            "name": company.name, "amount": amount, "new_balance": float(company.balance),
        })
    return RedirectResponse(url=f"/admin/companies/{company_id}", status_code=303)


@router.post("/companies/{company_id}/suspend")
async def suspend_company(
    company_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company and getattr(company, "status", "active") == "active":
        company.status = "suspended"
        # Pause all active campaigns
        camp_result = await db.execute(
            select(Campaign).where(Campaign.company_id == company_id, Campaign.status == "active")
        )
        paused_count = 0
        for c in camp_result.scalars().all():
            c.status = "paused"
            paused_count += 1
        await db.flush()
        await log_admin_action(db, request, "company_suspended", "company", company_id, {
            "name": company.name, "campaigns_paused": paused_count,
        })
    return RedirectResponse(url=f"/admin/companies/{company_id}", status_code=303)


@router.post("/companies/{company_id}/unsuspend")
async def unsuspend_company(
    company_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company and getattr(company, "status", "active") == "suspended":
        company.status = "active"
        await db.flush()
        await log_admin_action(db, request, "company_unsuspended", "company", company_id, {
            "name": company.name,
        })
    return RedirectResponse(url=f"/admin/companies/{company_id}", status_code=303)
