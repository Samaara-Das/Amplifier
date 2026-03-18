from datetime import datetime
from sqlalchemy import String, Text, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Penalty(Base):
    __tablename__ = "penalties"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)

    reason: Mapped[str] = mapped_column(String(30))
    # content_removed | off_brief | fake_metrics | platform_violation

    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    appealed: Mapped[bool] = mapped_column(Boolean, default=False)
    appeal_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="penalties")
