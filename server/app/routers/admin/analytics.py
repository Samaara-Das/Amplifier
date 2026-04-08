"""Admin platform analytics routes."""

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.post import Post
from app.models.metric import Metric
from app.services.metric_helpers import latest_metric_filter
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.routers.admin import _render, _check_admin, _login_redirect

router = APIRouter()


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    # Per-platform post counts and success rates
    post_result = await db.execute(
        select(
            Post.platform,
            func.count(Post.id).label("total_posts"),
            func.sum(case((Post.status == "live", 1), else_=0)).label("live_count"),
        ).group_by(Post.platform)
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
            "success_rate": round((live / total * 100), 1) if total > 0 else 0,
            "avg_impressions": 0.0,
            "avg_likes": 0.0,
            "avg_reposts": 0.0,
            "total_impressions": 0,
            "total_likes": 0,
            "total_reposts": 0,
            "total_comments": 0,
            "total_engagement": 0,
        }

    # Per-platform metric aggregates
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
        .where(latest_metric_filter())
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
        platform_data[platform_name]["avg_impressions"] = round(float(row[1]), 1)
        platform_data[platform_name]["avg_likes"] = round(float(row[2]), 1)
        platform_data[platform_name]["avg_reposts"] = round(float(row[3]), 1)
        platform_data[platform_name]["total_impressions"] = int(row[4])
        total_likes = int(row[5])
        total_reposts = int(row[6])
        total_comments = int(row[7])
        platform_data[platform_name]["total_likes"] = total_likes
        platform_data[platform_name]["total_reposts"] = total_reposts
        platform_data[platform_name]["total_comments"] = total_comments
        platform_data[platform_name]["total_engagement"] = total_likes + total_reposts + total_comments

    platforms = sorted(platform_data.values(), key=lambda x: x["total_posts"], reverse=True)
    total_posts = sum(p["total_posts"] for p in platforms)
    total_impressions = sum(p.get("total_impressions", 0) for p in platforms)
    total_engagement = sum(p.get("total_engagement", 0) for p in platforms)

    # Top performing posts
    top_posts_result = await db.execute(
        select(
            Post, Metric, User,
        )
        .select_from(Post)
        .join(Metric, Metric.post_id == Post.id)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(latest_metric_filter())
        .order_by((Metric.likes + Metric.reposts + Metric.comments).desc())
        .limit(10)
    )
    top_posts = []
    for post, metric, user in top_posts_result.all():
        top_posts.append({
            "post_url": post.post_url,
            "platform": post.platform,
            "user_email": user.email,
            "impressions": metric.impressions,
            "likes": metric.likes,
            "reposts": metric.reposts,
            "comments": metric.comments,
            "total_engagement": metric.likes + metric.reposts + metric.comments,
        })

    return _render(
        "admin/analytics.html",
        active_page="analytics",
        platforms=platforms,
        total_posts=total_posts,
        total_impressions=total_impressions,
        total_engagement=total_engagement,
        top_posts=top_posts,
    )
