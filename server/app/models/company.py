from datetime import datetime, timezone
from sqlalchemy import String, Integer, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)  # v2: money as cents
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active | suspended
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    campaigns = relationship("Campaign", back_populates="company", lazy="selectin")
