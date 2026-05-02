"""Creator dashboard — overview page."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.assignment import CampaignAssignment
from app.models.draft import Draft
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.agent_status import AgentStatus
from app.routers.user import _render, _login_redirect, get_user_from_cookie

# Active platforms only — X disabled (Task #40), TikTok/IG disabled in platforms.json.
_ACTIVE_PLATFORMS = ["linkedin", "facebook", "reddit"]

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    # Count active assignments
    active_statuses = ("accepted", "content_generated", "posted", "metrics_collected")
    active_count = await db.scalar(
        select(func.count()).select_from(CampaignAssignment).where(
            CampaignAssignment.user_id == user.id,
            CampaignAssignment.status.in_(active_statuses),
        )
    ) or 0

    # Count pending payout cents
    pending_cents = await db.scalar(
        select(func.coalesce(func.sum(Payout.amount_cents), 0)).where(
            Payout.user_id == user.id,
            Payout.status == "pending",
            Payout.campaign_id.isnot(None),
        )
    ) or 0

    # Recent 5 posts
    recent_result = await db.execute(
        select(Post, CampaignAssignment)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(CampaignAssignment.user_id == user.id)
        .order_by(Post.posted_at.desc())
        .limit(5)
    )
    recent_posts = []
    for post, assignment in recent_result.all():
        # Latest metric
        latest_metric = None
        if post.metrics:
            latest_metric = max(post.metrics, key=lambda m: m.id)
        recent_posts.append({
            "id": post.id,
            "platform": post.platform,
            "post_url": post.post_url,
            "posted_at": post.posted_at,
            "status": post.status,
            "assignment_status": assignment.status,
            "campaign_id": assignment.campaign_id,
            "impressions": latest_metric.impressions if latest_metric else 0,
            "likes": latest_metric.likes if latest_metric else 0,
        })

    # 30-day earnings sparkline data (daily totals from payouts)
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sparkline_result = await db.execute(
        select(Payout).where(
            Payout.user_id == user.id,
            Payout.created_at >= thirty_days_ago,
            Payout.campaign_id.isnot(None),
        ).order_by(Payout.created_at)
    )
    payouts_30d = sparkline_result.scalars().all()

    # Build daily buckets (last 30 days, index 0 = oldest)
    daily_earnings = [0.0] * 30
    for p in payouts_30d:
        created = p.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta_days = (now - created).days
        if 0 <= delta_days < 30:
            bucket = 29 - delta_days
            daily_earnings[bucket] += p.amount_cents / 100.0

    # Connected platforms — active platforms only (X/TikTok/IG filtered out)
    platforms_raw = user.platforms or {}
    connected_platforms = []
    for platform in _ACTIVE_PLATFORMS:
        val = platforms_raw.get(platform)
        if isinstance(val, dict):
            if val.get("connected"):
                connected_platforms.append(platform)
        elif val:
            connected_platforms.append(platform)

    # Fetch agent status for initial badge render
    status_result = await db.execute(
        select(AgentStatus).where(AgentStatus.user_id == user.id)
    )
    agent_status = status_result.scalar_one_or_none()

    # Build per-platform health dict for template
    platform_health = {}
    if agent_status and agent_status.platform_health:
        for p in _ACTIVE_PLATFORMS:
            platform_health[p] = agent_status.platform_health.get(p)

    # Count pending drafts for "drafts ready" widget
    drafts_ready_count = await db.scalar(
        select(func.count()).select_from(Draft).where(
            Draft.user_id == user.id,
            Draft.status == "pending",
        )
    ) or 0

    last_seen_iso = (
        agent_status.last_seen.isoformat()
        if agent_status and agent_status.last_seen
        else None
    )

    return _render(
        "user/dashboard.html",
        user=user,
        active_page="dashboard",
        active_count=active_count,
        pending_cents=pending_cents,
        recent_posts=recent_posts,
        connected_platforms=connected_platforms,
        daily_earnings=daily_earnings,
        agent_status=agent_status,
        last_seen_iso=last_seen_iso,
        platform_health=platform_health,
        active_platforms=_ACTIVE_PLATFORMS,
        drafts_ready_count=drafts_ready_count,
    )
