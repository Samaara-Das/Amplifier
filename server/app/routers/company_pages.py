"""Company web pages — Jinja2 templates with cookie-based auth."""

import csv
import io
import os

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader
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
from app.models.payout import Payout
from app.models.user import User

router = APIRouter()
_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)
settings = get_settings()


def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


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
    return _render("company/login.html", error=error)


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
        return _render("company/login.html", status_code=401, error="Invalid email or password")

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
        return _render("company/login.html", status_code=400, error="Email already registered", show_register=True)

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

    return _render("company/campaigns.html", company=company, campaigns=campaign_data, active="campaigns")


# ── Create Campaign ────────────────────────────────────────────────


@router.get("/campaigns/new", response_class=HTMLResponse)
async def campaign_create_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    return _render("company/campaign_wizard.html", company=company, active="create")


@router.post("/campaigns/ai-generate")
async def ai_generate_campaign(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Proxy for AI wizard — uses cookie auth instead of JWT Bearer."""
    from fastapi.responses import JSONResponse
    if not company:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    from app.services.campaign_wizard import run_campaign_wizard
    try:
        targeting = body.get("targeting", {})
        result = await run_campaign_wizard(
            db=db,
            product_description=body.get("product_description", ""),
            campaign_goal=body.get("campaign_goal", "brand_awareness"),
            company_urls=body.get("company_urls", []),
            target_niches=targeting.get("niche_tags") or targeting.get("target_niches", []),
            target_regions=targeting.get("target_regions", []),
            required_platforms=targeting.get("required_platforms", []),
            min_followers=targeting.get("min_followers", {}),
            tone=body.get("tone", "professional"),
            must_include=body.get("must_include", ""),
            must_avoid=body.get("must_avoid", ""),
        )
        return JSONResponse(result)
    except Exception as e:
        # Return sensible defaults on AI failure
        return JSONResponse({
            "title": body.get("product_description", "Campaign")[:60],
            "brief": body.get("product_description", ""),
            "content_guidance": f"Tone: {body.get('tone', 'professional')}. Create engaging content.",
            "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
            "suggested_budget": 100,
            "targeting": body.get("targeting", {}),
            "reach_estimate": {"matching_users": 0, "estimated_impressions_low": 0, "estimated_impressions_high": 0},
            "error": str(e)
        })


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
    campaign_status: str = Form("draft"),
    budget_exhaustion_action: str = Form("auto_pause"),
    max_users: int | None = Form(None),
    min_engagement: float = Form(0.0),
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

    # Sanitize campaign_status — only "draft" or "active" allowed
    if campaign_status not in ("draft", "active"):
        campaign_status = "draft"

    # Sanitize budget_exhaustion_action
    if budget_exhaustion_action not in ("auto_pause", "auto_complete"):
        budget_exhaustion_action = "auto_pause"

    # Validate minimum budget
    if budget < 50.0:
        return _render(
            "company/campaign_wizard.html",
            status_code=400,
            company=company,
            active="create",
            error="Minimum campaign budget is $50.00",
        )

    # Validate budget against balance — only for active campaigns, not drafts
    if campaign_status == "active" and float(company.balance) < budget:
        return _render(
            "company/campaign_wizard.html",
            status_code=400,
            company=company,
            active="create",
            error=f"Insufficient balance to activate. Current balance: ${float(company.balance):.2f}. Save as draft instead, then add funds.",
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
            "min_engagement": min_engagement,
            "niche_tags": tags,
            "target_regions": target_regions,
            "required_platforms": required_platforms,
        },
        content_guidance=content_guidance or None,
        penalty_rules={},
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date),
        status=campaign_status,
        budget_exhaustion_action=budget_exhaustion_action,
        max_users=max_users,
    )
    db.add(campaign)

    # Deduct budget from company balance — only when activating, not for drafts
    if campaign_status == "active":
        company.balance = float(company.balance) - budget
    await db.flush()

    return RedirectResponse(url="/company/", status_code=302)


# ── Campaign Detail ────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail_page(
    request: Request,
    campaign_id: int,
    success: str | None = None,
    error: str | None = None,
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

    # Per-platform breakdown with ROI calculations
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

    payout_rules = campaign.payout_rules or {}
    platforms = []
    for row in platform_stats:
        impressions_val = int(row.impressions)
        likes_val = int(row.likes)
        reposts_val = int(row.reposts)
        comments_val = int(row.comments)
        clicks_val = int(row.clicks)
        engagement_val = likes_val + reposts_val + comments_val

        # Calculate per-platform spend from payout rules
        plat_spend = (
            (impressions_val / 1000 * payout_rules.get("rate_per_1k_impressions", 0))
            + (likes_val * payout_rules.get("rate_per_like", 0))
            + (reposts_val * payout_rules.get("rate_per_repost", 0))
            + (clicks_val * payout_rules.get("rate_per_click", 0))
        )
        cost_per_1k = (plat_spend / impressions_val * 1000) if impressions_val > 0 else 0
        cost_per_eng = (plat_spend / engagement_val) if engagement_val > 0 else 0

        platforms.append(
            {
                "platform": row.platform,
                "posts": row.post_count,
                "impressions": impressions_val,
                "likes": likes_val,
                "reposts": reposts_val,
                "comments": comments_val,
                "clicks": clicks_val,
                "engagement": engagement_val,
                "spend": round(plat_spend, 2),
                "cost_per_1k": round(cost_per_1k, 2),
                "cost_per_eng": round(cost_per_eng, 2),
            }
        )

    spent = float(campaign.budget_total) - float(campaign.budget_remaining)

    # Invitation stats from denormalized counters
    invitation_count = campaign.invitation_count or 0
    accepted_count = campaign.accepted_count or 0
    rejected_count = campaign.rejected_count or 0
    expired_count = campaign.expired_count or 0
    pending_count = invitation_count - accepted_count - rejected_count - expired_count
    if pending_count < 0:
        pending_count = 0

    invitation_stats = {
        "total": invitation_count,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "expired": expired_count,
        "pending": pending_count,
        "responded": accepted_count + rejected_count + expired_count,
    }

    # Payout totals per user for this campaign
    payouts_q = await db.execute(
        select(
            Payout.user_id,
            func.coalesce(func.sum(Payout.amount), 0).label("total_paid"),
        )
        .where(Payout.campaign_id == campaign_id)
        .group_by(Payout.user_id)
    )
    user_payout_map: dict[int, float] = {}
    for pr in payouts_q:
        user_payout_map[pr.user_id] = float(pr.total_paid)

    # Influencer list — users assigned to this campaign with their posts and metrics
    influencer_query = await db.execute(
        select(
            User.id, User.email, User.platforms,
            CampaignAssignment.status.label("assignment_status"),
            CampaignAssignment.id.label("assignment_id"),
            CampaignAssignment.user_id.label("user_id"),
        )
        .select_from(CampaignAssignment)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
    )
    influencers = []
    creator_index = 0
    for row in influencer_query:
        creator_index += 1
        # Get this user's posts for this campaign
        user_posts_q = await db.execute(
            select(Post.platform, Post.post_url)
            .where(Post.assignment_id == row.assignment_id)
        )
        user_posts = [{"platform": p.platform, "url": p.post_url} for p in user_posts_q if p.post_url]

        # Get this user's detailed metrics for this campaign
        user_metrics_q = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes), 0).label("likes"),
                func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
                func.coalesce(func.sum(Metric.comments), 0).label("comments"),
                func.coalesce(func.sum(Metric.clicks), 0).label("clicks"),
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

        # Calculate estimated earned from metrics + payout rules
        imp = int(um.impressions)
        lk = int(um.likes)
        rp = int(um.reposts)
        cm = int(um.comments)
        ck = int(um.clicks)
        estimated_earned = (
            (imp / 1000 * payout_rules.get("rate_per_1k_impressions", 0))
            + (lk * payout_rules.get("rate_per_like", 0))
            + (rp * payout_rules.get("rate_per_repost", 0))
            + (ck * payout_rules.get("rate_per_click", 0))
        )
        actual_paid = user_payout_map.get(row.user_id, 0.0)

        influencers.append({
            "index": creator_index,
            "email": row.email,
            "handles": handles,
            "platforms": connected_platforms,
            "status": row.assignment_status,
            "posts": user_posts,
            "impressions": imp,
            "likes": lk,
            "reposts": rp,
            "comments": cm,
            "engagement": lk + rp + cm,
            "estimated_earned": round(estimated_earned, 2),
            "actual_paid": round(actual_paid, 2),
        })

    # Sort influencers by estimated_earned descending
    influencers.sort(key=lambda x: x["estimated_earned"], reverse=True)

    # Cost per impression / cost per engagement (overall)
    total_impressions = int(t.impressions)
    total_engagement = int(t.engagement)
    cost_per_1k_imp = (spent / total_impressions * 1000) if total_impressions > 0 else 0
    cost_per_eng = (spent / total_engagement) if total_engagement > 0 else 0

    return _render(
        "company/campaign_detail.html",
        company=company,
        campaign=campaign,
        spent=spent,
        post_count=t.post_count,
        user_count=t.user_count,
        impressions=total_impressions,
        engagement=total_engagement,
        cost_per_1k_imp=round(cost_per_1k_imp, 2),
        cost_per_eng=round(cost_per_eng, 2),
        platforms=platforms,
        influencers=influencers,
        invitation_stats=invitation_stats,
        budget_alert_sent=campaign.budget_alert_sent,
        budget_exhaustion_action=campaign.budget_exhaustion_action or "auto_pause",
        campaign_version=campaign.campaign_version or 1,
        active="campaigns",
        success=success,
        error=error,
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


# ── Campaign Edit (web form) ──────────────────────────────────────


@router.post("/campaigns/{campaign_id}/edit")
async def campaign_edit_submit(
    campaign_id: int,
    title: str = Form(...),
    brief: str = Form(...),
    content_guidance: str = Form(""),
    rate_per_1k_impressions: float = Form(0.50),
    rate_per_like: float = Form(0.01),
    rate_per_repost: float = Form(0.05),
    rate_per_click: float = Form(0.10),
    end_date: str = Form(""),
    budget_exhaustion_action: str = Form("auto_pause"),
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

    # Track content changes for version bump
    content_changed = False
    if title != campaign.title:
        campaign.title = title
        content_changed = True
    if brief != campaign.brief:
        campaign.brief = brief
        content_changed = True
    if (content_guidance or None) != campaign.content_guidance:
        campaign.content_guidance = content_guidance or None
        content_changed = True

    # Update payout rules
    campaign.payout_rules = {
        "rate_per_1k_impressions": rate_per_1k_impressions,
        "rate_per_like": rate_per_like,
        "rate_per_repost": rate_per_repost,
        "rate_per_click": rate_per_click,
    }

    # Update end date if provided
    if end_date.strip():
        from datetime import datetime as dt
        try:
            campaign.end_date = dt.fromisoformat(end_date)
        except ValueError:
            pass

    # Update budget exhaustion action
    if budget_exhaustion_action in ("auto_pause", "auto_complete"):
        campaign.budget_exhaustion_action = budget_exhaustion_action

    # Increment version on content edits
    if content_changed:
        campaign.campaign_version = (campaign.campaign_version or 1) + 1

        # Content screening deferred — auto-approve
        campaign.screening_status = "approved"

    await db.flush()

    return RedirectResponse(
        url=f"/company/campaigns/{campaign_id}?success=Campaign+updated+successfully",
        status_code=302,
    )


# ── Campaign Clone (web) ──────────────────────────────────────────


@router.post("/campaigns/{campaign_id}/clone")
async def campaign_clone_web(
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
    original = result.scalar_one_or_none()
    if not original:
        return RedirectResponse(url="/company/", status_code=302)

    if float(company.balance) < float(original.budget_total):
        return RedirectResponse(
            url=f"/company/campaigns/{campaign_id}?error=Insufficient+balance+to+clone+campaign",
            status_code=302,
        )

    clone = Campaign(
        company_id=company.id,
        title=f"{original.title} (Copy)",
        brief=original.brief,
        assets=original.assets,
        budget_total=float(original.budget_total),
        budget_remaining=float(original.budget_total),
        payout_rules=original.payout_rules,
        targeting=original.targeting,
        content_guidance=original.content_guidance,
        penalty_rules=original.penalty_rules,
        company_urls=original.company_urls,
        ai_generated_brief=original.ai_generated_brief,
        budget_exhaustion_action=original.budget_exhaustion_action,
        status="draft",
        start_date=original.start_date,
        end_date=original.end_date,
        budget_alert_sent=False,
        campaign_version=1,
        invitation_count=0,
        accepted_count=0,
        rejected_count=0,
        expired_count=0,
    )
    db.add(clone)
    company.balance = float(company.balance) - float(original.budget_total)
    await db.flush()

    return RedirectResponse(url=f"/company/campaigns/{clone.id}", status_code=302)


# ── Campaign Budget Top-Up (web) ──────────────────────────────────


@router.post("/campaigns/{campaign_id}/topup")
async def campaign_topup_web(
    campaign_id: int,
    amount: float = Form(...),
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

    if amount <= 0:
        return RedirectResponse(
            url=f"/company/campaigns/{campaign_id}?error=Amount+must+be+greater+than+zero",
            status_code=302,
        )

    if float(company.balance) < amount:
        return RedirectResponse(
            url=f"/company/campaigns/{campaign_id}?error=Insufficient+balance",
            status_code=302,
        )

    campaign.budget_remaining = float(campaign.budget_remaining) + amount
    campaign.budget_total = float(campaign.budget_total) + amount
    company.balance = float(company.balance) - amount

    # Resume auto-paused campaign
    if campaign.status == "paused" and campaign.budget_exhaustion_action == "auto_pause":
        campaign.status = "active"

    # Reset budget alert if budget is now above 20%
    if float(campaign.budget_remaining) >= 0.2 * float(campaign.budget_total):
        campaign.budget_alert_sent = False

    await db.flush()

    return RedirectResponse(
        url=f"/company/campaigns/{campaign_id}?success=Budget+topped+up+by+%24{amount:.2f}",
        status_code=302,
    )


# ── Campaign CSV Export (web, cookie auth) ────────────────────────


@router.get("/campaigns/{campaign_id}/export")
async def campaign_export_csv_web(
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

    # Fetch assignments
    assignments_result = await db.execute(
        select(CampaignAssignment).where(
            CampaignAssignment.campaign_id == campaign_id
        )
    )
    assignments = assignments_result.scalars().all()
    assignment_map = {a.id: a for a in assignments}
    user_ids = {a.user_id for a in assignments}

    # Fetch users
    user_map: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            user_map[u.id] = u

    # Fetch posts
    assignment_ids = [a.id for a in assignments]
    posts = []
    if assignment_ids:
        posts_result = await db.execute(
            select(Post).where(Post.assignment_id.in_(assignment_ids))
        )
        posts = posts_result.scalars().all()

    # Fetch payouts
    payouts_result = await db.execute(
        select(Payout).where(Payout.campaign_id == campaign_id)
    )
    payouts = payouts_result.scalars().all()
    user_payout_map: dict[int, float] = {}
    for p in payouts:
        user_payout_map[p.user_id] = user_payout_map.get(p.user_id, 0.0) + float(p.amount)

    # Build CSV
    p_rules = campaign.payout_rules or {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Creator", "Platform", "Post URL", "Status", "Impressions",
        "Likes", "Reposts", "Comments", "Clicks", "Est. Earned", "Posted At",
    ])

    for post in posts:
        assignment = assignment_map.get(post.assignment_id)
        if not assignment:
            continue
        user = user_map.get(assignment.user_id)
        user_display = user.email if user else f"Creator #{assignment.user_id}"

        # Get latest final metric
        final_metrics = [m for m in (post.metrics or []) if m.is_final]
        if final_metrics:
            latest = max(final_metrics, key=lambda m: m.scraped_at)
        elif post.metrics:
            latest = max(post.metrics, key=lambda m: m.scraped_at)
        else:
            latest = None

        imp = latest.impressions if latest else 0
        lk = latest.likes if latest else 0
        rp = latest.reposts if latest else 0
        cm = latest.comments if latest else 0
        cl = latest.clicks if latest else 0

        earned = (
            (imp / 1000 * p_rules.get("rate_per_1k_impressions", 0))
            + (lk * p_rules.get("rate_per_like", 0))
            + (rp * p_rules.get("rate_per_repost", 0))
            + (cl * p_rules.get("rate_per_click", 0))
        )

        posted_at_str = post.posted_at.strftime("%Y-%m-%d %H:%M:%S") if post.posted_at else ""

        writer.writerow([
            user_display, post.platform, post.post_url or "", assignment.status,
            imp, lk, rp, cm, cl, f"${earned:.2f}", posted_at_str,
        ])

    output.seek(0)
    filename = f"campaign-{campaign_id}-report.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Billing ────────────────────────────────────────────────────────


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    success: str | None = None,
    error: str | None = None,
    cancelled: str | None = None,
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

    stripe_configured = bool(settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY"))

    flash_success = None
    flash_error = None
    if success:
        flash_success = success
    elif cancelled:
        flash_error = "Payment was cancelled. No funds were added."
    elif error:
        flash_error = error

    return _render(
        "company/billing.html",
        company=company,
        allocations=allocations,
        active="billing",
        stripe_configured=stripe_configured,
        flash_success=flash_success,
        flash_error=flash_error,
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
        return RedirectResponse(url="/company/billing?error=Amount+must+be+greater+than+zero", status_code=302)

    amount_cents = int(round(amount * 100))

    from app.services.payments import create_company_checkout
    checkout_url = await create_company_checkout(company.id, amount_cents, db)

    if not checkout_url:
        # Stripe not configured — fall back to instant credit (dev/test only)
        company.balance = float(company.balance) + amount
        await db.flush()
        return RedirectResponse(
            url=f"/company/billing?success=Added+%24{amount:.2f}+to+your+balance+(test+mode)",
            status_code=302,
        )

    return RedirectResponse(url=checkout_url, status_code=302)


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success(
    request: Request,
    session_id: str,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Stripe redirects here after a successful payment. Verifies session and credits balance."""
    if not company:
        return _login_redirect()

    from app.services.payments import verify_checkout_session
    result = await verify_checkout_session(session_id)

    if not result:
        return RedirectResponse(
            url="/company/billing?error=Payment+verification+failed.+Contact+support.",
            status_code=302,
        )

    if result["company_id"] != company.id:
        return RedirectResponse(
            url="/company/billing?error=Session+mismatch.",
            status_code=302,
        )

    # Credit the balance
    amount = result["amount_cents"] / 100.0
    company.balance = float(company.balance) + amount
    await db.flush()

    return RedirectResponse(
        url=f"/company/billing?success=Successfully+added+%24{amount:.2f}+to+your+balance.",
        status_code=302,
    )


# ── Statistics ─────────────────────────────────────────────────────


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    from collections import defaultdict

    # Get all campaigns for this company
    result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    total_campaigns = len(campaigns)
    active_campaigns = sum(1 for c in campaigns if c.status == "active")

    # Overall metrics across all campaigns
    total_spend = 0.0
    total_impressions = 0
    total_engagement = 0
    best_campaign = None
    best_campaign_efficiency = 0.0  # engagement per dollar

    # Per-platform aggregation
    platform_engagement: dict[str, int] = defaultdict(int)

    # Monthly spend aggregation
    monthly_spend: dict[str, float] = defaultdict(float)

    for c in campaigns:
        spent = float(c.budget_total) - float(c.budget_remaining)
        total_spend += spent

        # Monthly spend (by created_at month)
        if c.created_at:
            month_key = c.created_at.strftime("%Y-%m")
            monthly_spend[month_key] += spent

        # Get metrics for this campaign
        metrics_q = await db.execute(
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
        m = metrics_q.one()
        camp_impressions = int(m.impressions)
        camp_engagement = int(m.engagement)

        total_impressions += camp_impressions
        total_engagement += camp_engagement

        # Best performing campaign (engagement per dollar spent)
        if spent > 0:
            efficiency = camp_engagement / spent
            if efficiency > best_campaign_efficiency:
                best_campaign_efficiency = efficiency
                best_campaign = {
                    "id": c.id,
                    "title": c.title,
                    "engagement": camp_engagement,
                    "impressions": camp_impressions,
                    "spent": spent,
                    "efficiency": round(efficiency, 2),
                }

        # Per-platform engagement for this campaign
        plat_q = await db.execute(
            select(
                Post.platform,
                func.coalesce(
                    func.sum(Metric.likes + Metric.reposts + Metric.comments), 0
                ).label("engagement"),
            )
            .select_from(Post)
            .outerjoin(Metric, and_(Metric.post_id == Post.id, Metric.is_final == True))
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == c.id)
            .group_by(Post.platform)
        )
        for row in plat_q:
            platform_engagement[row.platform] += int(row.engagement)

    # Derived stats
    cost_per_1k = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0
    cost_per_eng = (total_spend / total_engagement) if total_engagement > 0 else 0

    # Best platform
    best_platform = None
    if platform_engagement:
        best_plat = max(platform_engagement, key=platform_engagement.get)
        best_platform = {
            "name": best_plat,
            "engagement": platform_engagement[best_plat],
        }

    # Platform breakdown list (sorted by engagement desc)
    platform_breakdown = [
        {"name": p, "engagement": e}
        for p, e in sorted(platform_engagement.items(), key=lambda x: -x[1])
    ]

    # Monthly spend table (sorted by month)
    monthly_spend_list = [
        {"month": k, "spend": round(v, 2)}
        for k, v in sorted(monthly_spend.items())
    ]

    return _render(
        "company/stats.html",
        company=company,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_spend=round(total_spend, 2),
        total_impressions=total_impressions,
        total_engagement=total_engagement,
        cost_per_1k=round(cost_per_1k, 2),
        cost_per_eng=round(cost_per_eng, 2),
        best_campaign=best_campaign,
        best_platform=best_platform,
        platform_breakdown=platform_breakdown,
        monthly_spend=monthly_spend_list,
        active="stats",
    )


# ── Settings ───────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    return _render("company/settings.html", company=company, active="settings")


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
            return _render(
                "company/settings.html",
                status_code=400,
                company=company,
                active="settings",
                error="Email already in use by another account",
            )

    company.name = name
    company.email = email
    await db.flush()

    return _render("company/settings.html", company=company, active="settings", success="Profile updated successfully")
