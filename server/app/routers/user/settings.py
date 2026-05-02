"""Creator settings page."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent_command import AgentCommand
from app.models.agent_status import AgentStatus
from app.models.user import User
from app.routers.user import _render, _login_redirect, get_user_from_cookie

router = APIRouter()

# Active platforms only — X is hardcoded-disabled (Task #40),
# TikTok and Instagram are disabled in config/platforms.json.
_ACTIVE_PLATFORMS = ["linkedin", "facebook", "reddit"]


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    action: str = "",
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    # Build connected platforms list (active platforms only)
    platforms_raw = user.platforms or {}
    connected_platforms = []
    for platform in _ACTIVE_PLATFORMS:
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

    # Fetch agent status for initial badge render
    status_result = await db.execute(
        select(AgentStatus).where(AgentStatus.user_id == user.id)
    )
    agent_status = status_result.scalar_one_or_none()

    action_msgs = {
        "pause_queued": "Pause command queued — agent will pause within 30s.",
        "resume_queued": "Resume command queued — agent will resume within 30s.",
    }

    last_seen_iso = (
        agent_status.last_seen.isoformat()
        if agent_status and agent_status.last_seen
        else None
    )

    return _render(
        "user/settings.html",
        user=user,
        active_page="settings",
        connected_platforms=connected_platforms,
        agent_status=agent_status,
        last_seen_iso=last_seen_iso,
        action_msg=action_msgs.get(action, ""),
    )


@router.post("/settings/pause-agent")
async def pause_agent(
    request: Request,
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Insert a pause_agent AgentCommand for the daemon to pick up."""
    if not user:
        return _login_redirect()

    cmd = AgentCommand(
        user_id=user.id,
        type="pause_agent",
        payload={},
        status="pending",
    )
    db.add(cmd)
    await db.flush()

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        html = (
            '<div id="agent-cmd-result" style="color:#86efac;font-size:13px;margin-top:8px;">'
            "Pause command queued — agent will pause within 30s."
            "</div>"
        )
        return HTMLResponse(html, status_code=200)
    return RedirectResponse(url="/user/settings?action=pause_queued", status_code=303)


@router.post("/settings/resume-agent")
async def resume_agent(
    request: Request,
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Insert a resume_agent AgentCommand for the daemon to pick up."""
    if not user:
        return _login_redirect()

    cmd = AgentCommand(
        user_id=user.id,
        type="resume_agent",
        payload={},
        status="pending",
    )
    db.add(cmd)
    await db.flush()

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        html = (
            '<div id="agent-cmd-result" style="color:#86efac;font-size:13px;margin-top:8px;">'
            "Resume command queued — agent will resume within 30s."
            "</div>"
        )
        return HTMLResponse(html, status_code=200)
    return RedirectResponse(url="/user/settings?action=resume_queued", status_code=303)
