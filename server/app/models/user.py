from datetime import datetime
from sqlalchemy import String, Numeric, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    platforms: Mapped[dict] = mapped_column(JSONB, default=dict)
    # platforms: {"x": {"username": "@handle", "connected": true},
    #             "linkedin": {"username": "...", "connected": true}, ...}

    follower_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    # follower_counts: {"x": 1500, "linkedin": 500, "facebook": 200, ...}

    niche_tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    # ["finance", "tech", "lifestyle"]

    trust_score: Mapped[int] = mapped_column(Integer, default=50)
    mode: Mapped[str] = mapped_column(String(20), default="semi_auto")
    # full_auto | semi_auto | manual

    earnings_balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    total_earned: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # active | suspended | banned

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    assignments = relationship("CampaignAssignment", back_populates="user", lazy="selectin")
    payouts = relationship("Payout", back_populates="user", lazy="selectin")
    penalties = relationship("Penalty", back_populates="user", lazy="selectin")
