from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContentScreeningLog(Base):
    __tablename__ = "content_screening_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), unique=True, index=True)

    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    screening_categories: Mapped[list] = mapped_column(JSONB, default=list)

    reviewed_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    review_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # approved | rejected
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
