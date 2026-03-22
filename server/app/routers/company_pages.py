"""Company web pages — Jinja2 templates with cookie-based auth."""

import os

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric

router = APIRouter()
_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_template_dir)
settings = get_settings()


# ── Helper: cookie-based auth ──────────────────────────────────────


async def get_company_from_cookie(
    company_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> Company | None:
    """Extract company from JWT cookie. Returns None if not authenticated."""
    if not company_token:
        return None
    try:
        payload = decode_token(company_token)
    except Exception:
        return None
    if payload.get("type") != "company":
        return None
    company_id = payload.get("sub")
    if not company_id:
        return None
    result = await db.execute(select(Company).where(Company.id == int(company_id)))
    return result.scalar_one_or_none()


def _login_redirect():
    return RedirectResponse(url="/company/login", status_code=302)


# ── Login / Register ───────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "company/login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Company).where(Company.email == email))
    company = result.scalar_one_or_none()
    if not company or not verify_password(password, company.password_hash):
        return templates.TemplateResponse(
            "company/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401,
        )

    token = create_access_token({"sub": str(company.id), "type": "company"})
    response = RedirectResponse(url="/company/", status_code=302)
    response.set_cookie(
        key="company_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


@router.post("/register")
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Check duplicate email
    existing = await db.execute(select(Company).where(Company.email == email))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            "company/login.html",
            {"request": request, "error": "Email already registered", "show_register": True},
            status_code=400,
        )

    company = Company(
        name=name,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(company)
    await db.flush()

    token = create_access_token({"sub": str(company.id), "type": "company"})
    response = RedirectResponse(url="/company/", status_code=302)
    response.set_cookie(
        key="company_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/company/login", status_code=302)
    response.delete_cookie("company_token")
    return response


# ── Campaigns list (index) ─────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def campaigns_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    # Aggregate stats for each campaign
    campaign_data = []
    for c in campaigns:
        stats = await db.execute(
            select(
                func.count(Post.id).label("post_count"),
                func.count(func.distinct(CampaignAssignment.user_id)).label("user_count"),
            )
            .select_from(Post)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == c.id)
        )
        row = stats.one()

        metrics = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(
                    func.sum(Metric.likes + Metric.reposts + Metric.comments), 0
                ).label("engagement"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(
                and_(
                    CampaignAssignment.campaign_id == c.id,
                    Metric.is_final == True,
                )
            )
        )
        m = metrics.one()

        campaign_data.append(
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "budget_total": float(c.budget_total),
                "budget_remaining": float(c.budget_remaining),
                "user_count": row.user_count,
                "post_count": row.post_count,
                "impressions": int(m.impressions),
                "engagement": int(m.engagement),
            }
        )

    return templates.TemplateResponse(
        "company/campaigns.html",
        {
            "request": request,
            "company": company,
            "campaigns": campaign_data,
            "active": "campaigns",
        },
    )


# ── Create Campaign ────────────────────────────────────────────────


@router.get("/campaigns/new", response_class=HTMLResponse)
async def campaign_create_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    return templates.TemplateResponse(
        "company/campaign_create.html",
        {"request": request, "company": company, "active": "create"},
    )


@router.post("/campaigns/new")
async def campaign_create_submit(
    request: Request,
    title: str = Form(...),
    brief: str = Form(...),
    budget: float = Form(...),
    rate_per_1k_impressions: float = Form(0.50),
    rate_per_like: float = Form(0.01),
    rate_per_repost: float = Form(0.05),
    rate_per_click: float = Form(0.10),
    min_followers_json: str = Form("{}"),
    niche_tags: list[str] = Form([]),
    target_regions: list[str] = Form([]),
    required_platforms: list[str] = Form([]),
    content_guidance: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    import json
    from datetime import datetime

    # Parse min_followers JSON
    try:
        min_followers = json.loads(min_followers_json) if min_followers_json.strip() else {}
    except json.JSONDecodeError:
        min_followers = {}

    # niche_tags comes as a list from checkboxes
    tags = [t.strip() for t in niche_tags if t.strip()]

    # Validate budget
    if float(company.balance) < budget:
        return templates.TemplateResponse(
            "company/campaign_create.html",
            {
                "request": request,
                "company": company,
                "active": "create",
                "error": f"Insufficient balance. Current balance: ${float(company.balance):.2f}",
                "form": {
                    "title": title,
                    "brief": brief,
                    "content_guidance": content_guidance,
                    "budget": budget,
                    "start_date": start_date,
                    "end_date": end_date,
                    "rate_per_1k_impressions": rate_per_1k_impressions,
                    "rate_per_like": rate_per_like,
                    "rate_per_repost": rate_per_repost,
                    "rate_per_click": rate_per_click,
                    "min_followers_json": min_followers_json,
                    "niche_tags": niche_tags,
                    "target_regions": target_regions,
                    "required_platforms": required_platforms,
                },
            },
            status_code=400,
        )

    campaign = Campaign(
        company_id=company.id,
        title=title,
        brief=brief,
        budget_total=budget,
        budget_remaining=budget,
        payout_rules={
            "rate_per_1k_impressions": rate_per_1k_impressions,
            "rate_per_like": rate_per_like,
            "rate_per_repost": rate_per_repost,
            "rate_per_click": rate_per_click,
        },
        targeting={
            "min_followers": min_followers,
            "niche_tags": tags,
            "target_regions": target_regions,
            "required_platforms": required_platforms,
        },
        content_guidance=content_guidance or None,
        penalty_rules={},
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date),
        status="draft",
    )
    db.add(campaign)

    # Deduct budget from company balance
    company.balance = float(company.balance) - budget
    await db.flush()

    return RedirectResponse(url="/company/", status_code=302)


