"""Creator posts — paginated global post list."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.routers.user import _render, _login_redirect, get_user_from_cookie, paginate_scalars

router = APIRouter()

_PER_PAGE = 20


@router.get("/posts", response_class=HTMLResponse)
async def posts_page(
    request: Request,
    page: int = 1,
    platform: str | None = None,
    status: str | None = None,
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    is_htmx = request.headers.get("HX-Request") == "true"

    posts_data, pagination = await _load_posts(db, user.id, page, platform, status)

    ctx = dict(
        user=user,
        active_page="posts",
        posts=posts_data,
        pagination=pagination,
        platform=platform,
        status=status,
    )

    if is_htmx:
        return _render("user/_posts_table.html", **ctx)
    return _render("user/posts.html", **ctx)


async def _load_posts(db, user_id, page, platform_filter, status_filter):
    filters = [CampaignAssignment.user_id == user_id]
    if platform_filter:
        filters.append(Post.platform == platform_filter)
    if status_filter:
        filters.append(Post.status == status_filter)

    base_query = (
        select(Post)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(and_(*filters))
        .order_by(Post.posted_at.desc())
    )
    count_query = (
        select(func.count()).select_from(Post)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(and_(*filters))
    )

    pagination = await paginate_scalars(db, base_query, count_query, page=page, per_page=_PER_PAGE)

    posts_data = []
    for post in pagination["items"]:
        latest_metric = max(post.metrics, key=lambda m: m.id) if post.metrics else None
        posts_data.append({
            "id": post.id,
            "platform": post.platform,
            "post_url": post.post_url,
            "posted_at": post.posted_at,
            "status": post.status,
            "impressions": latest_metric.impressions if latest_metric else 0,
            "likes": latest_metric.likes if latest_metric else 0,
            "comments": latest_metric.comments if latest_metric else 0,
            "reposts": latest_metric.reposts if latest_metric else 0,
        })

    pagination["items"] = posts_data
    return posts_data, pagination
