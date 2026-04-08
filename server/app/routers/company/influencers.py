"""Company influencers page — cross-campaign influencer performance."""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.services.metric_helpers import latest_metric_filter
from app.models.payout import Payout
from app.models.user import User
from app.routers.company import _render, _login_redirect, get_company_from_cookie

router = APIRouter()


@router.get("/influencers", response_class=HTMLResponse)
async def influencers_page(
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
    search: str = "",
):
    if not company:
        return _login_redirect()

    # Get all users who have been assigned to any of this company's campaigns
    query = (
        select(
            User.id,
            User.email,
            User.platforms,
            User.trust_score,
            func.count(func.distinct(CampaignAssignment.campaign_id)).label("campaign_count"),
            func.count(Post.id).label("post_count"),
        )
        .select_from(CampaignAssignment)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .join(User, CampaignAssignment.user_id == User.id)
        .outerjoin(Post, Post.assignment_id == CampaignAssignment.id)
        .where(Campaign.company_id == company.id)
        .group_by(User.id, User.email, User.platforms, User.trust_score)
    )

    if search:
        query = query.where(User.email.ilike(f"%{search}%"))

    result = await db.execute(query.order_by(func.count(Post.id).desc()).limit(100))

    influencers = []
    for row in result.all():
        user_id = row[0]
        email = row[1]
        user_platforms = row[2] or {}
        trust_score = row[3]
        campaign_count = row[4]
        post_count = row[5]

        # Get metrics for all this user's posts across our campaigns
        metrics_q = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
            .where(Campaign.company_id == company.id, CampaignAssignment.user_id == user_id, latest_metric_filter())
        )
        m = metrics_q.one()

        # Total paid to this user across our campaigns
        paid_q = await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0))
            .select_from(Payout)
            .join(Campaign, Payout.campaign_id == Campaign.id)
            .where(Campaign.company_id == company.id, Payout.user_id == user_id)
        ) or 0

        # Connected platforms
        connected = []
        for plat, info in user_platforms.items():
            if isinstance(info, dict) and info.get("connected"):
                connected.append(plat)

        impressions = int(m.impressions)
        engagement = int(m.engagement)

        influencers.append({
            "id": user_id,
            "email": email,
            "trust_score": trust_score,
            "platforms": connected,
            "campaign_count": campaign_count,
            "post_count": post_count,
            "impressions": impressions,
            "engagement": engagement,
            "total_paid": float(paid_q),
            "engagement_rate": round((engagement / impressions * 100), 2) if impressions > 0 else 0,
        })

    # Sort by engagement descending
    influencers.sort(key=lambda x: x["engagement"], reverse=True)

    # Summary stats
    total_influencers = len(influencers)
    total_posts = sum(i["post_count"] for i in influencers)
    total_impressions = sum(i["impressions"] for i in influencers)
    total_engagement = sum(i["engagement"] for i in influencers)
    total_paid = sum(i["total_paid"] for i in influencers)

    return _render(
        "company/influencers.html",
        company=company,
        active_page="influencers",
        influencers=influencers,
        search=search,
        total_influencers=total_influencers,
        total_posts=total_posts,
        total_impressions=total_impressions,
        total_engagement=total_engagement,
        total_paid=total_paid,
    )
