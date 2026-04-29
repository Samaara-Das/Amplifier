from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminReviewQueue(Base):
    """Campaigns flagged by AI review with brand_safety='caution'.

    Admins resolve these via the review-queue page. Created automatically
    by the quality gate when a caution rating is returned.
    """
    __tablename__ = "admin_review_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    concerns_json: Mapped[str] = mapped_column(Text, default="[]")
    # JSON-serialized list of concern strings from ai_review_campaign()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
