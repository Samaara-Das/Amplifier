from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    # linkedin | facebook | reddit

    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # daemon's local path to image on disk

    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending | approved | rejected | posted

    iteration: Mapped[int] = mapped_column(Integer, default=1)
    # day_number from content agent

    local_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # daemon's agent_draft.id — used for idempotent upsert on retry

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
