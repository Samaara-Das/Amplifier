"""Admin dashboard — modular router package."""

import os
from math import ceil

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog

# ── Config ────────────────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_TOKEN_VALUE = "valid"

_template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)

# Register shared filters
from app.utils.status_labels import display_status as _display_status
_env.filters["display_status"] = _display_status


# ── Shared helpers ────────────────────────────────────────────────────────────

def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


def _check_admin(admin_token: str | None) -> bool:
    return admin_token == ADMIN_TOKEN_VALUE


def _login_redirect():
    return RedirectResponse(url="/admin/login", status_code=303)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def paginate(db: AsyncSession, query, count_query, page: int = 1, per_page: int = 25):
    """Standard pagination helper. Returns dict with items + pagination metadata."""
    total = await db.scalar(count_query) or 0
    pages = max(1, ceil(total / per_page))
    page = max(1, min(page, pages))
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    return {
        "items": result.all(),
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


async def paginate_scalars(db: AsyncSession, query, count_query, page: int = 1, per_page: int = 25):
    """Pagination for scalar results (single model queries)."""
    total = await db.scalar(count_query) or 0
    pages = max(1, ceil(total / per_page))
    page = max(1, min(page, pages))
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    return {
        "items": result.scalars().all(),
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


async def log_admin_action(
    db: AsyncSession,
    request: Request,
    action: str,
    target_type: str,
    target_id: int,
    details: dict | None = None,
):
    """Write an audit log entry for an admin action."""
    entry = AuditLog(
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        admin_ip=_get_client_ip(request),
    )
    db.add(entry)
    await db.flush()


def build_query_string(**params) -> str:
    """Build URL query string from params, omitting None/empty values."""
    parts = []
    for k, v in params.items():
        if v is not None and v != "" and k != "page":
            parts.append(f"{k}={v}")
    return "&".join(parts)


# ── Import sub-routers and build combined router ─────────────────────────────

router = APIRouter()

from app.routers.admin.login import router as login_router
from app.routers.admin.overview import router as overview_router
from app.routers.admin.users import router as users_router
from app.routers.admin.companies import router as companies_router
from app.routers.admin.campaigns import router as campaigns_router
from app.routers.admin.financial import router as financial_router
from app.routers.admin.fraud import router as fraud_router
from app.routers.admin.analytics import router as analytics_router
from app.routers.admin.review import router as review_router
from app.routers.admin.settings import router as settings_router
from app.routers.admin.audit import router as audit_router

router.include_router(login_router)
router.include_router(overview_router)
router.include_router(users_router)
router.include_router(companies_router)
router.include_router(campaigns_router)
router.include_router(financial_router)
router.include_router(fraud_router)
router.include_router(analytics_router)
router.include_router(review_router)
router.include_router(settings_router)
router.include_router(audit_router)
