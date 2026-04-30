"""Creator settings page."""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.models.user import User
from app.routers.user import _render, _login_redirect, get_user_from_cookie

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    user: User | None = Depends(get_user_from_cookie),
):
    if not user:
        return _login_redirect()

    # Build connected platforms list (defensive handling of both data shapes)
    platforms_raw = user.platforms or {}
    connected_platforms = []
    all_platforms = ["linkedin", "facebook", "reddit", "x", "tiktok", "instagram"]
    for platform in all_platforms:
        val = platforms_raw.get(platform)
        if isinstance(val, dict):
            connected = val.get("connected", False)
            username = val.get("username", "")
        elif val:
            connected = True
            username = ""
        else:
            connected = False
            username = ""
        connected_platforms.append({
            "name": platform,
            "label": platform.title(),
            "connected": connected,
            "username": username,
        })

    return _render(
        "user/settings.html",
        user=user,
        active_page="settings",
        connected_platforms=connected_platforms,
    )
