"""Company analytics dashboard — server-rendered HTML pages for companies."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_company
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric

router = APIRouter()

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Campaign Analytics — {company_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
        h1 {{ font-size: 24px; margin-bottom: 20px; }}
        h2 {{ font-size: 18px; margin: 24px 0 12px; color: #94a3b8; }}
        .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
        .stat {{ background: #1e293b; padding: 16px 24px; border-radius: 10px; min-width: 140px; }}
        .stat-val {{ font-size: 28px; font-weight: 700; color: #3b82f6; }}
        .stat-label {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ color: #64748b; font-size: 12px; text-transform: uppercase; font-weight: 600; }}
        td {{ font-size: 14px; }}
        .status {{ display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 12px; }}
        .status-active {{ background: #14532d; color: #86efac; }}
        .status-draft {{ background: #1e293b; color: #94a3b8; }}
        .status-completed {{ background: #064e3b; color: #6ee7b7; }}
        .status-paused {{ background: #713f12; color: #fde68a; }}
        .status-cancelled {{ background: #7f1d1d; color: #fca5a5; }}
        a {{ color: #60a5fa; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>Campaign Analytics</h1>
    <div class="stats">
        <div class="stat">
            <div class="stat-val">{total_campaigns}</div>
            <div class="stat-label">Total Campaigns</div>
        </div>
        <div class="stat">
            <div class="stat-val">{active_campaigns}</div>
            <div class="stat-label">Active</div>
        </div>
        <div class="stat">
            <div class="stat-val">${total_spent:.2f}</div>
            <div class="stat-label">Total Spent</div>
        </div>
        <div class="stat">
            <div class="stat-val">{total_reach:,}</div>
            <div class="stat-label">Total Reach</div>
        </div>
        <div class="stat">
            <div class="stat-val">{total_engagement:,}</div>
            <div class="stat-label">Total Engagement</div>
        </div>
        <div class="stat">
            <div class="stat-val">${balance:.2f}</div>
            <div class="stat-label">Balance</div>
        </div>
    </div>

    <h2>Campaigns</h2>
    <table>
        <thead>
            <tr><th>Title</th><th>Status</th><th>Budget</th><th>Remaining</th><th>Users</th><th>Posts</th><th>Impressions</th><th>Engagement</th><th>Actions</th></tr>
        </thead>
        <tbody>
            {campaign_rows}
        </tbody>
    </table>
</body>
</html>
"""

CAMPAIGN_ROW = """
<tr>
    <td>{title}</td>
    <td><span class="status status-{status}">{status}</span></td>
    <td>${budget_total:.2f}</td>
    <td>${budget_remaining:.2f}</td>
    <td>{user_count}</td>
    <td>{post_count}</td>
    <td>{impressions:,}</td>
    <td>{engagement:,}</td>
    <td><a href="/api/company/campaigns/{id}/analytics">Details</a></td>
</tr>
"""


@router.get("/company/dashboard", response_class=HTMLResponse)
async def company_dashboard(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    # Get all campaigns for this company
    result = await db.execute(
        select(Campaign).where(Campaign.company_id == company.id).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    total_spent = 0.0
    total_reach = 0
    total_engagement = 0
    active_count = 0
    campaign_rows = ""

    for c in campaigns:
        if c.status == "active":
            active_count += 1

        spent = float(c.budget_total) - float(c.budget_remaining)
        total_spent += spent

        # Get stats for this campaign
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

        # Get metrics
        metrics = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
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

        impressions = int(m.impressions)
        engagement = int(m.engagement)
        total_reach += impressions
        total_engagement += engagement

        campaign_rows += CAMPAIGN_ROW.format(
            id=c.id,
            title=c.title,
            status=c.status,
            budget_total=float(c.budget_total),
            budget_remaining=float(c.budget_remaining),
            user_count=row.user_count,
            post_count=row.post_count,
            impressions=impressions,
            engagement=engagement,
        )

    html = DASHBOARD_HTML.format(
        company_name=company.name,
        total_campaigns=len(campaigns),
        active_campaigns=active_count,
        total_spent=total_spent,
        total_reach=total_reach,
        total_engagement=total_engagement,
        balance=float(company.balance),
        campaign_rows=campaign_rows or "<tr><td colspan='9' style='text-align:center;color:#64748b'>No campaigns yet</td></tr>",
    )

    return HTMLResponse(content=html)


@router.get("/company/campaigns/{campaign_id}/analytics")
async def campaign_analytics(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Detailed analytics for a single campaign."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return {"error": "Campaign not found"}

    # Per-platform breakdown
    platform_stats = await db.execute(
        select(
            Post.platform,
            func.count(Post.id).label("post_count"),
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(Metric.likes), 0).label("likes"),
            func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
            func.coalesce(func.sum(Metric.comments), 0).label("comments"),
        )
        .select_from(Post)
        .outerjoin(Metric, and_(Metric.post_id == Post.id, Metric.is_final == True))
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
        .group_by(Post.platform)
    )

    platforms = []
    for row in platform_stats:
        platforms.append({
            "platform": row.platform,
            "posts": row.post_count,
            "impressions": int(row.impressions),
            "likes": int(row.likes),
            "reposts": int(row.reposts),
            "comments": int(row.comments),
        })

    # User count
    user_count = await db.scalar(
        select(func.count(func.distinct(CampaignAssignment.user_id)))
        .where(CampaignAssignment.campaign_id == campaign_id)
    )

    return {
        "campaign": {
            "id": campaign.id,
            "title": campaign.title,
            "status": campaign.status,
            "budget_total": float(campaign.budget_total),
            "budget_remaining": float(campaign.budget_remaining),
            "spent": float(campaign.budget_total) - float(campaign.budget_remaining),
        },
        "users": user_count,
        "platforms": platforms,
    }
