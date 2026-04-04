"""Admin user management routes."""

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.assignment import CampaignAssignment
from app.models.campaign import Campaign
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.penalty import Penalty
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate_scalars,
    log_admin_action, build_query_string,
)

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    search: str = "",
    status: str = "",
    sort: str = "created_at",
    order: str = "desc",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
        count_query = count_query.where(User.email.ilike(f"%{search}%"))
    if status:
        query = query.where(User.status == status)
        count_query = count_query.where(User.status == status)

    sort_col = {
        "trust_score": User.trust_score,
        "total_earned": User.total_earned,
        "email": User.email,
    }.get(sort, User.created_at)

    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pagination = await paginate_scalars(db, query, count_query, page, per_page=25)

    users_list = []
    for u in pagination["items"]:
        platform_count = len([k for k, v in (u.platforms or {}).items() if isinstance(v, dict) and v.get("connected")])
        users_list.append({
            "id": u.id,
            "email": u.email,
            "trust_score": u.trust_score,
            "mode": u.mode,
            "platform_count": platform_count,
            "total_earned": float(u.total_earned),
            "status": u.status,
            "created_at": u.created_at,
        })

    qs = build_query_string(search=search, status=status, sort=sort, order=order)

    return _render(
        "admin/users.html",
        active_page="users",
        users=users_list,
        pagination=pagination,
        search=search,
        current_status=status,
        sort=sort,
        order=order,
        qs=qs,
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: int,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return _render("admin/users.html", active_page="users", users=[], pagination={"items": [], "page": 1, "pages": 1, "total": 0, "has_prev": False, "has_next": False}, search="", current_status="", sort="created_at", order="desc", qs="")

    # Get assignments with campaign titles
    assign_result = await db.execute(
        select(CampaignAssignment, Campaign)
        .join(Campaign, CampaignAssignment.campaign_id == Campaign.id)
        .where(CampaignAssignment.user_id == user_id)
        .order_by(CampaignAssignment.assigned_at.desc())
        .limit(50)
    )
    assignments = []
    for a, c in assign_result.all():
        assignments.append({
            "id": a.id,
            "campaign_id": c.id,
            "campaign_title": c.title,
            "status": a.status,
            "content_mode": a.content_mode,
            "assigned_at": a.assigned_at,
        })

    # Get posts with metrics
    post_result = await db.execute(
        select(Post, CampaignAssignment)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(CampaignAssignment.user_id == user_id)
        .order_by(Post.posted_at.desc())
        .limit(50)
    )
    posts = []
    for p, a in post_result.all():
        # Get latest metric for this post
        metric_result = await db.execute(
            select(Metric).where(Metric.post_id == p.id).order_by(Metric.created_at.desc()).limit(1)
        )
        metric = metric_result.scalar_one_or_none()
        posts.append({
            "id": p.id,
            "platform": p.platform,
            "post_url": p.post_url,
            "status": p.status,
            "posted_at": p.posted_at,
            "impressions": metric.impressions if metric else 0,
            "likes": metric.likes if metric else 0,
            "reposts": metric.reposts if metric else 0,
        })

    # Get payouts
    payout_result = await db.execute(
        select(Payout).where(Payout.user_id == user_id).order_by(Payout.created_at.desc()).limit(50)
    )
    payouts = []
    for p in payout_result.scalars().all():
        payouts.append({
            "id": p.id,
            "amount": float(p.amount),
            "status": p.status,
            "created_at": p.created_at,
        })

    # Get penalties
    penalty_result = await db.execute(
        select(Penalty).where(Penalty.user_id == user_id).order_by(Penalty.created_at.desc())
    )
    penalties = []
    for p in penalty_result.scalars().all():
        penalties.append({
            "id": p.id,
            "reason": p.reason,
            "amount": float(p.amount),
            "description": p.description,
            "appealed": p.appealed,
            "appeal_result": p.appeal_result,
            "created_at": p.created_at,
        })

    # Platform details
    platforms = user.platforms or {}
    connected_platforms = {k: v for k, v in platforms.items() if isinstance(v, dict) and v.get("connected")}

    return _render(
        "admin/user_detail.html",
        active_page="users",
        user={
            "id": user.id,
            "email": user.email,
            "trust_score": user.trust_score,
            "mode": user.mode,
            "status": user.status,
            "earnings_balance": float(user.earnings_balance),
            "total_earned": float(user.total_earned),
            "audience_region": user.audience_region,
            "niche_tags": user.niche_tags or [],
            "created_at": user.created_at,
        },
        connected_platforms=connected_platforms,
        assignments=assignments,
        posts=posts,
        payouts=payouts,
        penalties=penalties,
    )


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.status == "active":
        user.status = "suspended"
        await db.flush()
        await log_admin_action(db, request, "user_suspended", "user", user_id, {"email": user.email})
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.status == "suspended":
        user.status = "active"
        await db.flush()
        await log_admin_action(db, request, "user_unsuspended", "user", user_id, {"email": user.email})
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: int, request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.status != "banned":
        user.status = "banned"
        await db.flush()
        await log_admin_action(db, request, "user_banned", "user", user_id, {"email": user.email})
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/adjust-trust")
async def adjust_trust(
    user_id: int,
    request: Request,
    new_score: int = Form(...),
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        old_score = user.trust_score
        user.trust_score = max(0, min(100, new_score))
        await db.flush()
        await log_admin_action(db, request, "trust_adjusted", "user", user_id, {
            "email": user.email, "old_score": old_score, "new_score": user.trust_score,
        })
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)
