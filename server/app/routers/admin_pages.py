"""Admin dashboard pages — server-rendered Jinja2 templates."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.penalty import Penalty

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_TOKEN_VALUE = "valid"

# Jinja2 template setup
_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


def _render(template_name: str, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx))


def _check_admin(admin_token: str | None) -> bool:
    return admin_token == ADMIN_TOKEN_VALUE


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return _render("admin/login.html", error=error)


@router.post("/login")
async def login_submit(password: str = Form(...), admin_token: str = Cookie(None)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin/", status_code=303)
        response.set_cookie("admin_token", ADMIN_TOKEN_VALUE, httponly=True, samesite="lax")
        return response
    return RedirectResponse(url="/admin/login?error=Invalid+password", status_code=303)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_token")
    return response


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def overview(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.status == "active")
    ) or 0
    total_campaigns = await db.scalar(select(func.count()).select_from(Campaign)) or 0
    active_campaigns = await db.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.status == "active")
    ) or 0
    total_posts = await db.scalar(select(func.count()).select_from(Post)) or 0
    total_payouts = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).select_from(Payout)
        ) or 0
    )

    # Platform revenue = total budget spent - total paid to users
    total_budget_spent = float(
        await db.scalar(
            select(func.coalesce(func.sum(Campaign.budget_total - Campaign.budget_remaining), 0))
            .select_from(Campaign)
        ) or 0
    )
    platform_revenue = total_budget_spent - total_payouts

    # Recent activity: last 10 assignments
    result = await db.execute(
        select(CampaignAssignment, User, Campaign)
        .join(User, CampaignAssignment.user_id == User.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .order_by(CampaignAssignment.assigned_at.desc())
        .limit(10)
    )
    recent = []
    for assignment, user, campaign in result.all():
        recent.append({
            "id": assignment.id,
            "user_email": user.email,
            "campaign_title": campaign.title,
            "status": assignment.status,
            "assigned_at": assignment.assigned_at,
        })

    return _render(
        "admin/overview.html",
        total_users=total_users,
        active_users=active_users,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_posts=total_posts,
        total_payouts=total_payouts,
        platform_revenue=platform_revenue,
        recent=recent,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_page(
    admin_token: str = Cookie(None),
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    query = select(User).order_by(User.created_at.desc())
    if status:
        query = query.where(User.status == status)
    result = await db.execute(query)
    users_list = []
    for u in result.scalars().all():
        platform_count = len([k for k, v in (u.platforms or {}).items() if v.get("connected")])
        users_list.append({
            "id": u.id,
            "email": u.email,
            "trust_score": u.trust_score,
            "mode": u.mode,
            "platform_count": platform_count,
            "total_earned": float(u.total_earned),
            "status": u.status,
        })

    return _render("admin/users.html", users=users_list, current_status=status)


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: int, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.status = "suspended"
        await db.flush()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: int, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.status == "suspended":
        user.status = "active"
        await db.flush()
    return RedirectResponse(url="/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    result = await db.execute(
        select(Campaign, Company)
        .join(Company, Campaign.company_id == Company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns_list = []
    for campaign, company in result.all():
        # Count users and posts for this campaign
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
            "title": campaign.title,
            "status": campaign.status,
            "budget_total": float(campaign.budget_total),
            "budget_remaining": float(campaign.budget_remaining),
            "user_count": user_count,
            "post_count": post_count,
            "created_at": campaign.created_at,
        })

    return _render("admin/campaigns.html", campaigns=campaigns_list)


# ---------------------------------------------------------------------------
# Fraud
# ---------------------------------------------------------------------------

@router.get("/fraud", response_class=HTMLResponse)
async def fraud_page(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Get recent penalties
    result = await db.execute(
        select(Penalty, User)
        .join(User, Penalty.user_id == User.id)
        .order_by(Penalty.created_at.desc())
        .limit(50)
    )
    penalties = []
    for penalty, user in result.all():
        penalties.append({
            "id": penalty.id,
            "user_id": penalty.user_id,
            "user_email": user.email,
            "reason": penalty.reason,
            "amount": float(penalty.amount),
            "description": penalty.description,
            "appealed": penalty.appealed,
            "created_at": penalty.created_at,
        })

    return _render(
        "admin/fraud.html",
        anomalies=[],
        deletions=[],
        penalties=penalties,
        check_result=None,
    )


@router.post("/fraud/run-check", response_class=HTMLResponse)
async def fraud_run_check(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.services.trust import detect_metrics_anomalies, detect_deletion_fraud, run_trust_check

    check_result = await run_trust_check(db)
    anomalies = check_result.get("anomalies", [])
    deletions = check_result.get("deletions", [])

    # Enrich anomalies with user email
    for a in anomalies:
        user_result = await db.execute(select(User).where(User.id == a["user_id"]))
        user = user_result.scalar_one_or_none()
        a["user_email"] = user.email if user else "Unknown"

    # Get recent penalties
    result = await db.execute(
        select(Penalty, User)
        .join(User, Penalty.user_id == User.id)
        .order_by(Penalty.created_at.desc())
        .limit(50)
    )
    penalties = []
    for penalty, user in result.all():
        penalties.append({
            "id": penalty.id,
            "user_id": penalty.user_id,
            "user_email": user.email,
            "reason": penalty.reason,
            "amount": float(penalty.amount),
            "description": penalty.description,
            "appealed": penalty.appealed,
            "created_at": penalty.created_at,
        })

    return _render(
        "admin/fraud.html",
        anomalies=anomalies,
        deletions=deletions,
        penalties=penalties,
        check_result=check_result,
    )


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

@router.get("/payouts", response_class=HTMLResponse)
async def payouts_page(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    total_pending = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0))
            .where(Payout.status == "pending")
        ) or 0
    )
    total_paid = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0))
            .where(Payout.status == "paid")
        ) or 0
    )
    total_failed = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0))
            .where(Payout.status == "failed")
        ) or 0
    )

    # All payouts with user and campaign info
    result = await db.execute(
        select(Payout, User)
        .join(User, Payout.user_id == User.id)
        .order_by(Payout.created_at.desc())
        .limit(200)
    )
    payouts_list = []
    # Pre-fetch campaign titles
    campaign_cache = {}
    for payout, user in result.all():
        campaign_title = ""
        if payout.campaign_id and payout.campaign_id > 0:
            if payout.campaign_id not in campaign_cache:
                c = await db.execute(select(Campaign).where(Campaign.id == payout.campaign_id))
                camp = c.scalar_one_or_none()
                campaign_cache[payout.campaign_id] = camp.title if camp else "N/A"
            campaign_title = campaign_cache[payout.campaign_id]
        else:
            campaign_title = "Aggregate"

        payouts_list.append({
            "id": payout.id,
            "user_email": user.email,
            "campaign_title": campaign_title,
            "amount": float(payout.amount),
            "status": payout.status,
            "breakdown": payout.breakdown or {},
            "created_at": payout.created_at,
        })

    return _render(
        "admin/payouts.html",
        total_pending=total_pending,
        total_paid=total_paid,
        total_failed=total_failed,
        payouts=payouts_list,
        result_msg=None,
    )


@router.post("/payouts/run-billing", response_class=HTMLResponse)
async def run_billing(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.services.billing import run_billing_cycle
    result = await run_billing_cycle(db)
    msg = f"Billing complete: {result['posts_processed']} posts, ${result['total_earned']:.2f} earned, ${result['total_budget_deducted']:.2f} deducted"

    # Re-fetch payout data
    total_pending = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "pending")
        ) or 0
    )
    total_paid = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "paid")
        ) or 0
    )
    total_failed = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "failed")
        ) or 0
    )

    payout_result = await db.execute(
        select(Payout, User)
        .join(User, Payout.user_id == User.id)
        .order_by(Payout.created_at.desc())
        .limit(200)
    )
    payouts_list = []
    campaign_cache = {}
    for payout, user in payout_result.all():
        campaign_title = ""
        if payout.campaign_id and payout.campaign_id > 0:
            if payout.campaign_id not in campaign_cache:
                c = await db.execute(select(Campaign).where(Campaign.id == payout.campaign_id))
                camp = c.scalar_one_or_none()
                campaign_cache[payout.campaign_id] = camp.title if camp else "N/A"
            campaign_title = campaign_cache[payout.campaign_id]
        else:
            campaign_title = "Aggregate"
        payouts_list.append({
            "id": payout.id,
            "user_email": user.email,
            "campaign_title": campaign_title,
            "amount": float(payout.amount),
            "status": payout.status,
            "breakdown": payout.breakdown or {},
            "created_at": payout.created_at,
        })

    return _render(
        "admin/payouts.html",
        total_pending=total_pending,
        total_paid=total_paid,
        total_failed=total_failed,
        payouts=payouts_list,
        result_msg=msg,
    )


@router.post("/payouts/run-payout", response_class=HTMLResponse)
async def run_payout(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    from app.services.payments import run_payout_cycle
    result = await run_payout_cycle(db)
    msg = f"Payout complete: {result['users_paid']} users, ${result['total_paid']:.2f} paid, {result['failures']} failures"

    # Re-fetch payout data
    total_pending = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "pending")
        ) or 0
    )
    total_paid = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "paid")
        ) or 0
    )
    total_failed = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "failed")
        ) or 0
    )

    payout_result = await db.execute(
        select(Payout, User)
        .join(User, Payout.user_id == User.id)
        .order_by(Payout.created_at.desc())
        .limit(200)
    )
    payouts_list = []
    campaign_cache = {}
    for payout, user in payout_result.all():
        campaign_title = ""
        if payout.campaign_id and payout.campaign_id > 0:
            if payout.campaign_id not in campaign_cache:
                c = await db.execute(select(Campaign).where(Campaign.id == payout.campaign_id))
                camp = c.scalar_one_or_none()
                campaign_cache[payout.campaign_id] = camp.title if camp else "N/A"
            campaign_title = campaign_cache[payout.campaign_id]
        else:
            campaign_title = "Aggregate"
        payouts_list.append({
            "id": payout.id,
            "user_email": user.email,
            "campaign_title": campaign_title,
            "amount": float(payout.amount),
            "status": payout.status,
            "breakdown": payout.breakdown or {},
            "created_at": payout.created_at,
        })

    return _render(
        "admin/payouts.html",
        total_pending=total_pending,
        total_paid=total_paid,
        total_failed=total_failed,
        payouts=payouts_list,
        result_msg=msg,
    )


# ---------------------------------------------------------------------------
# Platform Stats
# ---------------------------------------------------------------------------

@router.get("/platform-stats", response_class=HTMLResponse)
async def platform_stats_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    # Get per-platform post counts and success rates
    post_result = await db.execute(
        select(
            Post.platform,
            func.count(Post.id).label("total_posts"),
            func.sum(
                case((Post.status == "live", 1), else_=0)
            ).label("live_count"),
        )
        .group_by(Post.platform)
    )

    platform_data = {}
    for row in post_result.all():
        platform_name = row[0]
        total = row[1] or 0
        live = row[2] or 0
        platform_data[platform_name] = {
            "platform": platform_name,
            "total_posts": total,
            "live_count": live,
            "success_rate": (live / total * 100) if total > 0 else 0,
            "avg_impressions": 0.0,
            "avg_likes": 0.0,
            "avg_reposts": 0.0,
            "total_impressions": 0,
            "total_engagement": 0,
        }

    # Get per-platform metric aggregates via Post join
    metric_result = await db.execute(
        select(
            Post.platform,
            func.coalesce(func.avg(Metric.impressions), 0).label("avg_imp"),
            func.coalesce(func.avg(Metric.likes), 0).label("avg_likes"),
            func.coalesce(func.avg(Metric.reposts), 0).label("avg_reposts"),
            func.coalesce(func.sum(Metric.impressions), 0).label("total_imp"),
            func.coalesce(func.sum(Metric.likes), 0).label("total_likes"),
            func.coalesce(func.sum(Metric.reposts), 0).label("total_reposts"),
            func.coalesce(func.sum(Metric.comments), 0).label("total_comments"),
        )
        .select_from(Metric)
        .join(Post, Metric.post_id == Post.id)
        .where(Metric.is_final == True)
        .group_by(Post.platform)
    )

    for row in metric_result.all():
        platform_name = row[0]
        if platform_name not in platform_data:
            platform_data[platform_name] = {
                "platform": platform_name,
                "total_posts": 0,
                "live_count": 0,
                "success_rate": 0,
            }
        platform_data[platform_name]["avg_impressions"] = float(row[1])
        platform_data[platform_name]["avg_likes"] = float(row[2])
        platform_data[platform_name]["avg_reposts"] = float(row[3])
        platform_data[platform_name]["total_impressions"] = int(row[4])
        total_likes = int(row[5])
        total_reposts = int(row[6])
        total_comments = int(row[7])
        platform_data[platform_name]["total_engagement"] = (
            total_likes + total_reposts + total_comments
        )

    platforms = sorted(platform_data.values(), key=lambda x: x["total_posts"], reverse=True)

    total_posts = sum(p["total_posts"] for p in platforms)
    total_impressions = sum(p.get("total_impressions", 0) for p in platforms)
    total_engagement = sum(p.get("total_engagement", 0) for p in platforms)

    return _render(
        "admin/platform_stats.html",
        platforms=platforms,
        total_posts=total_posts,
        total_impressions=total_impressions,
        total_engagement=total_engagement,
    )


# ---------------------------------------------------------------------------
# Review Queue (Flagged Campaigns)
# ---------------------------------------------------------------------------

@router.get("/review-queue", response_class=HTMLResponse)
async def review_queue_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    result = await db.execute(
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

    flagged_list = []
    for log, campaign, company in result.all():
        flagged_list.append({
            "campaign_id": campaign.id,
            "company_name": company.name,
            "title": campaign.title,
            "flagged_keywords": log.flagged_keywords or [],
            "categories": log.screening_categories or [],
            "created_at": log.created_at,
        })

    return _render("admin/review_queue.html", flagged=flagged_list, result_msg=None)


@router.post("/review-queue/{campaign_id}/approve", response_class=HTMLResponse)
async def approve_flagged(
    campaign_id: int,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    log_result = await db.execute(
        select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
    )
    log = log_result.scalar_one_or_none()
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_result.scalar_one_or_none()

    if log and campaign and campaign.screening_status == "flagged":
        log.reviewed_by_admin = True
        log.review_result = "approved"
        campaign.screening_status = "approved"
        await db.flush()
        await db.commit()

    return RedirectResponse(url="/admin/review-queue", status_code=303)


@router.post("/review-queue/{campaign_id}/reject", response_class=HTMLResponse)
async def reject_flagged(
    campaign_id: int,
    reason: str = Form("Rejected by admin"),
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return RedirectResponse(url="/admin/login", status_code=303)

    log_result = await db.execute(
        select(ContentScreeningLog).where(ContentScreeningLog.campaign_id == campaign_id)
    )
    log = log_result.scalar_one_or_none()
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_result.scalar_one_or_none()

    if log and campaign and campaign.screening_status == "flagged":
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
        await db.commit()

    return RedirectResponse(url="/admin/review-queue", status_code=303)
