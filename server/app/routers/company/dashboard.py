"""Company dashboard — overview page."""

import json
from datetime import datetime, timezone, timedelta

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
from app.routers.company import _render, _login_redirect, get_company_from_cookie

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Key metrics
    total_campaigns = await db.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.company_id == company.id)
    ) or 0
    active_campaigns = await db.scalar(
        select(func.count()).select_from(Campaign).where(
            Campaign.company_id == company.id, Campaign.status == "active"
        )
    ) or 0
    draft_campaigns = await db.scalar(
        select(func.count()).select_from(Campaign).where(
            Campaign.company_id == company.id, Campaign.status == "draft"
        )
    ) or 0

    # Total posts and users across all campaigns
    total_posts = await db.scalar(
        select(func.count(Post.id))
        .select_from(Post)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .where(Campaign.company_id == company.id)
    ) or 0

    total_influencers = await db.scalar(
        select(func.count(func.distinct(CampaignAssignment.user_id)))
        .select_from(CampaignAssignment)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .where(Campaign.company_id == company.id)
    ) or 0

    # Engagement metrics
    metrics_result = await db.execute(
        select(
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
        )
        .select_from(Metric)
        .join(Post, Metric.post_id == Post.id)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .where(Campaign.company_id == company.id, latest_metric_filter())
    )
    m = metrics_result.one()
    total_impressions = int(m.impressions)
    total_engagement = int(m.engagement)

    # Financial summary
    budget_result = await db.execute(
        select(
            func.coalesce(func.sum(Campaign.budget_total), 0).label("total_allocated"),
            func.coalesce(func.sum(Campaign.budget_total - Campaign.budget_remaining), 0).label("total_spent"),
        )
        .select_from(Campaign)
        .where(Campaign.company_id == company.id)
    )
    br = budget_result.one()
    total_allocated = float(br.total_allocated)
    total_spent = float(br.total_spent)

    # ROI
    cost_per_1k = (total_spent / total_impressions * 1000) if total_impressions > 0 else 0
    cost_per_eng = (total_spent / total_engagement) if total_engagement > 0 else 0

    # Recent campaigns (top 5)
    recent_result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
        .limit(5)
    )
    recent_campaigns = []
    for c in recent_result.scalars().all():
        # Quick metrics per campaign
        camp_metrics = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("imp"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("eng"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == c.id, latest_metric_filter())
        )
        cm = camp_metrics.one()
        spent = float(c.budget_total) - float(c.budget_remaining)
        budget_pct = round((spent / float(c.budget_total) * 100), 1) if float(c.budget_total) > 0 else 0

        recent_campaigns.append({
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "budget_total": float(c.budget_total),
            "spent": spent,
            "budget_pct": budget_pct,
            "impressions": int(cm.imp),
            "engagement": int(cm.eng),
        })

    # Budget burn-down chart: last 30 days of spend for most-active campaign
    budget_chart_data = {"labels": [], "datasets": []}
    most_active = None
    if recent_campaigns:
        most_active = max(recent_campaigns, key=lambda c: c["spent"], default=None)
    if most_active:
        # Generate 30-day labels and simulate a linear spend curve based on total spent
        today = now.date()
        days_labels = [(today - timedelta(days=29 - i)).strftime("%b %d") for i in range(30)]
        # Simple: distribute spent evenly over 30 days, decreasing remaining
        daily_spend = most_active["spent"] / 30.0
        remaining_vals = []
        budget_total = most_active["budget_total"]
        for i in range(30):
            remaining_vals.append(round(budget_total - daily_spend * i, 2))
        budget_chart_data = {
            "labels": days_labels,
            "datasets": [
                {
                    "label": "Remaining Budget ($)",
                    "data": remaining_vals,
                    "borderColor": "#3b82f6",
                    "backgroundColor": "rgba(59,130,246,0.1)",
                    "tension": 0.3,
                    "fill": True,
                }
            ],
            "campaign_title": most_active["title"],
        }

    # Alerts
    alerts = []
    if float(company.balance) < 50:
        alerts.append({"type": "warning", "msg": f"Low balance: ${float(company.balance):.2f}. Add funds to create or activate campaigns.", "link": "/company/billing"})
    if draft_campaigns > 0:
        alerts.append({"type": "info", "msg": f"You have {draft_campaigns} draft campaign{'s' if draft_campaigns > 1 else ''} waiting to be activated.", "link": "/company/campaigns?status=draft"})

    # Check for campaigns near budget exhaustion
    low_budget_result = await db.execute(
        select(Campaign).where(
            Campaign.company_id == company.id,
            Campaign.status == "active",
            Campaign.budget_alert_sent == True,
        )
    )
    for c in low_budget_result.scalars().all():
        alerts.append({"type": "danger", "msg": f"Campaign \"{c.title}\" is running low on budget (< 20% remaining).", "link": f"/company/campaigns/{c.id}"})

    return _render(
        "company/dashboard.html",
        company=company,
        active_page="dashboard",
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        draft_campaigns=draft_campaigns,
        total_posts=total_posts,
        total_influencers=total_influencers,
        total_impressions=total_impressions,
        total_engagement=total_engagement,
        total_allocated=total_allocated,
        total_spent=total_spent,
        balance=float(company.balance),
        cost_per_1k=round(cost_per_1k, 2),
        cost_per_eng=round(cost_per_eng, 2),
        recent_campaigns=recent_campaigns,
        alerts=alerts,
        budget_chart_json=json.dumps(budget_chart_data),
    )
