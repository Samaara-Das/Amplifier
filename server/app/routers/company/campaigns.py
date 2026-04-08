"""Company campaign management routes."""

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.campaign_post import CampaignPost
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.services.metric_helpers import latest_metric_filter, latest_metric_join_condition
from app.models.payout import Payout
from app.models.user import User
from app.routers.company import (
    _render, _login_redirect, get_company_from_cookie,
    paginate_scalars, build_query_string,
)

router = APIRouter()
settings = get_settings()

MAX_IMAGE_SIZE = 4 * 1024 * 1024
MAX_FILE_SIZE = 4 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_FILE_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


# ── Campaigns List ────────────────────────────────────────────────────


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(
    request: Request,
    error: str | None = None,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    search: str = "",
    status: str = "",
    sort: str = "created_at",
    order: str = "desc",
):
    if not company:
        return _login_redirect()

    query = select(Campaign).where(Campaign.company_id == company.id)
    count_query = select(func.count()).select_from(Campaign).where(Campaign.company_id == company.id)

    if search:
        query = query.where(Campaign.title.ilike(f"%{search}%"))
        count_query = count_query.where(Campaign.title.ilike(f"%{search}%"))
    if status:
        query = query.where(Campaign.status == status)
        count_query = count_query.where(Campaign.status == status)

    sort_col = {
        "budget_total": Campaign.budget_total,
        "title": Campaign.title,
    }.get(sort, Campaign.created_at)

    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pagination = await paginate_scalars(db, query, count_query, page, per_page=15)

    campaign_data = []
    for c in pagination["items"]:
        stats = await db.execute(
            select(
                func.count(Post.id).label("post_count"),
                func.count(func.distinct(CampaignAssignment.user_id)).label("user_count"),
            )
            .select_from(Post)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(CampaignAssignment.campaign_id == c.id)
        )
        row = stats.one()

        metrics = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
            .where(and_(CampaignAssignment.campaign_id == c.id, latest_metric_filter()))
        )
        m = metrics.one()

        spent = float(c.budget_total) - float(c.budget_remaining)
        budget_pct = round((spent / float(c.budget_total) * 100), 1) if float(c.budget_total) > 0 else 0

        campaign_data.append({
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "screening_status": c.screening_status,
            "budget_total": float(c.budget_total),
            "budget_remaining": float(c.budget_remaining),
            "budget_pct": budget_pct,
            "user_count": row.user_count,
            "post_count": row.post_count,
            "impressions": int(m.impressions),
            "engagement": int(m.engagement),
            "created_at": c.created_at,
        })

    qs = build_query_string(search=search, status=status, sort=sort, order=order)

    return _render(
        "company/campaigns.html",
        company=company,
        campaigns=campaign_data,
        pagination=pagination,
        search=search,
        current_status=status,
        sort=sort,
        order=order,
        qs=qs,
        active_page="campaigns",
        error=error,
    )


# ── Create Campaign ────────────────────────────────────────────────────


