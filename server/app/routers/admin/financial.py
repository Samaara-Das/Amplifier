"""Admin financial dashboard routes."""

from fastapi import APIRouter, Cookie, Depends, Request
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
    )
