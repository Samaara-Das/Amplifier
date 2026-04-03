from datetime import datetime
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, func
from sqlalchemy import JSON as JSONB  # Portable: works with SQLite and PostgreSQL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Hold period: earnings stay in "pending" for 7 days before becoming "available"
# This gives time to detect fraud (deleted posts, fake metrics) before payout.
EARNING_HOLD_DAYS = 7


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)

    # Money stored as integer cents (v2 pattern: eliminates float rounding)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Legacy float column — kept for backward compat during migration
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending → available → processing → paid
    # pending → voided  (fraud detected during hold period)
    # Earning lifecycle (v2 pattern):
    #   pending: created on metric billing, held for EARNING_HOLD_DAYS
    #   available: hold period passed, user can request withdrawal
    #   processing: payout in progress (Stripe/PayPal)
    #   paid: money sent successfully
    #   voided: fraud detected — earning cancelled, funds returned to campaign
    #   failed: payout attempt failed, funds back to available

    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When this earning becomes available for withdrawal.
    # Set to created_at + EARNING_HOLD_DAYS on creation.

    breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"metric_id": 42, "post_id": 7, "platform": "x",
    #  "impressions": 1500, "likes": 23, "reposts": 5, "clicks": 0,
    #  "platform_cut_pct": 20}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="payouts")
