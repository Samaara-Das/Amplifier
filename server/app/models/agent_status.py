from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentStatus(Base):
    __tablename__ = "agent_status"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    platform_health: Mapped[dict] = mapped_column(JSONB, default=dict)
    # { linkedin: { connected: true, ... }, ... }
    ai_keys_configured: Mapped[dict] = mapped_column(JSONB, default=dict)
    # { gemini: true, mistral: false, groq: false }
    version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
