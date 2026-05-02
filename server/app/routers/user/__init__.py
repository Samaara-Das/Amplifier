"""Creator dashboard — modular router package."""

import os
from math import ceil

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.utils.status_labels import display_status

# ── Config ────────────────────────────────────────────────────────────────────

settings = get_settings()
_template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)
_env.filters["display_status"] = display_status


# ── Shared helpers ────────────────────────────────────────────────────────────

def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


def _login_redirect():
    return RedirectResponse(url="/user/login", status_code=302)


async def get_user_from_cookie(
    user_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Extract user from JWT cookie. Returns None if not authenticated."""
    if not user_token:
        return None
    try:
        payload = decode_token(user_token)
    except Exception:
        return None
    if payload.get("type") != "user":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == int(user_id)))
    return result.scalar_one_or_none()


async def paginate_scalars(db: AsyncSession, query, count_query, page: int = 1, per_page: int = 20):
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


# ── Import sub-routers and build combined router ─────────────────────────────

router = APIRouter()

from app.routers.user.login import router as login_router
from app.routers.user.dashboard import router as dashboard_router
from app.routers.user.campaigns import router as campaigns_router
from app.routers.user.posts import router as posts_router
from app.routers.user.earnings import router as earnings_router
from app.routers.user.settings import router as settings_router
from app.routers.user.stripe import router as stripe_router

router.include_router(login_router)
router.include_router(dashboard_router)
router.include_router(campaigns_router)
router.include_router(posts_router)
router.include_router(earnings_router)
router.include_router(settings_router)
router.include_router(stripe_router)
