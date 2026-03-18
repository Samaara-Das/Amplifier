from datetime import datetime
from sqlalchemy import String, Text, Numeric, DateTime, ForeignKey, Integer, func
from sqlalchemy import JSON as JSONB  # Portable: works with SQLite and PostgreSQL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    brief: Mapped[str] = mapped_column(Text)
    assets: Mapped[dict] = mapped_column(JSONB, default=dict)
    # assets: {"image_urls": [], "links": [], "hashtags": [], "brand_guidelines": ""}

    budget_total: Mapped[float] = mapped_column(Numeric(12, 2))
    budget_remaining: Mapped[float] = mapped_column(Numeric(12, 2))
    payout_rules: Mapped[dict] = mapped_column(JSONB)
    # payout_rules: {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01,
    #                "rate_per_repost": 0.05, "rate_per_click": 0.10}

    targeting: Mapped[dict] = mapped_column(JSONB, default=dict)
    # targeting: {"min_followers": {"x": 100, "linkedin": 50}, "niche_tags": ["finance"],
    #             "required_platforms": ["x", "linkedin"]}

    content_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tone, must-include phrases, forbidden phrases

    penalty_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    # penalty_rules: {"post_deleted_24h": 5.00, "off_brief": 2.00, "fake_metrics": 50.00}

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft | active | paused | completed | cancelled

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="campaigns")
    assignments = relationship("CampaignAssignment", back_populates="campaign", lazy="selectin")
