"""Payment processing via Stripe Connect.

Companies top up balance via Stripe Checkout.
Users receive payouts via Stripe Connect Express.
"""

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.models.payout import Payout

logger = logging.getLogger(__name__)
settings = get_settings()

# Stripe is optional — only import if key is set
_stripe = None


def _get_stripe():
    global _stripe
    if _stripe is None:
        try:
            import stripe
            stripe.api_key = settings.stripe_secret_key or os.getenv("STRIPE_SECRET_KEY", "")
            if stripe.api_key:
                _stripe = stripe
            else:
                logger.warning("STRIPE_SECRET_KEY not set — payments disabled")
        except ImportError:
            logger.warning("stripe package not installed — payments disabled")
    return _stripe


async def create_company_checkout(company_id: int, amount_cents: int, db: AsyncSession) -> str | None:
    """Create a Stripe Checkout session for company to top up balance.

    Returns the checkout URL or None if Stripe is not configured.
    """
    stripe = _get_stripe()
    if not stripe:
        return None

    base_url = settings.server_url
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Amplifier Balance Top-Up"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{base_url}/company/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/company/billing?cancelled=1",
            metadata={"company_id": str(company_id)},
        )
        return session.url
    except Exception as e:
        logger.error("Failed to create checkout session: %s", e)
        return None


async def verify_checkout_session(session_id: str) -> dict | None:
    """Retrieve a completed Stripe Checkout session and return payment details.

    Returns dict with {company_id, amount_cents, payment_status} or None on failure.
    """
    stripe = _get_stripe()
    if not stripe:
        return None

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return None
        # Stripe SDK 15.x: metadata is a StripeObject. Subscript-with-try is
        # the only access pattern that works (no .get(), no dict() iteration).
        try:
            company_id = session.metadata["company_id"]
        except (KeyError, TypeError):
            return None
        if not company_id:
            return None
        return {
            "company_id": int(company_id),
            "amount_cents": session.amount_total,
            "payment_status": session.payment_status,
        }
    except Exception as e:
        logger.error("Failed to retrieve checkout session %s: %s", session_id, e)
        return None


async def create_user_stripe_account(user_id: int, email: str) -> str | None:
    """Create a Stripe Connect Express account for a user.

    Returns the onboarding URL or None.
    """
    stripe = _get_stripe()
    if not stripe:
        return None

    try:
        account = stripe.Account.create(
            type="express",
            email=email,
            capabilities={"transfers": {"requested": True}},
            metadata={"user_id": str(user_id)},
        )

        # Create account link for onboarding
        link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/user/stripe/connect/refresh",
            return_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/user/stripe/connect/return?account_id={account.id}",
            type="account_onboarding",
        )

        return {"account_id": account.id, "onboarding_url": link.url}
    except Exception as e:
        logger.error("Failed to create Stripe account: %s", e)
        return None


async def process_payout(user_id: int, amount: float, stripe_account_id: str, db: AsyncSession) -> bool:
    """Send a payout to a user via Stripe Connect."""
    stripe = _get_stripe()
    if not stripe:
        return False

    try:
        transfer = stripe.Transfer.create(
            amount=int(amount * 100),  # cents
            currency="usd",
            destination=stripe_account_id,
            metadata={"user_id": str(user_id)},
        )
        logger.info("Payout of $%.2f to user %d: %s", amount, user_id, transfer.id)
        return True
    except Exception as e:
        logger.error("Payout failed for user %d: %s", user_id, e)
        return False


