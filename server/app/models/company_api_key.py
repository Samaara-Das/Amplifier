from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyApiKey(Base):
    """Encrypted per-provider API keys for BYOK (Bring Your Own Keys).

    Row exists ⇒ configured for that provider.
    No row ⇒ server falls back to its own env-var key.
    Unique on (company_id, provider) — one row per provider per company.
    """

    __tablename__ = "company_api_keys"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_company_api_keys_company_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'gemini' | 'mistral' | 'groq'

    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Format: iv_hex:ciphertext_hex (AES-256-GCM via app.utils.crypto)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
