"""Company dashboard — modular router package."""

import os
from math import ceil

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.company import Company

# ── Config ────────────────────────────────────────────────────────────────────

settings = get_settings()
_template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


def _login_redirect():
    return RedirectResponse(url="/company/login", status_code=302)


async def get_company_from_cookie(
    company_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> Company | None:
    """Extract company from JWT cookie. Returns None if not authenticated."""
    if not company_token:
        return None
    try:
        payload = decode_token(company_token)
    except Exception:
        return None
    if payload.get("type") != "company":
        return None
    company_id = payload.get("sub")
    if not company_id:
        return None
    result = await db.execute(select(Company).where(Company.id == int(company_id)))
    return result.scalar_one_or_none()


async def paginate(db: AsyncSession, query, count_query, page: int = 1, per_page: int = 25):
    """Standard pagination helper."""
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
    """Pagination for scalar results."""
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


def build_query_string(**params) -> str:
    """Build URL query string, omitting empty/None values and 'page'."""
    parts = []
    for k, v in params.items():
        if v is not None and v != "" and k != "page":
            parts.append(f"{k}={v}")
    return "&".join(parts)


# ── Import sub-routers and build combined router ─────────────────────────────

router = APIRouter()

from app.routers.company.login import router as login_router
from app.routers.company.dashboard import router as dashboard_router
from app.routers.company.campaigns import router as campaigns_router
from app.routers.company.billing import router as billing_router
from app.routers.company.influencers import router as influencers_router
from app.routers.company.stats import router as stats_router
from app.routers.company.settings import router as settings_router

router.include_router(login_router)
router.include_router(dashboard_router)
router.include_router(campaigns_router)
router.include_router(billing_router)
router.include_router(influencers_router)
router.include_router(stats_router)
router.include_router(settings_router)
