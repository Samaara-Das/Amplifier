"""Company statistics/analytics page."""

import json
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.services.metric_helpers import latest_metric_filter, latest_metric_join_condition
from app.routers.company import _render, _login_redirect, get_company_from_cookie

router = APIRouter()


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    # Get all campaigns
    result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    total_campaigns = len(campaigns)
    active_campaigns = sum(1 for c in campaigns if c.status == "active")

    total_spend = 0.0
    total_impressions = 0
    total_engagement = 0
    best_campaign = None
    best_campaign_efficiency = 0.0

    platform_engagement: dict[str, int] = defaultdict(int)
    monthly_spend: dict[str, float] = defaultdict(float)

    for c in campaigns:
        spent = float(c.budget_total) - float(c.budget_remaining)
        total_spend += spent

        if c.created_at:
            month_key = c.created_at.strftime("%Y-%m")
            monthly_spend[month_key] += spent

        metrics_q = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(and_(CampaignAssignment.campaign_id == c.id, latest_metric_filter()))
        )
        m = metrics_q.one()
        camp_impressions = int(m.impressions)
        camp_engagement = int(m.engagement)

        total_impressions += camp_impressions
        total_engagement += camp_engagement

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

        plat_q = await db.execute(
            select(
                Post.platform,
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
            )
            .select_from(Post)
            .outerjoin(Metric, latest_metric_join_condition())
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == c.id)
            .group_by(Post.platform)
        )
        for row in plat_q:
            platform_engagement[row.platform] += int(row.engagement)

    cost_per_1k = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0
    cost_per_eng = (total_spend / total_engagement) if total_engagement > 0 else 0

    best_platform = None
    if platform_engagement:
        best_plat = max(platform_engagement, key=platform_engagement.get)
        best_platform = {"name": best_plat, "engagement": platform_engagement[best_plat]}

    platform_breakdown = [
        {"name": p, "engagement": e}
        for p, e in sorted(platform_engagement.items(), key=lambda x: -x[1])
    ]

    monthly_spend_list = [
        {"month": k, "spend": round(v, 2)}
        for k, v in sorted(monthly_spend.items())
    ]

    # Chart JSON: post volume per month (reuse monthly_spend data as proxy)
    post_volume_chart = json.dumps({
        "labels": [m["month"] for m in monthly_spend_list],
        "datasets": [{
            "label": "Monthly Spend ($)",
            "data": [m["spend"] for m in monthly_spend_list],
            "backgroundColor": "rgba(59,130,246,0.7)",
        }],
    })

    # Chart JSON: platform mix doughnut
    platform_colors = {
        "x": "#1d9bf0", "linkedin": "#0a66c2", "facebook": "#1877f2",
        "reddit": "#ff4500", "tiktok": "#25f4ee", "instagram": "#e1306c",
    }
    platform_mix_chart = json.dumps({
        "labels": [p["name"] for p in platform_breakdown],
        "datasets": [{
            "data": [p["engagement"] for p in platform_breakdown],
            "backgroundColor": [platform_colors.get(p["name"], "#334155") for p in platform_breakdown],
        }],
    })

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
        active_page="stats",
        post_volume_chart_json=post_volume_chart,
        platform_mix_chart_json=platform_mix_chart,
    )