async def run_payout_cycle(db: AsyncSession) -> dict:
    """Process pending payouts for all eligible users.

    Creates aggregate payout records from available earnings.
    Returns summary: {users_paid, total_paid, failures}
    """
    min_threshold = settings.min_payout_threshold

    # Get users with available balance above threshold
    result = await db.execute(
        select(User).where(
            and_(
                User.earnings_balance >= min_threshold,
                User.status == "active",
            )
        )
    )
    users = result.scalars().all()

    users_paid = 0
    total_paid = 0.0
    failures = 0

    now = datetime.now(timezone.utc)
    for user in users:
        amount = float(user.earnings_balance)
        amount_cents = int(amount * 100)
        payout = Payout(
            user_id=user.id,
            campaign_id=None,  # Aggregate payout
            amount=amount,
            amount_cents=amount_cents,
            period_start=now,
            period_end=now,
            status="processing",
            breakdown={"aggregate": True, "balance_at_time_cents": amount_cents},
        )
        db.add(payout)

        # Reset balance
        user.earnings_balance = 0.0
        user.earnings_balance_cents = 0
        users_paid += 1
        total_paid += amount

    await db.flush()

    logger.info("Payout cycle: %d users, $%.2f total, %d failures",
                users_paid, total_paid, failures)

    return {"users_paid": users_paid, "total_paid": total_paid, "failures": failures}


async def process_pending_payouts(db: AsyncSession) -> dict:
    """Auto-process payouts in 'processing' status via Stripe Connect.

    v2 pattern: runs as a background task (every 5 min via cron or admin trigger).
    For each payout:
      - If Stripe is configured: send transfer, update status to paid/failed
      - If no Stripe: mark as paid (test mode)

    Returns: {processed, paid, failed}
    """
    result = await db.execute(
        select(Payout).where(Payout.status == "processing")
    )
    payouts = result.scalars().all()

    processed = 0
    paid = 0
    failed = 0
    stripe = _get_stripe()

    for payout in payouts:
        processed += 1
        user_result = await db.execute(
            select(User).where(User.id == payout.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            payout.status = "failed"
            breakdown = payout.breakdown or {}
            breakdown["failure_reason"] = "User not found"
            payout.breakdown = breakdown
            failed += 1
            continue

        if stripe:
            # Real Stripe transfer
            stripe_account_id = user.stripe_account_id
            if stripe_account_id:
                try:
                    transfer = stripe.Transfer.create(
                        amount=payout.amount_cents or int(float(payout.amount) * 100),
                        currency="usd",
                        destination=stripe_account_id,
                        metadata={"user_id": str(payout.user_id), "payout_id": str(payout.id)},
                    )
                    payout.status = "paid"
                    breakdown = payout.breakdown or {}
                    breakdown["processor_ref"] = transfer.id
                    payout.breakdown = breakdown
                    flag_modified(payout, "breakdown")
                    paid += 1
                    logger.info("Stripe payout %d: $%.2f → user %d (transfer=%s)",
                                payout.id, float(payout.amount), payout.user_id, transfer.id)
                except Exception as e:
                    payout.status = "failed"
                    breakdown = payout.breakdown or {}
                    breakdown["failure_reason"] = str(e)
                    payout.breakdown = breakdown
                    flag_modified(payout, "breakdown")
                    # Return funds to user balance
                    user.earnings_balance = float(user.earnings_balance) + float(payout.amount)
                    user.earnings_balance_cents = (user.earnings_balance_cents or 0) + (payout.amount_cents or 0)
                    failed += 1
                    logger.error("Stripe payout %d failed: %s", payout.id, e)
            else:
                # No Stripe account — mark as paid in test mode
                payout.status = "paid"
                breakdown = payout.breakdown or {}
                breakdown["processor_ref"] = "test_mode_no_stripe_account"
                payout.breakdown = breakdown
                flag_modified(payout, "breakdown")
                paid += 1
                logger.info("Test mode payout %d: $%.2f → user %d (no Stripe account)",
                            payout.id, float(payout.amount), payout.user_id)
        else:
            # No Stripe configured — mark as paid (test mode)
            payout.status = "paid"
            breakdown = payout.breakdown or {}
            breakdown["processor_ref"] = "test_mode_no_stripe"
            payout.breakdown = breakdown
            flag_modified(payout, "breakdown")
            paid += 1

    if payouts:
        await db.flush()

    logger.info("Payout processing: %d processed, %d paid, %d failed", processed, paid, failed)
    return {"processed": processed, "paid": paid, "failed": failed}
