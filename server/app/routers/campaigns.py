import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_company, get_current_user
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.models.company import Company
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.schemas.campaign import (
    CampaignCreate, CampaignUpdate, CampaignResponse, CampaignBrief,
    BudgetTopUp, WizardRequest, ReachEstimateRequest,
    CampaignPostCreate, CampaignPostResponse,
)
from app.models.campaign_post import CampaignPost
from app.services.matching import get_matched_campaigns
from app.utils.platform_guard import contains_disabled, is_platform_disabled

MINIMUM_CAMPAIGN_BUDGET = 50.0

router = APIRouter()


# ── Company endpoints ──────────────────────────────────────────────


@router.post("/company/campaigns", response_model=CampaignResponse)
async def create_campaign(
    data: CampaignCreate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    if data.budget_total < MINIMUM_CAMPAIGN_BUDGET:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum campaign budget is ${MINIMUM_CAMPAIGN_BUDGET:.2f}",
        )

    # Reject campaigns targeting disabled platforms
    required_platforms = (data.targeting.required_platforms or []) if data.targeting else []
    if contains_disabled(required_platforms):
        raise HTTPException(
            status_code=400,
            detail="Cannot target disabled platform: X is not supported. See docs/platform-posting-playbook.md.",
        )
    min_f = (data.targeting.min_followers or {}) if data.targeting else {}
    if is_platform_disabled("x") and min_f.get("x", 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot set min_followers_x: X is not supported. See docs/platform-posting-playbook.md.",
        )

    # Drafts don't require balance — only deduct on activation
    campaign = Campaign(
        company_id=company.id,
        title=data.title,
        brief=data.brief,
        assets=data.assets,
        budget_total=data.budget_total,
        budget_remaining=data.budget_total,
        payout_rules=data.payout_rules.model_dump(),
        targeting=data.targeting.model_dump(),
        content_guidance=data.content_guidance,
        penalty_rules=data.penalty_rules,
        start_date=data.start_date,
        end_date=data.end_date,
        max_users=data.max_users,
        status="draft",
        # Phase C fields
        campaign_type=data.campaign_type,
        campaign_goal=data.campaign_goal,
        tone=data.tone,
        preferred_formats=data.preferred_formats,
        disclaimer_text=data.disclaimer_text,
    )
    campaign.screening_status = "approved"
    db.add(campaign)
    await db.flush()

    return campaign


