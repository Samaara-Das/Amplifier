"""Admin fraud & trust center routes."""

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.penalty import Penalty
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate,
    log_admin_action, build_query_string,
)

router = APIRouter()


@router.get("/fraud", response_class=HTMLResponse)
async def fraud_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    search: str = "",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    # Summary stats
    total_penalties = await db.scalar(select(func.count()).select_from(Penalty)) or 0
    total_penalty_amount = float(
        await db.scalar(
            select(func.coalesce(func.sum(Penalty.amount), 0)).select_from(Penalty)
        ) or 0
    )
    pending_appeals = await db.scalar(
        select(func.count()).select_from(Penalty).where(
            Penalty.appealed == True, Penalty.appeal_result == None
        )
    ) or 0
    low_trust_count = await db.scalar(
        select(func.count()).select_from(User).where(User.trust_score < 20, User.status == "active")
    ) or 0

    # Penalties with user info (paginated)
    query = (
        select(Penalty, User)
        .join(User, Penalty.user_id == User.id)
    )
    count_query = select(func.count()).select_from(Penalty)

    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
        count_query = count_query.join(User, Penalty.user_id == User.id).where(User.email.ilike(f"%{search}%"))

    query = query.order_by(Penalty.created_at.desc())
    pagination = await paginate(db, query, count_query, page, per_page=25)

    penalties = []
    for penalty, user in pagination["items"]:
        penalties.append({
            "id": penalty.id,
            "user_id": penalty.user_id,
            "user_email": user.email,
            "reason": penalty.reason,
            "amount": float(penalty.amount),
            "description": penalty.description,
            "appealed": penalty.appealed,
            "appeal_result": penalty.appeal_result,
            "created_at": penalty.created_at,
        })

    qs = build_query_string(search=search)

    return _render(
        "admin/fraud.html",
        active_page="fraud",
        total_penalties=total_penalties,
        total_penalty_amount=total_penalty_amount,
        pending_appeals=pending_appeals,
        low_trust_count=low_trust_count,
        penalties=penalties,
        pagination=pagination,
        search=search,
        qs=qs,
        check_result=None,
    )


@router.post("/fraud/run-check", response_class=HTMLResponse)
async def fraud_run_check(request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()

    from app.services.trust import run_trust_check
    check_result = await run_trust_check(db)
    await log_admin_action(db, request, "trust_check_run", "system", 0, {
        "anomalies": len(check_result.get("anomalies", [])),
        "deletions": len(check_result.get("deletions", [])),
    })

    anomalies = check_result.get("anomalies", [])
    for a in anomalies:
        user_result = await db.execute(select(User).where(User.id == a["user_id"]))
        user = user_result.scalar_one_or_none()
        a["user_email"] = user.email if user else "Unknown"

    # Re-fetch penalties
    total_penalties = await db.scalar(select(func.count()).select_from(Penalty)) or 0
    total_penalty_amount = float(
        await db.scalar(select(func.coalesce(func.sum(Penalty.amount), 0)).select_from(Penalty)) or 0
    )
    pending_appeals = await db.scalar(
        select(func.count()).select_from(Penalty).where(Penalty.appealed == True, Penalty.appeal_result == None)
    ) or 0
    low_trust_count = await db.scalar(
        select(func.count()).select_from(User).where(User.trust_score < 20, User.status == "active")
    ) or 0

    penalty_result = await db.execute(
        select(Penalty, User).join(User, Penalty.user_id == User.id)
        .order_by(Penalty.created_at.desc()).limit(25)
    )
    penalties = []
    for penalty, user in penalty_result.all():
        penalties.append({
            "id": penalty.id,
            "user_id": penalty.user_id,
            "user_email": user.email,
            "reason": penalty.reason,
            "amount": float(penalty.amount),
            "description": penalty.description,
            "appealed": penalty.appealed,
            "appeal_result": penalty.appeal_result,
            "created_at": penalty.created_at,
        })

    return _render(
        "admin/fraud.html",
        active_page="fraud",
        total_penalties=total_penalties,
        total_penalty_amount=total_penalty_amount,
        pending_appeals=pending_appeals,
        low_trust_count=low_trust_count,
        penalties=penalties,
        pagination={"page": 1, "pages": 1, "total": len(penalties), "has_prev": False, "has_next": False},
        search="",
        qs="",
        check_result=check_result,
        anomalies=anomalies,
        deletions=check_result.get("deletions", []),
    )


@router.post("/fraud/penalties/{penalty_id}/approve-appeal")
async def approve_appeal(
    penalty_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Penalty).where(Penalty.id == penalty_id))
    penalty = result.scalar_one_or_none()
    if penalty and penalty.appealed and not penalty.appeal_result:
        penalty.appeal_result = "upheld"
        # Refund: restore trust points (approximate reversal)
        user_result = await db.execute(select(User).where(User.id == penalty.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.trust_score = min(100, user.trust_score + 10)
        await db.flush()
        await log_admin_action(db, request, "appeal_approved", "penalty", penalty_id, {
            "user_id": penalty.user_id, "reason": penalty.reason,
        })
    return RedirectResponse(url="/admin/fraud", status_code=303)


@router.post("/fraud/penalties/{penalty_id}/deny-appeal")
async def deny_appeal(
    penalty_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    if not _check_admin(admin_token):
        return _login_redirect()
    result = await db.execute(select(Penalty).where(Penalty.id == penalty_id))
    penalty = result.scalar_one_or_none()
    if penalty and penalty.appealed and not penalty.appeal_result:
        penalty.appeal_result = "denied"
        await db.flush()
        await log_admin_action(db, request, "appeal_denied", "penalty", penalty_id, {
            "user_id": penalty.user_id, "reason": penalty.reason,
        })
    return RedirectResponse(url="/admin/fraud", status_code=303)
