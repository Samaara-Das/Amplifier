"""Admin system settings routes."""

from fastapi import APIRouter, Cookie, Depends
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.routers.admin import _render, _check_admin, _login_redirect

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(admin_token: str = Cookie(None)):
    if not _check_admin(admin_token):
        return _login_redirect()

    settings = get_settings()

    # Mask sensitive values
    db_url = settings.database_url
    if "://" in db_url:
        parts = db_url.split("://", 1)
        db_url = parts[0] + "://" + parts[1][:10] + "..."

    stripe_status = "Configured" if settings.stripe_secret_key else "Not configured"
    supabase_status = "Configured" if settings.supabase_url else "Not configured"

    return _render(
        "admin/settings.html",
        active_page="settings",
        config={
            "platform_cut_percent": settings.platform_cut_percent,
            "min_payout_threshold": settings.min_payout_threshold,
            "jwt_algorithm": settings.jwt_algorithm,
            "jwt_expire_minutes": settings.jwt_access_token_expire_minutes,
            "debug": settings.debug,
            "database_url": db_url,
            "server_url": settings.server_url,
            "stripe_status": stripe_status,
            "supabase_status": supabase_status,
        },
    )
