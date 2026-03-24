from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CampaignAssignment(Base):
    __tablename__ = "campaign_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(30), default="pending_invitation")
    # pending_invitation | accepted | content_generated | posted | paid | rejected | expired

    content_mode: Mapped[str] = mapped_column(String(20), default="ai_generated")
    # ai_generated | user_customized | repost

    payout_multiplier: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    # DEPRECATED — kept for backward compat, always 1.0 in v2

    # v2: Invitation lifecycle timestamps
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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

    __table_args__ = (
        Index("ix_assignment_user_status", "user_id", "status"),
        Index("ix_assignment_expires_at", "expires_at"),
    )