@router.post("/company/campaigns/ai-wizard")
async def ai_wizard(
    data: WizardRequest,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """AI generates a full campaign draft from wizard answers and optionally scraped company URLs.

    Does NOT create a campaign. Returns a generated draft for the company to
    review and edit before calling POST /api/company/campaigns.
    """
    from app.services.campaign_wizard import run_campaign_wizard
    result = await run_campaign_wizard(
        db=db,
        product_description=data.product_description,
        campaign_goal=data.campaign_goal,
        company_urls=data.company_urls or None,
        target_niches=data.target_niches or None,
        target_regions=data.target_regions or None,
        required_platforms=data.required_platforms or None,
        min_followers=data.min_followers or None,
        must_include=data.must_include or None,
        must_avoid=data.must_avoid or None,
        budget_range=data.budget_range,
        start_date=data.start_date,
        end_date=data.end_date,
    )
    return result


@router.post("/company/campaigns/reach-estimate")
async def reach_estimate(
    data: ReachEstimateRequest,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Estimate reach for targeting criteria before creating a campaign.

    Uses the same hard filters as the matching algorithm to count eligible users,
    then estimates impressions from follower counts and engagement rates.
    """
    from app.services.campaign_wizard import suggest_payout_rates, estimate_reach
    payout_rates = suggest_payout_rates(data.target_niches)
    result = await estimate_reach(
        db=db,
        niche_tags=data.target_niches or None,
        target_regions=data.target_regions or None,
        required_platforms=data.required_platforms or None,
        min_followers=data.min_followers or None,
        payout_rates=payout_rates,
    )
    return result


@router.get("/company/campaigns/{campaign_id}/reach-estimate")
async def campaign_reach_estimate(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
    niche_tags: str | None = Query(None, description="Comma-separated niche tags override"),
    required_platforms: str | None = Query(None, description="Comma-separated platforms override"),
    target_regions: str | None = Query(None, description="Comma-separated regions override"),
    min_followers_x: int | None = Query(None),
    min_followers_linkedin: int | None = Query(None),
    min_followers_facebook: int | None = Query(None),
    min_followers_reddit: int | None = Query(None),
):
    """Estimate reach for an existing campaign, with optional targeting overrides."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    targeting = campaign.targeting or {}

    # Use overrides if provided, otherwise fall back to campaign targeting
    niches = niche_tags.split(",") if niche_tags else targeting.get("niche_tags")
    platforms = required_platforms.split(",") if required_platforms else targeting.get("required_platforms")
    regions = target_regions.split(",") if target_regions else targeting.get("target_regions")

    min_f = targeting.get("min_followers", {})
    if min_followers_x is not None:
        min_f["x"] = min_followers_x
    if min_followers_linkedin is not None:
        min_f["linkedin"] = min_followers_linkedin
    if min_followers_facebook is not None:
        min_f["facebook"] = min_followers_facebook
    if min_followers_reddit is not None:
        min_f["reddit"] = min_followers_reddit

    from app.services.campaign_wizard import suggest_payout_rates, estimate_reach as _estimate_reach
    payout_rates = campaign.payout_rules or suggest_payout_rates(niches or [])

    estimate = await _estimate_reach(
        db=db,
        niche_tags=niches or None,
        target_regions=regions or None,
        required_platforms=platforms or None,
        min_followers=min_f or None,
        payout_rates=payout_rates,
    )
    return estimate


@router.get("/company/campaigns")
async def list_company_campaigns(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.company_id == company.id).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    out = []
    for campaign in campaigns:
        data = CampaignResponse.model_validate(campaign).model_dump()
        data["invitation_stats"] = {
            "total_invited": campaign.invitation_count or 0,
            "accepted": campaign.accepted_count or 0,
            "rejected": campaign.rejected_count or 0,
            "expired": campaign.expired_count or 0,
            "pending": (campaign.invitation_count or 0)
                       - (campaign.accepted_count or 0)
                       - (campaign.rejected_count or 0)
                       - (campaign.expired_count or 0),
        }
        out.append(data)
    return out


@router.get("/company/campaigns/{campaign_id}")
async def get_company_campaign(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    data = CampaignResponse.model_validate(campaign).model_dump()
    data["invitation_stats"] = {
        "total_invited": campaign.invitation_count or 0,
        "accepted": campaign.accepted_count or 0,
        "rejected": campaign.rejected_count or 0,
        "expired": campaign.expired_count or 0,
        "pending": (campaign.invitation_count or 0)
                   - (campaign.accepted_count or 0)
                   - (campaign.rejected_count or 0)
                   - (campaign.expired_count or 0),
    }

    # Per-user invitation status
    assignments_result = await db.execute(
        select(CampaignAssignment).where(
            CampaignAssignment.campaign_id == campaign_id
        )
    )
    assignments = assignments_result.scalars().all()
    data["invited_users"] = [
        {
            "user_id": a.user_id,
            "status": a.status,
            "invited_at": a.invited_at.isoformat() if a.invited_at else None,
            "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        }
        for a in assignments
    ]

    return data


@router.patch("/company/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate status transitions
    if data.status:
        valid_transitions = {
            "draft": ["active", "cancelled"],
            "active": ["paused", "cancelled"],
            "paused": ["active", "cancelled"],
        }
        allowed = valid_transitions.get(campaign.status, [])
        if data.status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {campaign.status} to {data.status}",
            )

        # Block activation if screening status is flagged (not yet reviewed)
        if data.status == "active" and campaign.screening_status == "flagged":
            raise HTTPException(
                status_code=400,
                detail="Campaign is flagged for content review and cannot be activated until approved by an admin.",
            )
        # Block activation if screening status is rejected
        if data.status == "active" and campaign.screening_status == "rejected":
            raise HTTPException(
                status_code=400,
                detail="Campaign was rejected during content review and cannot be activated.",
            )
        # Quality gate — campaign must score >= 85 to activate
        if data.status == "active":
            from app.services.campaign_quality import score_campaign_quality
            quality = await score_campaign_quality(campaign)
            if not quality["passed"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Campaign quality score {quality['score']}/100 (needs 85+). "
                           f"Issues: {'; '.join(quality['feedback'][:3])}",
                )

        # Deduct budget on activation (not on draft creation)
        if data.status == "active" and campaign.status == "draft":
            if float(company.balance) < float(campaign.budget_total):
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance (${float(company.balance):.2f}) to activate campaign (${float(campaign.budget_total):.2f} required). Add funds first.",
                )
            company.balance = float(company.balance) - float(campaign.budget_total)

        campaign.status = data.status

    content_changed = False
    if data.title is not None:
        campaign.title = data.title
        content_changed = True
    if data.brief is not None:
        campaign.brief = data.brief
        content_changed = True
    if data.assets is not None:
        campaign.assets = data.assets
        content_changed = True
    if data.content_guidance is not None:
        campaign.content_guidance = data.content_guidance
        content_changed = True

    # Increment version on content edits so user app detects changes
    if content_changed:
        campaign.campaign_version = (campaign.campaign_version or 1) + 1

    # Content screening deferred — auto-approve
    if content_changed:
        campaign.screening_status = "approved"

    await db.flush()
    return campaign


# ── Clone, Delete, Budget Top-up ──────────────────────────────────


@router.post("/company/campaigns/{campaign_id}/clone", response_model=CampaignResponse)
async def clone_campaign(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Clone a campaign: duplicate all fields, reset status to draft, zero counters."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Check company has enough balance for the cloned budget
    if float(company.balance) < float(original.budget_total):
        raise HTTPException(status_code=400, detail="Insufficient balance to clone campaign")

    clone = Campaign(
        company_id=company.id,
        title=original.title,
        brief=original.brief,
        assets=original.assets,
        budget_total=float(original.budget_total),
        budget_remaining=float(original.budget_total),
        payout_rules=original.payout_rules,
        targeting=original.targeting,
        content_guidance=original.content_guidance,
        penalty_rules=original.penalty_rules,
        company_urls=original.company_urls,
        ai_generated_brief=original.ai_generated_brief,
        budget_exhaustion_action=original.budget_exhaustion_action,
        # Reset: new draft, no dates, zero counters
        status="draft",
        start_date=original.start_date,
        end_date=original.end_date,
        budget_alert_sent=False,
        campaign_version=1,
        invitation_count=0,
        accepted_count=0,
        rejected_count=0,
        expired_count=0,
    )
    db.add(clone)

    # Deduct budget from company balance
    company.balance = float(company.balance) - float(original.budget_total)
    await db.flush()

    return clone


@router.delete("/company/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Delete a campaign. Only allowed if status is draft or cancelled."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("draft", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete campaign with status '{campaign.status}'. Only draft or cancelled campaigns can be deleted.",
        )

    # Refund budget_total back to company balance for draft campaigns
    if campaign.status == "draft":
        company.balance = float(company.balance) + float(campaign.budget_total)

    # Delete associated assignments
    await db.execute(
        delete(CampaignAssignment).where(
            CampaignAssignment.campaign_id == campaign_id
        )
    )

    await db.delete(campaign)
    await db.flush()

    return {"status": "deleted", "campaign_id": campaign_id}


@router.post("/company/campaigns/{campaign_id}/budget-topup", response_model=CampaignResponse)
async def budget_topup(
    campaign_id: int,
    data: BudgetTopUp,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Top up an active campaign's budget."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    if float(company.balance) < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Add to campaign budget
    campaign.budget_remaining = float(campaign.budget_remaining) + data.amount
    campaign.budget_total = float(campaign.budget_total) + data.amount

    # Deduct from company balance
    company.balance = float(company.balance) - data.amount

    # Resume auto-paused campaign
    if campaign.status == "paused" and campaign.budget_exhaustion_action == "auto_pause":
        campaign.status = "active"

    # Reset budget alert if budget is now above 20%
    if float(campaign.budget_remaining) >= 0.2 * float(campaign.budget_total):
        campaign.budget_alert_sent = False

    await db.flush()
    return campaign


# ── Repost Campaign Posts (pre-written content) ──────────────────


@router.post(
    "/company/campaigns/{campaign_id}/posts",
    response_model=CampaignPostResponse,
    status_code=201,
)
async def add_campaign_post(
    campaign_id: int,
    data: CampaignPostCreate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Add a pre-written post to a repost campaign."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if (campaign.campaign_type or "ai_generated") != "repost":
        raise HTTPException(
            status_code=400,
            detail="Pre-written posts can only be added to repost campaigns",
        )

    post = CampaignPost(
        campaign_id=campaign_id,
        platform=data.platform,
        content=data.content,
        image_url=data.image_url,
        post_order=data.post_order,
        scheduled_offset_hours=data.scheduled_offset_hours,
    )
    db.add(post)
    await db.flush()
    return post


@router.get(
    "/company/campaigns/{campaign_id}/posts",
    response_model=list[CampaignPostResponse],
)
async def list_campaign_posts(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """List pre-written posts for a repost campaign."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    posts_result = await db.execute(
        select(CampaignPost)
        .where(CampaignPost.campaign_id == campaign_id)
        .order_by(CampaignPost.post_order)
    )
    return posts_result.scalars().all()


@router.delete("/company/campaigns/{campaign_id}/posts/{post_id}")
async def delete_campaign_post(
    campaign_id: int,
    post_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Delete a pre-written post from a repost campaign."""
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    post_result = await db.execute(
        select(CampaignPost).where(
            and_(
                CampaignPost.id == post_id,
                CampaignPost.campaign_id == campaign_id,
            )
        )
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Campaign post not found")

    await db.delete(post)
    await db.flush()
    return {"status": "deleted", "post_id": post_id}


# ── Reporting & Export ─────────────────────────────────────────────


@router.get("/company/campaigns/{campaign_id}/export")
async def export_campaign_csv(
    campaign_id: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
    format: str = Query("csv", description="Export format (only csv supported)"),
    start_date: str | None = Query(None, description="Filter start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="Filter end date (YYYY-MM-DD)"),
):
    """Export campaign performance report as CSV download.

    Includes all posts with metrics, user info, and earnings for the campaign.
    Optional date range filtering on post.posted_at.
    """
    if format != "csv":
        raise HTTPException(status_code=400, detail="Only csv format is supported")

    # Verify campaign ownership
    result = await db.execute(
        select(Campaign).where(
            and_(Campaign.id == campaign_id, Campaign.company_id == company.id)
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Parse date filters
    filter_start = None
    filter_end = None
    if start_date:
        try:
            filter_start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    if end_date:
        try:
            filter_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    # Build query: assignments -> posts -> metrics, joined with users
    assignments_q = select(CampaignAssignment).where(
        CampaignAssignment.campaign_id == campaign_id
    )
    assignments_result = await db.execute(assignments_q)
    assignments = assignments_result.scalars().all()

    # Map user_id -> assignment for lookup
    assignment_map = {a.id: a for a in assignments}
    user_ids = {a.user_id for a in assignments}

    # Fetch users
    users_result = await db.execute(select(User).where(User.id.in_(user_ids))) if user_ids else None
    user_map = {}
    if users_result:
        for u in users_result.scalars().all():
            user_map[u.id] = u

    # Fetch all posts for these assignments
    assignment_ids = [a.id for a in assignments]
    posts_query = select(Post).where(Post.assignment_id.in_(assignment_ids)) if assignment_ids else None
    posts = []
    if posts_query is not None:
        posts_result = await db.execute(posts_query)
        posts = posts_result.scalars().all()

    # Apply date filters
    if filter_start:
        posts = [p for p in posts if p.posted_at and p.posted_at.replace(tzinfo=None) >= filter_start]
    if filter_end:
        posts = [p for p in posts if p.posted_at and p.posted_at.replace(tzinfo=None) <= filter_end]

    # Fetch payouts for this campaign
    payouts_result = await db.execute(
        select(Payout).where(Payout.campaign_id == campaign_id)
    )
    payouts = payouts_result.scalars().all()
    # Build user_id -> total payout amount
    user_payout_map: dict[int, float] = {}
    for p in payouts:
        user_payout_map[p.user_id] = user_payout_map.get(p.user_id, 0.0) + float(p.amount)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "User", "Platform", "Post URL", "Impressions", "Likes",
        "Reposts", "Comments", "Clicks", "Earned", "Posted At",
    ])

    for post in posts:
        assignment = assignment_map.get(post.assignment_id)
        if not assignment:
            continue

        user = user_map.get(assignment.user_id)
        user_display = user.email if user else f"user_{assignment.user_id}"

        # Get the latest metric for this post (highest ID = most recent scrape)
        latest_metric = max(post.metrics, key=lambda m: m.id) if post.metrics else None

        impressions = latest_metric.impressions if latest_metric else 0
        likes = latest_metric.likes if latest_metric else 0
        reposts = latest_metric.reposts if latest_metric else 0
        comments = latest_metric.comments if latest_metric else 0
        clicks = latest_metric.clicks if latest_metric else 0

        # Per-post earnings estimate from payout rules
        payout_rules = campaign.payout_rules or {}
        earned = (
            (impressions / 1000 * payout_rules.get("rate_per_1k_impressions", 0))
            + (likes * payout_rules.get("rate_per_like", 0))
            + (reposts * payout_rules.get("rate_per_repost", 0))
            + (clicks * payout_rules.get("rate_per_click", 0))
        )
        earned_str = f"${earned:.2f}"

        posted_at_str = post.posted_at.strftime("%Y-%m-%d %H:%M:%S") if post.posted_at else ""

        writer.writerow([
            user_display,
            post.platform,
            post.post_url,
            impressions,
            likes,
            reposts,
            comments,
            clicks,
            earned_str,
            posted_at_str,
        ])

    output.seek(0)
    filename = f"campaign-{campaign_id}-report.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── User endpoints ─────────────────────────────────────────────────


@router.get("/campaigns/mine", response_model=list[CampaignBrief])
async def get_my_campaigns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll for campaigns matched to this user. Creates assignments for new matches."""
    return await get_matched_campaigns(user, db)


@router.patch("/campaigns/assignments/{assignment_id}")
async def update_assignment_status(
    assignment_id: int,
    status: str = Query(..., description="New status"),
    content_mode: str | None = Query(None, description="Content mode if changed"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CampaignAssignment).where(
            and_(
                CampaignAssignment.id == assignment_id,
                CampaignAssignment.user_id == user.id,
            )
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    valid_statuses = ["content_generated", "posted", "skipped"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    assignment.status = status

    if content_mode:
        assignment.content_mode = content_mode
        # v2: payout_multiplier no longer changes with content_mode — always 1.0

    await db.flush()
    return {"status": "updated", "assignment_id": assignment_id}