@router.post("/campaigns/upload-asset")
async def upload_campaign_asset(
    file: UploadFile = File(...),
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    content_type = file.content_type or ""
    filename = file.filename or "unknown"
    is_image = content_type in ALLOWED_IMAGE_TYPES
    is_file = content_type in ALLOWED_FILE_TYPES

    if not is_image and not is_file:
        return JSONResponse(
            {"error": f"Unsupported file type: {content_type}. Allowed: images (JPEG/PNG/WebP/GIF) and documents (PDF/DOCX/TXT)."},
            status_code=400,
        )

    file_bytes = await file.read()
    max_size = MAX_IMAGE_SIZE if is_image else MAX_FILE_SIZE
    if len(file_bytes) > max_size:
        return JSONResponse(
            {"error": f"File too large. Maximum size: {max_size // (1024*1024)}MB."},
            status_code=400,
        )

    from app.services.storage import upload_file, extract_text_from_file

    folder = f"company-{company.id}/images" if is_image else f"company-{company.id}/files"
    public_url = upload_file(file_bytes, filename, content_type, folder=folder)

    if not public_url:
        return JSONResponse(
            {"error": "Upload failed. Check that Supabase Storage is configured (SUPABASE_URL, SUPABASE_SERVICE_KEY)."},
            status_code=500,
        )

    result = {
        "url": public_url,
        "filename": filename,
        "content_type": content_type,
        "type": "image" if is_image else "file",
    }

    if is_file:
        extracted = extract_text_from_file(file_bytes, filename, content_type)
        result["extracted_text"] = extracted

    return JSONResponse(result)


@router.get("/campaigns/new", response_class=HTMLResponse)
async def campaign_create_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    if float(company.balance) < 50.0:
        return RedirectResponse(
            url="/company/campaigns?error=You+need+at+least+%2450.00+in+your+balance+to+create+a+campaign.+Add+funds+on+the+Billing+page+first.",
            status_code=302,
        )

    return _render("company/campaign_wizard.html", company=company, active_page="create")


@router.post("/campaigns/ai-generate")
async def ai_generate_campaign(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    from app.services.campaign_wizard import run_campaign_wizard
    try:
        targeting = body.get("targeting", {})
        result = await run_campaign_wizard(
            db=db,
            product_description=body.get("product_description", ""),
            product_name=body.get("product_name", ""),
            product_features=body.get("product_features", ""),
            campaign_goal=body.get("campaign_goal", "brand_awareness"),
            company_urls=body.get("company_urls", []),
            target_niches=targeting.get("niche_tags") or targeting.get("target_niches", []),
            target_regions=targeting.get("target_regions", []),
            required_platforms=targeting.get("required_platforms", []),
            min_followers=targeting.get("min_followers", {}),
            must_include=body.get("must_include", ""),
            must_avoid=body.get("must_avoid", ""),
            image_urls=body.get("image_urls", []),
            file_contents=body.get("file_contents", []),
        )
        return JSONResponse(result)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("AI wizard failed: %s", e, exc_info=True)
        return JSONResponse({
            "title": f"[EDIT] {body.get('product_name', body.get('product_description', 'Campaign'))[:50]}",
            "brief": f"[AI generation failed: {e}]\n\nPlease edit this brief manually.\n\n{body.get('product_description', '')}",
            "content_guidance": "Create authentic, engaging content about this product.",
            "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05},
            "suggested_budget": 100,
            "reach_estimate": {"matching_users": 0, "estimated_impressions_low": 0, "estimated_impressions_high": 0},
            "ai_error": str(e),
        })


@router.post("/campaigns/new")
async def campaign_create_submit(
    request: Request,
    title: str = Form(...),
    brief: str = Form(...),
    budget: float = Form(...),
    rate_per_1k_impressions: float = Form(0.50),
    rate_per_like: float = Form(0.01),
    rate_per_repost: float = Form(0.05),
    rate_per_click: float = Form(0.10),
    min_followers_json: str = Form("{}"),
    niche_tags: list[str] = Form([]),
    target_regions: list[str] = Form([]),
    required_platforms: list[str] = Form([]),
    content_guidance: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    campaign_status: str = Form("draft"),
    budget_exhaustion_action: str = Form("auto_pause"),
    max_users: int | None = Form(None),
    min_engagement: float = Form(0.0),
    image_urls_json: str = Form("[]"),
    file_urls_json: str = Form("[]"),
    file_contents_json: str = Form("[]"),
    scraped_knowledge_json: str = Form(""),
    campaign_type: str = Form("ai_generated"),
    repost_x: str = Form(""),
    repost_x_image: str = Form(""),
    repost_linkedin: str = Form(""),
    repost_linkedin_image: str = Form(""),
    repost_facebook: str = Form(""),
    repost_facebook_image: str = Form(""),
    repost_reddit_title: str = Form(""),
    repost_reddit_body: str = Form(""),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    try:
        min_followers = json.loads(min_followers_json) if min_followers_json.strip() else {}
    except json.JSONDecodeError:
        min_followers = {}

    tags = [t.strip() for t in niche_tags if t.strip()]

    if campaign_status not in ("draft", "active"):
        campaign_status = "draft"
    if budget_exhaustion_action not in ("auto_pause", "auto_complete"):
        budget_exhaustion_action = "auto_pause"

    if budget < 50.0:
        return _render(
            "company/campaign_wizard.html",
            status_code=400,
            company=company,
            active_page="create",
            error="Minimum campaign budget is $50.00",
        )

    if campaign_status == "active" and float(company.balance) < budget:
        return _render(
            "company/campaign_wizard.html",
            status_code=400,
            company=company,
            active_page="create",
            error=f"Insufficient balance to activate. Current balance: ${float(company.balance):.2f}. Save as draft instead, then add funds.",
        )

    try:
        image_urls = json.loads(image_urls_json) if image_urls_json.strip() else []
    except json.JSONDecodeError:
        image_urls = []
    try:
        file_urls = json.loads(file_urls_json) if file_urls_json.strip() else []
    except json.JSONDecodeError:
        file_urls = []
    try:
        file_contents = json.loads(file_contents_json) if file_contents_json.strip() else []
    except json.JSONDecodeError:
        file_contents = []

    assets = {
        "image_urls": image_urls,
        "file_urls": file_urls,
        "file_contents": file_contents,
        "hashtags": [],
        "brand_guidelines": "",
    }
    if scraped_knowledge_json and scraped_knowledge_json.strip():
        try:
            assets["scraped_knowledge"] = json.loads(scraped_knowledge_json)
        except json.JSONDecodeError:
            pass

    # Validate campaign_type
    if campaign_type not in ("ai_generated", "repost"):
        campaign_type = "ai_generated"

    campaign = Campaign(
        company_id=company.id,
        title=title,
        brief=brief,
        budget_total=budget,
        budget_remaining=budget,
        campaign_type=campaign_type,
        payout_rules={
            "rate_per_1k_impressions": rate_per_1k_impressions,
            "rate_per_like": rate_per_like,
            "rate_per_repost": rate_per_repost,
            "rate_per_click": rate_per_click,
        },
        targeting={
            "min_followers": min_followers,
            "min_engagement": min_engagement,
            "niche_tags": tags,
            "target_regions": target_regions,
            "required_platforms": required_platforms,
        },
        assets=assets,
        content_guidance=content_guidance or None,
        penalty_rules={},
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date),
        status=campaign_status,
        budget_exhaustion_action=budget_exhaustion_action,
        max_users=max_users,
    )
    db.add(campaign)

    if campaign_status == "active":
        company.balance = float(company.balance) - budget
    await db.flush()

    # Create CampaignPost records for repost campaigns
    if campaign_type == "repost":
        post_order = 1
        repost_entries = [
            ("x", repost_x.strip(), repost_x_image.strip()),
            ("linkedin", repost_linkedin.strip(), repost_linkedin_image.strip()),
            ("facebook", repost_facebook.strip(), repost_facebook_image.strip()),
        ]
        for platform, content, image_url in repost_entries:
            if content:
                db.add(CampaignPost(
                    campaign_id=campaign.id,
                    platform=platform,
                    content=content,
                    image_url=image_url or None,
                    post_order=post_order,
                ))
                post_order += 1

        # Reddit has title + body; combine into content with a separator
        reddit_title = repost_reddit_title.strip()
        reddit_body = repost_reddit_body.strip()
        if reddit_title:
            reddit_content = reddit_title
            if reddit_body:
                reddit_content += "\n---\n" + reddit_body
            db.add(CampaignPost(
                campaign_id=campaign.id,
                platform="reddit",
                content=reddit_content,
                post_order=post_order,
            ))

        await db.flush()

    return RedirectResponse(url=f"/company/campaigns/{campaign.id}?success=Campaign+created+successfully", status_code=302)


# ── Campaign Detail ────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail_page(
    request: Request,
    campaign_id: int,
    success: str | None = None,
    error: str | None = None,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(and_(Campaign.id == campaign_id, Campaign.company_id == company.id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/campaigns", status_code=302)

    # Aggregate totals
    totals = await db.execute(
        select(
            func.count(Post.id).label("post_count"),
            func.count(func.distinct(CampaignAssignment.user_id)).label("user_count"),
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(Metric.likes + Metric.reposts + Metric.comments), 0).label("engagement"),
        )
        .select_from(Post)
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .outerjoin(Metric, latest_metric_join_condition())
        .where(CampaignAssignment.campaign_id == campaign_id)
    )
    t = totals.one()

    # Per-platform breakdown
    platform_stats = await db.execute(
        select(
            Post.platform,
            func.count(Post.id).label("post_count"),
            func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
            func.coalesce(func.sum(Metric.likes), 0).label("likes"),
            func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
            func.coalesce(func.sum(Metric.comments), 0).label("comments"),
            func.coalesce(func.sum(Metric.clicks), 0).label("clicks"),
        )
        .select_from(Post)
        .outerjoin(Metric, latest_metric_join_condition())
        .join(CampaignAssignment, Post.assignment_id == CampaignAssignment.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
        .group_by(Post.platform)
    )

    payout_rules = campaign.payout_rules or {}
    platforms = []
    for row in platform_stats:
        imp = int(row.impressions)
        lk = int(row.likes)
        rp = int(row.reposts)
        cm = int(row.comments)
        ck = int(row.clicks)
        eng = lk + rp + cm
        plat_spend = (
            (imp / 1000 * payout_rules.get("rate_per_1k_impressions", 0))
            + (lk * payout_rules.get("rate_per_like", 0))
            + (rp * payout_rules.get("rate_per_repost", 0))
            + (ck * payout_rules.get("rate_per_click", 0))
        )
        platforms.append({
            "platform": row.platform,
            "posts": row.post_count,
            "impressions": imp,
            "likes": lk,
            "reposts": rp,
            "comments": cm,
            "clicks": ck,
            "engagement": eng,
            "spend": round(plat_spend, 2),
            "cost_per_1k": round((plat_spend / imp * 1000) if imp > 0 else 0, 2),
            "cost_per_eng": round((plat_spend / eng) if eng > 0 else 0, 2),
        })

    spent = float(campaign.budget_total) - float(campaign.budget_remaining)

    # Invitation stats
    inv_total = campaign.invitation_count or 0
    inv_accepted = campaign.accepted_count or 0
    inv_rejected = campaign.rejected_count or 0
    inv_expired = campaign.expired_count or 0
    inv_pending = max(0, inv_total - inv_accepted - inv_rejected - inv_expired)

    invitation_stats = {
        "total": inv_total,
        "accepted": inv_accepted,
        "rejected": inv_rejected,
        "expired": inv_expired,
        "pending": inv_pending,
    }

    # Decline reasons from rejected invitations
    decline_q = await db.execute(
        select(CampaignAssignment.decline_reason)
        .where(
            and_(
                CampaignAssignment.campaign_id == campaign_id,
                CampaignAssignment.status == "rejected",
                CampaignAssignment.decline_reason.isnot(None),
                CampaignAssignment.decline_reason != "",
            )
        )
    )
    decline_reasons_raw = [r[0] for r in decline_q]
    # Aggregate: count occurrences of each reason
    decline_counts = {}
    for reason in decline_reasons_raw:
        decline_counts[reason] = decline_counts.get(reason, 0) + 1
    # Sort by count descending
    decline_reasons = sorted(decline_counts.items(), key=lambda x: -x[1])

    # User payouts
    payouts_q = await db.execute(
        select(Payout.user_id, func.coalesce(func.sum(Payout.amount), 0).label("total_paid"))
        .where(Payout.campaign_id == campaign_id)
        .group_by(Payout.user_id)
    )
    user_payout_map = {pr.user_id: float(pr.total_paid) for pr in payouts_q}

    # Influencer list
    influencer_query = await db.execute(
        select(
            User.id, User.email, User.platforms,
            CampaignAssignment.status.label("assignment_status"),
            CampaignAssignment.id.label("assignment_id"),
            CampaignAssignment.user_id.label("user_id"),
        )
        .select_from(CampaignAssignment)
        .join(User, CampaignAssignment.user_id == User.id)
        .where(CampaignAssignment.campaign_id == campaign_id)
    )
    influencers = []
    creator_index = 0
    for row in influencer_query:
        creator_index += 1
        user_posts_q = await db.execute(
            select(Post.platform, Post.post_url).where(Post.assignment_id == row.assignment_id)
        )
        user_posts = [{"platform": p.platform, "url": p.post_url} for p in user_posts_q if p.post_url]

        user_metrics_q = await db.execute(
            select(
                func.coalesce(func.sum(Metric.impressions), 0).label("impressions"),
                func.coalesce(func.sum(Metric.likes), 0).label("likes"),
                func.coalesce(func.sum(Metric.reposts), 0).label("reposts"),
                func.coalesce(func.sum(Metric.comments), 0).label("comments"),
                func.coalesce(func.sum(Metric.clicks), 0).label("clicks"),
            )
            .select_from(Metric)
            .join(Post, Metric.post_id == Post.id)
            .where(and_(Post.assignment_id == row.assignment_id, latest_metric_filter()))
        )
        um = user_metrics_q.one()

        handles = {}
        user_platforms = row.platforms or {}
        connected_platforms = []
        for plat, info in user_platforms.items():
            if isinstance(info, dict) and info.get("connected"):
                connected_platforms.append(plat)
                if info.get("username"):
                    handles[plat] = info["username"]

        imp = int(um.impressions)
        lk = int(um.likes)
        rp = int(um.reposts)
        ck = int(um.clicks)
        estimated_earned = (
            (imp / 1000 * payout_rules.get("rate_per_1k_impressions", 0))
            + (lk * payout_rules.get("rate_per_like", 0))
            + (rp * payout_rules.get("rate_per_repost", 0))
            + (ck * payout_rules.get("rate_per_click", 0))
        )

        influencers.append({
            "index": creator_index,
            "email": row.email,
            "handles": handles,
            "platforms": connected_platforms,
            "status": row.assignment_status,
            "posts": user_posts,
            "impressions": imp,
            "likes": lk,
            "engagement": lk + int(um.reposts) + int(um.comments),
            "estimated_earned": round(estimated_earned, 2),
            "actual_paid": round(user_payout_map.get(row.user_id, 0.0), 2),
        })

    influencers.sort(key=lambda x: x["estimated_earned"], reverse=True)

    total_impressions = int(t.impressions)
    total_engagement = int(t.engagement)

    return _render(
        "company/campaign_detail.html",
        company=company,
        campaign=campaign,
        spent=spent,
        post_count=t.post_count,
        user_count=t.user_count,
        impressions=total_impressions,
        engagement=total_engagement,
        cost_per_1k_imp=round((spent / total_impressions * 1000) if total_impressions > 0 else 0, 2),
        cost_per_eng=round((spent / total_engagement) if total_engagement > 0 else 0, 2),
        platforms=platforms,
        influencers=influencers,
        invitation_stats=invitation_stats,
        decline_reasons=decline_reasons,
        repost_content=[{"id": cp.id, "platform": cp.platform, "content": cp.content, "image_url": cp.image_url}
                        for cp in (campaign.campaign_posts or [])] if campaign.campaign_type == "repost" else [],
        budget_alert_sent=campaign.budget_alert_sent,
        budget_exhaustion_action=campaign.budget_exhaustion_action or "auto_pause",
        campaign_version=campaign.campaign_version or 1,
        active_page="campaigns",
        success=success,
        error=error,
    )


@router.post("/campaigns/{campaign_id}/repost-content")
async def update_repost_content(
    request: Request,
    campaign_id: int,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Update per-platform repost content for a repost campaign."""
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(and_(Campaign.id == campaign_id, Campaign.company_id == company.id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign or campaign.campaign_type != "repost":
        return RedirectResponse(url=f"/company/campaigns/{campaign_id}", status_code=302)

    form = await request.form()

    # Update each existing CampaignPost from form data
    posts_result = await db.execute(
        select(CampaignPost).where(CampaignPost.campaign_id == campaign_id)
    )
    for cp in posts_result.scalars().all():
        if cp.platform == "reddit":
            title = form.get(f"repost_{cp.platform}_title", "").strip()
            body = form.get(f"repost_{cp.platform}_body", "").strip()
            if title or body:
                cp.content = f"{title}\n---\n{body}"
        else:
            new_content = form.get(f"repost_{cp.platform}", "").strip()
            if new_content:
                cp.content = new_content

    await db.flush()
    return RedirectResponse(
        url=f"/company/campaigns/{campaign_id}?success=Repost+content+updated",
        status_code=303,
    )


# ── Campaign Actions ────────────────────────────────────────────────────


@router.post("/campaigns/{campaign_id}/status")
async def campaign_status_change(
    campaign_id: int,
    new_status: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(and_(Campaign.id == campaign_id, Campaign.company_id == company.id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/campaigns", status_code=302)

    valid_transitions = {
        "draft": ["active", "cancelled"],
        "active": ["paused", "cancelled"],
        "paused": ["active", "cancelled"],
    }
    allowed = valid_transitions.get(campaign.status, [])

    if new_status not in allowed:
        return RedirectResponse(url=f"/company/campaigns/{campaign_id}?error=Invalid+status+transition", status_code=302)

    # Check balance when activating from draft
    if campaign.status == "draft" and new_status == "active":
        if float(company.balance) < float(campaign.budget_total):
            return RedirectResponse(
                url=f"/company/campaigns/{campaign_id}?error=Insufficient+balance+to+activate.+Add+funds+first.",
                status_code=302,
            )
        company.balance = float(company.balance) - float(campaign.budget_total)

    # Refund on cancellation
    if new_status == "cancelled" and campaign.status != "draft":
        refund = float(campaign.budget_remaining)
        if refund > 0:
            company.balance = float(company.balance) + refund

    campaign.status = new_status
    await db.flush()

    return RedirectResponse(url=f"/company/campaigns/{campaign_id}?success=Campaign+{new_status}", status_code=302)


@router.post("/campaigns/{campaign_id}/edit")
async def campaign_edit_submit(
    campaign_id: int,
    title: str = Form(...),
    brief: str = Form(...),
    content_guidance: str = Form(""),
    rate_per_1k_impressions: float = Form(0.50),
    rate_per_like: float = Form(0.01),
    rate_per_repost: float = Form(0.05),
    rate_per_click: float = Form(0.10),
    end_date: str = Form(""),
    budget_exhaustion_action: str = Form("auto_pause"),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(and_(Campaign.id == campaign_id, Campaign.company_id == company.id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/campaigns", status_code=302)

    content_changed = False
    if title != campaign.title:
        campaign.title = title
        content_changed = True
    if brief != campaign.brief:
        campaign.brief = brief
        content_changed = True
    if (content_guidance or None) != campaign.content_guidance:
        campaign.content_guidance = content_guidance or None
        content_changed = True

    campaign.payout_rules = {
        "rate_per_1k_impressions": rate_per_1k_impressions,
        "rate_per_like": rate_per_like,
        "rate_per_repost": rate_per_repost,
        "rate_per_click": rate_per_click,
    }

    if end_date.strip():
        try:
            campaign.end_date = datetime.fromisoformat(end_date)
        except ValueError:
            pass

    if budget_exhaustion_action in ("auto_pause", "auto_complete"):
        campaign.budget_exhaustion_action = budget_exhaustion_action

    if content_changed:
        campaign.campaign_version = (campaign.campaign_version or 1) + 1
        campaign.screening_status = "approved"

    await db.flush()

    return RedirectResponse(
        url=f"/company/campaigns/{campaign_id}?success=Campaign+updated+successfully",
        status_code=302,
    )


@router.post("/campaigns/{campaign_id}/topup")
async def campaign_topup_web(
    campaign_id: int,
    amount: float = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    result = await db.execute(
        select(Campaign).where(and_(Campaign.id == campaign_id, Campaign.company_id == company.id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return RedirectResponse(url="/company/campaigns", status_code=302)

    if amount <= 0:
        return RedirectResponse(url=f"/company/campaigns/{campaign_id}?error=Amount+must+be+greater+than+zero", status_code=302)

    if float(company.balance) < amount:
        return RedirectResponse(url=f"/company/campaigns/{campaign_id}?error=Insufficient+balance", status_code=302)

    campaign.budget_remaining = float(campaign.budget_remaining) + amount
    campaign.budget_total = float(campaign.budget_total) + amount
    company.balance = float(company.balance) - amount

    if campaign.status == "paused" and campaign.budget_exhaustion_action == "auto_pause":
        campaign.status = "active"

    if float(campaign.budget_remaining) >= 0.2 * float(campaign.budget_total):
        campaign.budget_alert_sent = False

    await db.flush()

    return RedirectResponse(
        url=f"/company/campaigns/{campaign_id}?success=Budget+topped+up+by+%24{amount:.2f}",
        status_code=302,
    )
