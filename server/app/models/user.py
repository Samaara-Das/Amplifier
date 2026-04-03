from datetime import datetime
from sqlalchemy import String, Numeric, Integer, DateTime, func
from sqlalchemy import JSON as JSONB
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

    niche_tags: Mapped[list] = mapped_column(JSONB, default=list)
    # ["finance", "tech", "lifestyle"] — stored as JSON array

    audience_region: Mapped[str] = mapped_column(String(50), default="global")
    # Where the user's audience is: "us", "uk", "india", "eu", "global", etc.

    trust_score: Mapped[int] = mapped_column(Integer, default=50)
    mode: Mapped[str] = mapped_column(String(20), default="semi_auto")
    # full_auto | semi_auto | manual

    earnings_balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    earnings_balance_cents: Mapped[int] = mapped_column(Integer, default=0)  # v2: money as cents
    total_earned: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    total_earned_cents: Mapped[int] = mapped_column(Integer, default=0)  # v2: money as cents

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # active | suspended | banned

    # v2: Scraped profile data
    scraped_profiles: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Per-platform scraped data: {"x": {"follower_count": 1500, ...}, "linkedin": {...}}

    ai_detected_niches: Mapped[list] = mapped_column(JSONB, default=list)
    # AI-classified niches from scraped post content: ["finance", "tech", "crypto"]

    last_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