# ── Campaign Detail ────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail_page(
    request: Request,
    campaign_id: int,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/", status_code=302)

    # Aggregate totals
    totals = await db.execute(
        select(
            func.count(Post.id).label("post_count"),
            func.count(func.distinct(CampaignAssignment.user_id)).label("user_count"),
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(
                func.sum(Metric.likes + Metric.reposts + Metric.comments), 0
            ).label("engagement"),
        )
        .select_from(Post)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .outerjoin(Metric, and_(Metric.post_id == Post.id, Metric.is_final == True))
        .where(CampaignAssignment.campaign_id == campaign_id)
    )
    t = totals.one()

    # Per-platform breakdown
    platform_stats = await db.execute(
        select(
            Post.platform,
            func.count(Post.id).label("post_count"),
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(Metric.likes), 0).label("likes"),
            func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
            func.coalesce(func.sum(Metric.comments), 0).label("comments"),
            func.coalesce(func.sum(Metric.clicks), 0).label("clicks"),
        )
        .select_from(Post)
        .outerjoin(Metric, and_(Metric.post_id == Post.id, Metric.is_final == True))
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
        .group_by(Post.platform)
    )

    platforms = []
    for row in platform_stats:
        platforms.append(
            {
                "platform": row.platform,
                "posts": row.post_count,
                "impressions": int(row.impressions),
                "likes": int(row.likes),
                "reposts": int(row.reposts),
                "comments": int(row.comments),
                "clicks": int(row.clicks),
            }
        )

    spent = float(campaign.budget_total) - float(campaign.budget_remaining)

    # Influencer list — users assigned to this campaign with their posts and metrics
    from app.models.user import User
    influencer_query = await db.execute(
        select(
            User.id, User.email, User.platforms,
            CampaignAssignment.status.label("assignment_status"),
            CampaignAssignment.id.label("assignment_id"),
        )
        .select_from(CampaignAssignment)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
    )
    influencers = []
    for row in influencer_query:
        # Get this user's posts for this campaign
        user_posts_q = await db.execute(
            select(Post.platform, Post.post_url)
            .where(Post.assignment_id == row.assignment_id)
        )
        user_posts = [{"platform": p.platform, "url": p.post_url} for p in user_posts_q if p.post_url]

        # Get this user's metrics for this campaign
        user_metrics_q = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .where(and_(Post.assignment_id == row.assignment_id, Metric.is_final == True))
        )
        um = user_metrics_q.one()

        # Extract handles from platforms JSON
        handles = {}
        user_platforms = row.platforms or {}
        connected_platforms = []
        for plat, info in user_platforms.items():
            if isinstance(info, dict) and info.get("connected"):
                connected_platforms.append(plat)
                if info.get("username"):
                    handles[plat] = info["username"]

        influencers.append({
            "email": row.email,
            "handles": handles,
            "platforms": connected_platforms,
            "status": row.assignment_status,
            "posts": user_posts,
            "impressions": int(um.impressions),
            "engagement": int(um.engagement),
        })

    return templates.TemplateResponse(
        "company/campaign_detail.html",
        {
            "request": request,
            "company": company,
            "campaign": campaign,
            "spent": spent,
            "post_count": t.post_count,
            "user_count": t.user_count,
            "impressions": int(t.impressions),
            "engagement": int(t.engagement),
            "platforms": platforms,
            "influencers": influencers,
            "active": "campaigns",
        },
    )


@router.post("/campaigns/{campaign_id}/status")
async def campaign_status_change(
    campaign_id: int,
    new_status: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/", status_code=302)

    valid_transitions = {
        "draft": ["active", "cancelled"],
        "active": ["paused", "cancelled"],
        "paused": ["active", "cancelled"],
    }
    allowed = valid_transitions.get(campaign.status, [])
    if new_status in allowed:
        campaign.status = new_status
        await db.flush()

    return RedirectResponse(url=f"/company/campaigns/{campaign_id}", status_code=302)


# ── Billing ────────────────────────────────────────────────────────


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    # Get campaign budget allocations as payment history
    result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    allocations = []
    for c in campaigns:
        allocations.append(
            {
                "campaign_title": c.title,
                "amount": float(c.budget_total),
                "spent": float(c.budget_total) - float(c.budget_remaining),
                "date": c.created_at,
                "status": c.status,
            }
        )

    return templates.TemplateResponse(
        "company/billing.html",
        {
            "request": request,
            "company": company,
            "allocations": allocations,
            "active": "billing",
        },
    )


@router.post("/billing/topup")
async def billing_topup(
    request: Request,
    amount: float = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    if amount <= 0:
        return RedirectResponse(url="/company/billing", status_code=302)

    # Placeholder: in production this would go through Stripe
    company.balance = float(company.balance) + amount
    await db.flush()

    return RedirectResponse(url="/company/billing", status_code=302)


# ── Settings ───────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    return templates.TemplateResponse(
        "company/settings.html",
        {
            "request": request,
            "company": company,
            "active": "settings",
        },
    )


@router.post("/settings")
async def settings_update(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    # Check email uniqueness if changed
    if email != company.email:
        existing = await db.execute(select(Company).where(Company.email == email))
        if existing.scalar_one_or_none():
            return templates.TemplateResponse(
                "company/settings.html",
                {
                    "request": request,
                    "company": company,
                    "active": "settings",
                    "error": "Email already in use by another account",
                },
                status_code=400,
            )

    company.name = name
    company.email = email
    await db.flush()

    return templates.TemplateResponse(
        "company/settings.html",
        {
            "request": request,
            "company": company,
            "active": "settings",
            "success": "Profile updated successfully",
        },
    )
