from datetime import datetime
from sqlalchemy import String, Text, Numeric, Boolean, DateTime, ForeignKey, Integer, func
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

    # Phase C schema extensions (Tier 4 features)
    campaign_goal: Mapped[str | None] = mapped_column(String(30), nullable=True, default="brand_awareness")
    # brand_awareness | leads | virality | engagement
    campaign_type: Mapped[str | None] = mapped_column(String(20), nullable=True, default="ai_generated")
    # ai_generated | repost | political
    tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # professional | casual | edgy | educational | urgent
    preferred_formats: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"x": ["thread", "poll"], "linkedin": ["carousel"]}
    disclaimer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "#ad" or "Paid for by [committee]" — appended to every post

    penalty_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    # penalty_rules: {"post_deleted_24h": 5.00, "off_brief": 2.00, "fake_metrics": 50.00}

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft | active | paused | completed | cancelled

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # v2: AI wizard & invitation tracking
    company_urls: Mapped[list] = mapped_column(JSONB, default=list)
    # URLs provided by company during wizard step 1

    ai_generated_brief: Mapped[bool] = mapped_column(Boolean, default=False)
    # True if the brief was generated/enriched by AI from scraped URLs

    budget_exhaustion_action: Mapped[str] = mapped_column(
        String(20), default="auto_pause"
    )
    # "auto_pause" (can top up and resume) or "auto_complete" (campaign ends)

    # Budget management
    budget_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when budget_remaining < 20% of budget_total — triggers 80% alert

    screening_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )
    # pending | approved | flagged | rejected

    campaign_version: Mapped[int] = mapped_column(Integer, default=1)
    # Incremented on every edit — user app compares to detect campaign changes

    # Denormalized invitation counters
    invitation_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, default=0)

    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Maximum number of users who can accept this campaign

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="campaigns")
    assignments = relationship("CampaignAssignment", back_populates="campaign", lazy="selectin")
