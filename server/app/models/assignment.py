from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CampaignAssignment(Base):
    __tablename__ = "campaign_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(30), default="assigned")
    # assigned | content_generated | posted | metrics_collected | paid | skipped

    content_mode: Mapped[str] = mapped_column(String(20), default="ai_generated")
    # ai_generated | user_customized | repost

    payout_multiplier: Mapped[float] = mapped_column(Numeric(3, 2), default=1.5)
    # 1.0 repost, 1.5 AI generated, 2.0 user customized

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    campaign = relationship("Campaign", back_populates="assignments")
    user = relationship("User", back_populates="assignments")
    posts = relationship("Post", back_populates="assignment", lazy="selectin")
