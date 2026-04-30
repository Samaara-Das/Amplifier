from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy import JSON as JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


COMMAND_TYPES = (
    "draft_approved",
    "draft_rejected",
    "draft_edited",
    "generate_content",
    "scrape_profiles",
    "force_poll",
    "pause_agent",
    "resume_agent",
)


class AgentCommand(Base):
    __tablename__ = "agent_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending | processing | done | failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
