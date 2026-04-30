"""Creator campaigns — list + detail pages."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.assignment import CampaignAssignment
from app.models.campaign import Campaign
from app.models.post import Post
from app.models.metric import Metric
from app.routers.user import _render, _login_redirect, get_user_from_cookie

router = APIRouter()

_INVITATION_STATUSES = ("pending_invitation",)
_ACTIVE_STATUSES = ("accepted", "content_generated", "posted", "metrics_collected")
_COMPLETED_STATUSES = ("paid", "rejected", "expired")


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(
    request: Request,
    tab: str = "invitations",
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    tab = tab if tab in ("invitations", "active", "completed") else "invitations"

    invitations = await _load_invitations(db, user.id)
    active = await _load_active(db, user.id)
    completed = await _load_completed(db, user.id)

    return _render(
        "user/campaigns.html",
        user=user,
        active_page="campaigns",
        tab=tab,
        invitations=invitations,
        active=active,
        completed=completed,
    )


@router.get("/campaigns/_tab/{tab_name}", response_class=HTMLResponse)
async def campaigns_tab_partial(
    tab_name: str,
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """HTMX partial — swap just the tab body."""
    if not user:
        return HTMLResponse("", status_code=401)

    if tab_name == "invitations":
        invitations = await _load_invitations(db, user.id)
        return _render("user/_invitations_list.html", invitations=invitations)
    elif tab_name == "active":
        active = await _load_active(db, user.id)
        return _render("user/_active_list.html", active=active)
    elif tab_name == "completed":
        completed = await _load_completed(db, user.id)
        return _render("user/_completed_list.html", completed=completed)
    return HTMLResponse("", status_code=404)


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(
    campaign_id: int,
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return _login_redirect()

    # Load assignment for this user+campaign
    result = await db.execute(
        select(CampaignAssignment)
        .options(
            selectinload(CampaignAssignment.campaign),
            selectinload(CampaignAssignment.posts).selectinload(Post.metrics),
        )
        .where(
            and_(
                CampaignAssignment.user_id == user.id,
                CampaignAssignment.campaign_id == campaign_id,
            )
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        return _render("user/campaigns.html", user=user, active_page="campaigns",
                       tab="active", invitations=[], active=[], completed=[],
                       error="Campaign not found or you are not assigned to it.")

    campaign = assignment.campaign

    # Aggregate metrics
    total_impressions = 0
    total_likes = 0
    total_comments = 0
    total_reposts = 0

    posts_data = []
    for post in assignment.posts:
        latest_metric = max(post.metrics, key=lambda m: m.id) if post.metrics else None
        imp = latest_metric.impressions if latest_metric else 0
        lk = latest_metric.likes if latest_metric else 0
        cm = latest_metric.comments if latest_metric else 0
        rp = latest_metric.reposts if latest_metric else 0
        total_impressions += imp
        total_likes += lk
        total_comments += cm
        total_reposts += rp
        posts_data.append({
            "id": post.id,
            "platform": post.platform,
            "post_url": post.post_url,
            "posted_at": post.posted_at,
            "status": post.status,
            "impressions": imp,
            "likes": lk,
            "comments": cm,
            "reposts": rp,
        })

    return _render(
        "user/campaign_detail.html",
        user=user,
        active_page="campaigns",
        campaign=campaign,
        assignment=assignment,
        posts=posts_data,
        total_impressions=total_impressions,
        total_likes=total_likes,
        total_comments=total_comments,
        total_reposts=total_reposts,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_invitations(db, user_id):
    now = _utcnow()
    result = await db.execute(
        select(CampaignAssignment)
        .options(selectinload(CampaignAssignment.campaign))
        .where(
            and_(
                CampaignAssignment.user_id == user_id,
                CampaignAssignment.status == "pending_invitation",
            )
        )
    )
    items = []
    for a in result.scalars().all():
        campaign = a.campaign
        exp = a.expires_at
        if exp and exp.tzinfo:
            exp = exp.replace(tzinfo=None)
        expired = exp is not None and exp < now
        items.append({
            "assignment_id": a.id,
            "campaign_id": campaign.id if campaign else None,
            "title": campaign.title if campaign else "Unknown",
            "brief": (campaign.brief[:200] + "...") if campaign and len(campaign.brief or "") > 200 else (campaign.brief if campaign else ""),
            "payout_rules": campaign.payout_rules if campaign else {},
            "expires_at": a.expires_at,
            "expired": expired,
            "invited_at": a.invited_at,
        })
    return items


async def _load_active(db, user_id):
    result = await db.execute(
        select(CampaignAssignment)
        .options(selectinload(CampaignAssignment.campaign))
        .where(
            and_(
                CampaignAssignment.user_id == user_id,
                CampaignAssignment.status.in_(_ACTIVE_STATUSES),
            )
        )
    )
    items = []
    for a in result.scalars().all():
        campaign = a.campaign
        items.append({
            "assignment_id": a.id,
            "campaign_id": campaign.id if campaign else None,
            "title": campaign.title if campaign else "Unknown",
            "brief": (campaign.brief[:200] + "...") if campaign and len(campaign.brief or "") > 200 else (campaign.brief if campaign else ""),
            "payout_rules": campaign.payout_rules if campaign else {},
            "status": a.status,
            "start_date": campaign.start_date if campaign else None,
            "end_date": campaign.end_date if campaign else None,
        })
    return items


async def _load_completed(db, user_id):
    result = await db.execute(
        select(CampaignAssignment)
        .options(selectinload(CampaignAssignment.campaign))
        .where(
            and_(
                CampaignAssignment.user_id == user_id,
                CampaignAssignment.status.in_(_COMPLETED_STATUSES),
            )
        )
    )
    items = []
    for a in result.scalars().all():
        campaign = a.campaign
        items.append({
            "assignment_id": a.id,
            "campaign_id": campaign.id if campaign else None,
            "title": campaign.title if campaign else "Unknown",
            "status": a.status,
            "responded_at": a.responded_at,
        })
    return items
