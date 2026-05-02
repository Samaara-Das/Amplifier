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
    db: AsyncSession = Depends(get_db),
):
    """Stream admin-overview KPI events. Requires admin cookie."""
    if not _check_admin(admin_token):
        raise HTTPException(status_code=401, detail="Admin authentication required")

    async def _query_kpis(session: AsyncSession) -> dict:
        from sqlalchemy import select, func
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.post import Post
        from app.models.company import Company

        active_users = await session.scalar(
            select(func.count()).select_from(User).where(User.status == "active")
        ) or 0
        active_campaigns = await session.scalar(
            select(func.count()).select_from(Campaign).where(Campaign.status == "active")
        ) or 0
        posts_today = await session.scalar(
            select(func.count()).select_from(Post).where(
                func.date(Post.posted_at) == func.current_date()
            )
        ) or 0
        total_companies_count = await session.scalar(
            select(func.count()).select_from(Company)
        ) or 0
        return {
            "active_users": active_users,
            "active_campaigns": active_campaigns,
            "posts_today": posts_today,
            "total_companies": total_companies_count,
        }

    async def generator():
        # Initial connection acknowledgement
        yield {"event": "connected", "data": json.dumps({"stream": "admin/overview"})}
        # KPI stream loop
        while True:
            if await request.is_disconnected():
                break
            try:
                kpis = await _query_kpis(db)
                yield {"event": "kpi_update", "data": json.dumps(kpis)}
            except Exception:
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

    async def _query_metrics(session: AsyncSession) -> dict:
        from sqlalchemy import func
        from app.models.post import Post
        from app.models.metric import Metric
        from app.models.assignment import CampaignAssignment
        from app.services.metric_helpers import latest_metric_filter

        posts_count = await session.scalar(
            select(func.count(Post.id))
            .select_from(Post)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == campaign_id)
        ) or 0

        metrics_q = await session.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("views"),
                func.coalesce(func.sum(Metric.likes), 0).label("likes"),
                func.coalesce(func.sum(Metric.comments), 0).label("comments"),
                func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == campaign_id, latest_metric_filter())
        )
        m = metrics_q.one()

        from app.models.campaign import Campaign as CampaignModel
        camp_row = await session.get(CampaignModel, campaign_id)
        budget_total = float(camp_row.budget_total) if camp_row else 0.0
        budget_remaining = float(camp_row.budget_remaining) if camp_row else 0.0
        spent = budget_total - budget_remaining

        return {
            "posts": posts_count,
            "views": int(m.views),
            "likes": int(m.likes),
            "comments": int(m.comments),
            "reposts": int(m.reposts),
            "spent_cents": int(spent * 100),
            "remaining_budget_cents": int(budget_remaining * 100),
        }

    async def generator():
        yield {
            "event": "connected",
            "data": json.dumps({"stream": f"campaign/{campaign_id}/metrics"}),
        }
        while True:
            if await request.is_disconnected():
                break
            try:
                metrics = await _query_metrics(db)
                yield {"event": "metrics_update", "data": json.dumps(metrics)}
            except Exception:
                yield {"event": "ping", "data": json.dumps({"alive": True})}
            await asyncio.sleep(_HEARTBEAT_SEC)

    return EventSourceResponse(generator())


# ── User daemon-status stream ─────────────────────────────────────────────────

@router.get("/user/agent-status")
async def sse_user_agent_status(
    request: Request,
    user_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Stream user daemon-status events. Requires user_token cookie.

    EventSource cannot send custom Authorization headers, so this endpoint
    auths via httponly cookie (same pattern as admin + company SSE endpoints).
    """
    from app.core.security import decode_token
    from app.models.user import User
    from sqlalchemy import select

    if not user_token:
        raise HTTPException(status_code=401, detail="User authentication required")
    try:
        payload = decode_token(user_token)
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

    from app.models.agent_status import AgentStatus as _AgentStatus

    _heartbeat_ms = int(os.environ.get("AMPLIFIER_UAT_SSE_HEARTBEAT_MS", 0))
    _sleep_sec = (_heartbeat_ms / 1000.0) if _heartbeat_ms > 0 else _HEARTBEAT_SEC

    async def generator():
        yield {
            "event": "connected",
            "data": json.dumps({"stream": "user/agent-status", "user_id": user.id}),
        }
        while True:
            if await request.is_disconnected():
                break
            # Query latest AgentStatus for this user and emit it
            try:
                status_result = await db.execute(
                    select(_AgentStatus).where(_AgentStatus.user_id == user.id)
                )
                status = status_result.scalar_one_or_none()
                if status is not None:
                    yield {
                        "event": "agent_status",
                        "data": json.dumps({
                            "running": status.running,
                            "paused": status.paused,
                            "platform_health": status.platform_health or {},
                            "ai_keys_configured": status.ai_keys_configured or {},
                            "version": status.version,
                        }),
                    }
                else:
                    yield {"event": "ping", "data": json.dumps({"alive": True})}
            except Exception:
                yield {"event": "ping", "data": json.dumps({"alive": True})}
            await asyncio.sleep(_sleep_sec)

    return EventSourceResponse(generator())
