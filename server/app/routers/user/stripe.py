"""Stripe Connect onboarding routes for the creator dashboard."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.payments import create_user_stripe_account, _get_stripe
from app.routers.user import _login_redirect, get_user_from_cookie

logger = logging.getLogger(__name__)

router = APIRouter()


def _audit(db: AsyncSession, user_id: int, action: str, detail: dict) -> None:
    """Insert an AuditLog row (fire-and-forget — caller must flush/commit)."""
    log = AuditLog(
        action=action,
        target_type="user",
        target_id=user_id,
        details=detail,
    )
    db.add(log)


@router.post("/stripe/connect")
async def stripe_connect(
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Initiate Stripe Connect Express onboarding for the current user.

    If the user already has stripe_account_id set, redirect back to settings
    (idempotent — don't create a second account).
    Otherwise create a new Express account and redirect to Stripe-hosted form.
    """
    if not user:
        return _login_redirect()

    # Already connected — nothing to do
    if user.stripe_account_id:
        return RedirectResponse(url="/user/settings#stripe-connect", status_code=302)

    result = await create_user_stripe_account(user.id, user.email)
    if result is None:
        logger.warning("create_user_stripe_account returned None for user %d", user.id)
        return RedirectResponse(url="/user/settings?stripe_error=1", status_code=302)

    _audit(db, user.id, "stripe_connect_initiated", {
        "account_id": result["account_id"],
    })
    await db.flush()

    return RedirectResponse(url=result["onboarding_url"], status_code=302)


@router.get("/stripe/connect/return")
async def stripe_connect_return(
    request: Request,
    account_id: str = "",
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe's return redirect after the user completes onboarding.

    Stamps user.stripe_account_id if the account belongs to this user.
    """
    if not user:
        return _login_redirect()

    # Sanity-check the account_id format
    if not account_id or not account_id.startswith("acct_"):
        logger.warning(
            "stripe_connect_return: bad account_id=%r for user %d", account_id, user.id
        )
        return RedirectResponse(url="/user/settings?stripe_error=1", status_code=302)

    # Security: verify the account was created by us for THIS user
    stripe = _get_stripe()
    if stripe:
        try:
            acct = stripe.Account.retrieve(account_id)
            # Stripe SDK 15.x quirk: acct.metadata is a StripeObject. It
            # supports subscript access (`md["k"]`) but does NOT support
            # `.get(...)` (raises AttributeError) and `dict(md)` raises
            # KeyError(0) because StripeObject lacks proper dict iteration.
            # Subscript-with-try is the only API that works across SDK 15.x
            # AND older SDKs.
            try:
                owner_id = acct.metadata["user_id"]
            except (KeyError, TypeError):
                owner_id = None
            if owner_id != str(user.id):
                logger.warning(
                    "stripe_connect_return: account %s metadata.user_id=%s != user %d",
                    account_id, owner_id, user.id,
                )
                return RedirectResponse(url="/user/settings?stripe_error=1", status_code=302)
        except Exception as exc:
            logger.error(
                "stripe_connect_return: failed to retrieve account %s: %s", account_id, exc
            )
            return RedirectResponse(url="/user/settings?stripe_error=1", status_code=302)

    # Stamp the account ID
    user.stripe_account_id = account_id
    _audit(db, user.id, "stripe_account_stamped", {"account_id": account_id})
    await db.flush()

    return RedirectResponse(url="/user/earnings?connected=1", status_code=302)


@router.get("/stripe/connect/refresh")
async def stripe_connect_refresh(
    user: User | None = Depends(get_user_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Re-generate a Stripe AccountLink for users whose previous link expired.

    Stripe AccountLinks expire after 5 minutes — this produces a fresh one.
    """
    if not user:
        return _login_redirect()

    result = await create_user_stripe_account(user.id, user.email)
    if result is None:
        return RedirectResponse(url="/user/settings?stripe_error=1", status_code=302)

    _audit(db, user.id, "stripe_connect_refresh", {
        "account_id": result["account_id"],
    })
    await db.flush()

    return RedirectResponse(url=result["onboarding_url"], status_code=302)
