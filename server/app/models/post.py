from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("campaign_assignments.id"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    # x | linkedin | facebook | reddit | tiktok | instagram

    post_url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))  # SHA256
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="live")
    # live | deleted | flagged

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    assignment = relationship("CampaignAssignment", back_populates="posts")
    metrics = relationship("Metric", back_populates="post", lazy="selectin")
