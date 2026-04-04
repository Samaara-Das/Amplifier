from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(50))
    # user_suspended, user_unsuspended, user_banned, trust_adjusted,
    # company_funds_added, company_funds_deducted, company_suspended,
    # campaign_paused, campaign_resumed, campaign_cancelled,
    # review_approved, review_rejected, appeal_approved, appeal_denied,
    # billing_cycle_run, payout_cycle_run, trust_check_run

    target_type: Mapped[str] = mapped_column(String(30))
    # user, company, campaign, payout, penalty, system

    target_id: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    admin_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
