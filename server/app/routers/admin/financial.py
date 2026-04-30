"""Admin financial dashboard routes."""

import json
from datetime import datetime, timezone, date, timedelta

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.campaign import Campaign
from app.models.payout import Payout
from app.models.user import User
from app.routers.admin import (
    _render, _check_admin, _login_redirect, paginate,
    log_admin_action, build_query_string,
)

router = APIRouter()


async def _fetch_payout_stats(db: AsyncSession):
    total_pending = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "pending")
        ) or 0
    )
    total_paid = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "paid")
        ) or 0
    )
    total_failed = float(
        await db.scalar(
            select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status == "failed")
        ) or 0
    )
    total_budget_spent = float(
        await db.scalar(
            select(func.coalesce(func.sum(Campaign.budget_total - Campaign.budget_remaining), 0))
            .select_from(Campaign)
        ) or 0
    )
    all_payouts = total_pending + total_paid + total_failed
    platform_revenue = total_budget_spent - all_payouts
    return {
        "total_pending": total_pending,
        "total_paid": total_paid,
        "total_failed": total_failed,
        "total_budget_spent": total_budget_spent,
        "platform_revenue": platform_revenue,
    }


async def _fetch_revenue_30d(db: AsyncSession) -> str:
    """Return JSON string of last-30-days daily payout totals for Chart.js."""
    cutoff = date.today() - timedelta(days=29)
    result = await db.execute(
        select(
            func.date(Payout.created_at).label("day"),
            func.coalesce(func.sum(Payout.amount), 0).label("total"),
        )
        .where(Payout.status == "paid")
        .where(func.date(Payout.created_at) >= cutoff)
        .group_by(func.date(Payout.created_at))
        .order_by(func.date(Payout.created_at))
    )
    rows = {str(r[0]): float(r[1]) for r in result.all()}

    # Fill all 30 days (0 for missing days)
    labels, values = [], []
    for i in range(30):
        d = cutoff + timedelta(days=i)
        ds = str(d)
        # Short label: MM/DD
        labels.append(f"{d.month}/{d.day}")
        values.append(rows.get(ds, 0.0))

    return json.dumps({"labels": labels, "values": values})


async def _fetch_payouts(db: AsyncSession, page, status_filter, search):
    query = select(Payout, User).join(User, Payout.user_id == User.id)
    count_query = select(func.count()).select_from(Payout)

    if status_filter:
        query = query.where(Payout.status == status_filter)
        count_query = count_query.where(Payout.status == status_filter)
    if search:
        # User already joined in main query above
        count_query = count_query.join(User, Payout.user_id == User.id).where(User.email.ilike(f"%{search}%"))
        query = query.where(User.email.ilike(f"%{search}%"))

    query = query.order_by(Payout.created_at.desc())
    pagination = await paginate(db, query, count_query, page, per_page=25)

    campaign_cache = {}
    payouts_list = []
    for payout, user in pagination["items"]:
        campaign_title = "Aggregate"
        if payout.campaign_id and payout.campaign_id > 0:
            if payout.campaign_id not in campaign_cache:
                c = await db.execute(select(Campaign).where(Campaign.id == payout.campaign_id))
                camp = c.scalar_one_or_none()
                campaign_cache[payout.campaign_id] = camp.title if camp else "N/A"
            campaign_title = campaign_cache[payout.campaign_id]
        payouts_list.append({
            "id": payout.id,
            "user_email": user.email,
            "user_id": user.id,
            "campaign_title": campaign_title,
            "amount": float(payout.amount),
            "status": payout.status,
            "breakdown": payout.breakdown or {},
            "created_at": payout.created_at,
        })
    return payouts_list, pagination


@router.get("/financial", response_class=HTMLResponse)
async def financial_page(
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    status: str = "",
    search: str = "",
):
    if not _check_admin(admin_token):
        return _login_redirect()

    stats = await _fetch_payout_stats(db)
    payouts_list, pagination = await _fetch_payouts(db, page, status, search)
    revenue_data_json = await _fetch_revenue_30d(db)
    qs = build_query_string(status=status, search=search)

    return _render(
        "admin/financial.html",
        active_page="financial",
        **stats,
        payouts=payouts_list,
        pagination=pagination,
        search=search,
        current_status=status,
        qs=qs,
        result_msg=None,
        revenue_data_json=revenue_data_json,
    )


