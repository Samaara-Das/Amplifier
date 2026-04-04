"""Admin audit log routes."""

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate_scalars, build_query_string,
)

router = APIRouter()


@router.get("/audit-log", response_class=HTMLResponse)
async def audit_log_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    action: str = "",
    target_type: str = "",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
        count_query = count_query.where(AuditLog.target_type == target_type)

    query = query.order_by(AuditLog.created_at.desc())
    pagination = await paginate_scalars(db, query, count_query, page, per_page=30)

    entries = []
    for e in pagination["items"]:
        entries.append({
            "id": e.id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "details": e.details or {},
            "admin_ip": e.admin_ip,
            "created_at": e.created_at,
        })

    # Get distinct action types for filter dropdown
    action_types_result = await db.execute(
        select(AuditLog.action).distinct().order_by(AuditLog.action)
    )
    action_types = [r[0] for r in action_types_result.all()]

    qs = build_query_string(action=action, target_type=target_type)

    return _render(
        "admin/audit_log.html",
        active_page="audit",
        entries=entries,
        pagination=pagination,
        action_filter=action,
        target_type_filter=target_type,
        action_types=action_types,
        qs=qs,
    )
