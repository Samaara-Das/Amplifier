from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index, func
from sqlalchemy import JSON as JSONB  # Portable: works with SQLite and PostgreSQL
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CampaignInvitationLog(Base):
    __tablename__ = "campaign_invitation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    event: Mapped[str] = mapped_column(String(30))
    # sent | accepted | rejected | expired | re_invited

    event_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    # Column name in DB is "metadata", but Python attribute is "event_metadata"
    # to avoid conflict with SQLAlchemy's reserved `metadata` attribute

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_invitation_log_campaign_user", "campaign_id", "user_id"),
    )
