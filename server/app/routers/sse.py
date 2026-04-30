"""
sse.py — Server-Sent Events router (skeleton).

Endpoints:
  GET /sse/admin/overview           — Admin overview stream (admin auth)
  GET /sse/campaign/{campaign_id}/metrics — Campaign metrics stream (company auth, must own)
  GET /sse/user/agent-status        — User daemon status stream (user auth)

Each endpoint sends a heartbeat ping at a configurable interval.
Real event wiring comes in a later chunk.

UAT flag: AMPLIFIER_UAT_SSE_HEARTBEAT_MS (default 30000 ms)
"""

import asyncio
import json
import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.admin import ADMIN_TOKEN_VALUE, _check_admin
from app.routers.company import get_company_from_cookie

router = APIRouter(prefix="/sse", tags=["sse"])

# UAT knob: shorten heartbeat interval for fast automated tests
_HEARTBEAT_MS = int(os.environ.get("AMPLIFIER_UAT_SSE_HEARTBEAT_MS", "30000"))
_HEARTBEAT_SEC = _HEARTBEAT_MS / 1000.0


# ── Admin overview stream ─────────────────────────────────────────────────────

@router.get("/admin/overview")
async def sse_admin_overview(
    request: Request,
    admin_token: str | None = Cookie(None),
):
    """Stream admin-overview events. Requires admin cookie."""
    if not _check_admin(admin_token):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    async def generator():
        # Initial connection acknowledgement
        yield {"event": "connected", "data": json.dumps({"stream": "admin/overview"})}
        # Heartbeat loop
        while True:
            if await request.is_disconnected():
                break
            yield {"event": "ping", "data": json.dumps({"alive": True})}
            await asyncio.sleep(_HEARTBEAT_SEC)

    return EventSourceResponse(generator())


# ── Campaign metrics stream ───────────────────────────────────────────────────

@router.get("/campaign/{campaign_id}/metrics")
async def sse_campaign_metrics(
    campaign_id: int,
    request: Request,
    company_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Stream campaign-metrics events for a specific campaign. Company must own it."""
    from sqlalchemy import select
    from app.models.campaign import Campaign

    company = await get_company_from_cookie(company_token=company_token, db=db)
    if company is None:
        raise HTTPException(status_code=403, detail="Company authentication required")

    # Verify ownership
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.company_id == company.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found or access denied")

    async def generator():
        yield {
            "event": "connected",
            "data": json.dumps({"stream": f"campaign/{campaign_id}/metrics"}),
        }
        while True:
            if await request.is_disconnected():
                break
            yield {"event": "ping", "data": json.dumps({"alive": True})}
            await asyncio.sleep(_HEARTBEAT_SEC)

    return EventSourceResponse(generator())


# ── User daemon-status stream ─────────────────────────────────────────────────

@router.get("/user/agent-status")
async def sse_user_agent_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # User JWT is sent via Authorization: Bearer header by htmx-defaults.js.
    # We accept it here via the standard security dependency.
):
    """Stream user daemon-status events. Requires user JWT (Bearer token)."""
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from app.core.security import decode_token
    from app.models.user import User
    from sqlalchemy import select

    # Manually extract Bearer token so we can return SSE errors gracefully
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="User authentication required")
    token_str = auth_header[len("Bearer "):]
    try:
        payload = decode_token(token_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "user":
        raise HTTPException(status_code=403, detail="Not a user token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    async def generator():
        yield {
            "event": "connected",
            "data": json.dumps({"stream": "user/agent-status", "user_id": user.id}),
        }
        while True:
            if await request.is_disconnected():
                break
            yield {"event": "ping", "data": json.dumps({"alive": True})}
            await asyncio.sleep(_HEARTBEAT_SEC)

    return EventSourceResponse(generator())
