"""Admin overview dashboard."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
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
from app.routers.admin import _render, _check_admin, _login_redirect

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def overview(admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # Current counts
    total_users = await db.scalar(select(func.count()).select_from(User)) or 0
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.status == "active")
    ) or 0
    total_companies = await db.scalar(select(func.count()).select_from(Company)) or 0
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

    # Platform revenue
    total_budget_spent = float(
        await db.scalar(
            select(func.coalesce(func.sum(Campaign.budget_total - Campaign.budget_remaining), 0))
            .select_from(Campaign)
        ) or 0
    )
    platform_revenue = total_budget_spent - total_payouts

    # Trends (this week vs last week)
    new_users_this_week = await db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= week_ago)
    ) or 0
    new_users_last_week = await db.scalar(
        select(func.count()).select_from(User).where(
            User.created_at >= two_weeks_ago, User.created_at < week_ago
        )
    ) or 0

    new_campaigns_this_week = await db.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.created_at >= week_ago)
    ) or 0

    new_posts_this_week = await db.scalar(
        select(func.count()).select_from(Post).where(Post.created_at >= week_ago)
    ) or 0

    # Health indicators
    pending_reviews = await db.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.screening_status == "flagged")
    ) or 0
    pending_payouts_count = await db.scalar(
        select(func.count()).select_from(Payout).where(Payout.status == "pending")
    ) or 0
    low_trust_users = await db.scalar(
        select(func.count()).select_from(User).where(User.trust_score < 20, User.status == "active")
    ) or 0
    suspended_users = await db.scalar(
        select(func.count()).select_from(User).where(User.status == "suspended")
    ) or 0

    # Recent activity: mixed feed from assignments, users, campaigns
    result = await db.execute(
        select(CampaignAssignment, User, Campaign)
        .join(User, CampaignAssignment.user_id == User.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .order_by(CampaignAssignment.assigned_at.desc())
        .limit(15)
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
        active_page="overview",
        total_users=total_users,
        active_users=active_users,
        total_companies=total_companies,
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_posts=total_posts,
        total_payouts=total_payouts,
        platform_revenue=platform_revenue,
        new_users_this_week=new_users_this_week,
        new_users_last_week=new_users_last_week,
        new_campaigns_this_week=new_campaigns_this_week,
        new_posts_this_week=new_posts_this_week,
        pending_reviews=pending_reviews,
        pending_payouts_count=pending_payouts_count,
        low_trust_users=low_trust_users,
        suspended_users=suspended_users,
        recent=recent,
    )