@router.post("/financial/run-billing", response_class=HTMLResponse)
async def run_billing(request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()

    from app.services.billing import run_billing_cycle
    result = await run_billing_cycle(db)
    msg = f"Billing complete: {result['posts_processed']} posts, ${result['total_earned']:.2f} earned, ${result['total_budget_deducted']:.2f} deducted"
    await log_admin_action(db, request, "billing_cycle_run", "system", 0, result)

    stats = await _fetch_payout_stats(db)
    payouts_list, pagination = await _fetch_payouts(db, 1, "", "")
    revenue_data_json = await _fetch_revenue_30d(db)

    return _render(
        "admin/financial.html",
        active_page="financial",
        **stats,
        payouts=payouts_list,
        pagination=pagination,
        search="",
        current_status="",
        qs="",
        result_msg=msg,
        revenue_data_json=revenue_data_json,
    )


@router.post("/financial/run-payout", response_class=HTMLResponse)
async def run_payout(request: Request, admin_token: str = Cookie(None), db: AsyncSession = Depends(get_db)):
    if not _check_admin(admin_token):
        return _login_redirect()

    from app.services.payments import run_payout_cycle
    result = await run_payout_cycle(db)
    msg = f"Payout complete: {result['users_paid']} users, ${result['total_paid']:.2f} paid, {result['failures']} failures"
    await log_admin_action(db, request, "payout_cycle_run", "system", 0, result)

    stats = await _fetch_payout_stats(db)
    payouts_list, pagination = await _fetch_payouts(db, 1, "", "")
    revenue_data_json = await _fetch_revenue_30d(db)

    return _render(
        "admin/financial.html",
        active_page="financial",
        **stats,
        payouts=payouts_list,
        pagination=pagination,
        search="",
        current_status="",
        qs="",
        result_msg=msg,
        revenue_data_json=revenue_data_json,
    )


@router.post("/financial/run-earning-promotion", response_class=HTMLResponse)
async def run_earning_promotion(request: Request, admin_token: str = Cookie(None),
                                db: AsyncSession = Depends(get_db)):
    """Promote pending earnings to available after hold period expires (v2/v3 upgrade)."""
    if not _check_admin(admin_token):
        return _login_redirect()

    from app.services.billing import promote_pending_earnings
    promoted = await promote_pending_earnings(db)
    msg = f"Earning promotion: {promoted} payouts promoted from pending to available"
    await log_admin_action(db, request, "earning_promotion_run", "system", 0,
                           {"promoted": promoted})

    stats = await _fetch_payout_stats(db)
    payouts_list, pagination = await _fetch_payouts(db, 1, "", "")
    revenue_data_json = await _fetch_revenue_30d(db)

    return _render(
        "admin/financial.html",
        active_page="financial",
        **stats,
        payouts=payouts_list,
        pagination=pagination,
        search="",
        current_status="",
        qs="",
        result_msg=msg,
        revenue_data_json=revenue_data_json,
    )


@router.post("/financial/run-payout-processing", response_class=HTMLResponse)
async def run_payout_processing(request: Request, admin_token: str = Cookie(None),
                                db: AsyncSession = Depends(get_db)):
    """Process payouts in 'processing' status via Stripe Connect (v2/v3 upgrade)."""
    if not _check_admin(admin_token):
        return _login_redirect()

    from app.services.payments import process_pending_payouts
    result = await process_pending_payouts(db)
    msg = (f"Payout processing: {result['processed']} processed, "
           f"{result['paid']} paid, {result['failed']} failed")
    await log_admin_action(db, request, "payout_processing_run", "system", 0, result)

    stats = await _fetch_payout_stats(db)
    payouts_list, pagination = await _fetch_payouts(db, 1, "", "")
    revenue_data_json = await _fetch_revenue_30d(db)

    return _render(
        "admin/financial.html",
        active_page="financial",
        **stats,
        payouts=payouts_list,
        pagination=pagination,
        search="",
        current_status="",
        qs="",
        result_msg=msg,
        revenue_data_json=revenue_data_json,
    )


@router.post("/financial/payouts/{payout_id}/void")
async def void_payout(
    payout_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
    reason: str = Form(""),
):
    """Void a payout — return funds to campaign, deduct from user balance."""
    if not _check_admin(admin_token):
        return _login_redirect()

    payout = await db.get(Payout, payout_id)
    if not payout or payout.status not in ("pending", "available"):
        return RedirectResponse(url="/admin/financial", status_code=303)

    old_status = payout.status
    payout.status = "voided"

    # Return funds to campaign budget
    if payout.campaign_id:
        campaign = await db.get(Campaign, payout.campaign_id)
        if campaign:
            budget_cost_cents = (payout.breakdown or {}).get("budget_cost_cents", 0)
            campaign.budget_remaining = float(campaign.budget_remaining) + (budget_cost_cents / 100.0)

    # Deduct from user balance (billing adds to balance at payout creation, regardless of status)
    user = await db.get(User, payout.user_id)
    if user:
        user.earnings_balance = max(0, float(user.earnings_balance or 0) - float(payout.amount))
        if hasattr(user, "earnings_balance_cents"):
            user.earnings_balance_cents = max(0, (user.earnings_balance_cents or 0) - (payout.amount_cents or 0))
        user.total_earned = max(0, float(user.total_earned or 0) - float(payout.amount))
        if hasattr(user, "total_earned_cents"):
            user.total_earned_cents = max(0, (user.total_earned_cents or 0) - (payout.amount_cents or 0))

    await db.flush()
    await log_admin_action(db, request, "payout_voided", "payout", payout_id, {
        "reason": reason,
        "old_status": old_status,
        "amount": float(payout.amount),
        "user_id": payout.user_id,
        "campaign_id": payout.campaign_id,
    })

    return RedirectResponse(url="/admin/financial", status_code=303)


@router.post("/financial/payouts/{payout_id}/approve")
async def approve_payout(
    payout_id: int,
    request: Request,
    admin_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Force-approve a pending payout — skip 7-day hold, make available immediately."""
    if not _check_admin(admin_token):
        return _login_redirect()

    payout = await db.get(Payout, payout_id)
    if not payout or payout.status != "pending":
        return RedirectResponse(url="/admin/financial", status_code=303)

    payout.status = "available"
    payout.available_at = datetime.now(timezone.utc)

    await db.flush()
    await log_admin_action(db, request, "payout_approved", "payout", payout_id, {
        "amount": float(payout.amount),
        "user_id": payout.user_id,
        "campaign_id": payout.campaign_id,
    })

    return RedirectResponse(url="/admin/financial", status_code=303)
