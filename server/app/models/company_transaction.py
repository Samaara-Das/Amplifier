"""Company payment transactions — idempotency tracking for Stripe Checkout."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyTransaction(Base):
    __tablename__ = "company_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), index=True)
    stripe_session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20), default="topup")
    # topup | refund
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
