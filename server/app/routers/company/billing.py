"""Company billing and payment routes."""

import os
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.company_transaction import CompanyTransaction
from app.routers.company import _render, _login_redirect, get_company_from_cookie

router = APIRouter()
settings = get_settings()


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    success: str | None = None,
    error: str | None = None,
    cancelled: str | None = None,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    # Campaign budget allocations
    result = await db.execute(
        select(Campaign)
        .where(Campaign.company_id == company.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    allocations = []
    total_allocated = 0.0
    total_spent = 0.0
    for c in campaigns:
        allocated = float(c.budget_total)
        spent = allocated - float(c.budget_remaining)
        total_allocated += allocated
        total_spent += spent
        allocations.append({
            "campaign_id": c.id,
            "campaign_title": c.title,
            "amount": allocated,
            "spent": spent,
            "remaining": float(c.budget_remaining),
            "date": c.created_at,
            "status": c.status,
        })

    stripe_configured = bool(settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY"))

    # Fetch transaction history
    tx_result = await db.execute(
        select(CompanyTransaction)
        .where(CompanyTransaction.company_id == company.id)
        .order_by(CompanyTransaction.created_at.desc())
        .limit(50)
    )
    transactions = tx_result.scalars().all()

    flash_success = None
    flash_error = None
    if success:
        flash_success = success
    elif cancelled:
        flash_error = "Payment was cancelled. No funds were added."
    elif error:
        flash_error = error

    return _render(
        "company/billing.html",
        company=company,
        allocations=allocations,
        total_allocated=total_allocated,
        total_spent=total_spent,
        transactions=transactions,
        active_page="billing",
        stripe_configured=stripe_configured,
        flash_success=flash_success,
        flash_error=flash_error,
    )


@router.post("/billing/topup")
async def billing_topup(
    request: Request,
    amount: float = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    if amount <= 0:
        return RedirectResponse(url="/company/billing?error=Amount+must+be+greater+than+zero", status_code=302)

    amount_cents = int(round(amount * 100))

    from app.services.payments import create_company_checkout
    checkout_url = await create_company_checkout(company.id, amount_cents, db)

    if not checkout_url:
        # Test mode: credit balance and record transaction
        test_session_id = f"test_{uuid.uuid4().hex}"
        company.balance = float(company.balance) + amount
        company.balance_cents = (company.balance_cents or 0) + amount_cents
        tx = CompanyTransaction(
            company_id=company.id,
            stripe_session_id=test_session_id,
            amount_cents=amount_cents,
            type="topup",
        )
        db.add(tx)
        await db.flush()
        return RedirectResponse(
            url=f"/company/billing?success=Added+%24{amount:.2f}+to+your+balance+(test+mode)",
            status_code=302,
        )

    return RedirectResponse(url=checkout_url, status_code=302)


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success(
    request: Request,
    session_id: str,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    # Idempotency check: has this session already been processed?
    existing = await db.execute(
        select(CompanyTransaction).where(CompanyTransaction.stripe_session_id == session_id)
    )
    if existing.scalar_one_or_none():
        return RedirectResponse(
            url="/company/billing?success=Payment+already+processed.",
            status_code=302,
        )

    from app.services.payments import verify_checkout_session
    result = await verify_checkout_session(session_id)

    if not result:
        return RedirectResponse(
            url="/company/billing?error=Payment+verification+failed.+Contact+support.",
            status_code=302,
        )

    if result["company_id"] != company.id:
        return RedirectResponse(url="/company/billing?error=Session+mismatch.", status_code=302)

    amount_cents = result["amount_cents"]
    amount = amount_cents / 100.0
    company.balance = float(company.balance) + amount
    company.balance_cents = (company.balance_cents or 0) + amount_cents
    tx = CompanyTransaction(
        company_id=company.id,
        stripe_session_id=session_id,
        amount_cents=amount_cents,
        type="topup",
    )
    db.add(tx)
    await db.flush()

    return RedirectResponse(
        url=f"/company/billing?success=Successfully+added+%24{amount:.2f}+to+your+balance.",
        status_code=302,
    )
