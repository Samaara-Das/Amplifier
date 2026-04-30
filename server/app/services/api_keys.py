"""BYOK (Bring Your Own Keys) — company-scoped API key resolution.

Resolution order for any provider:
  1. Company row in company_api_keys (if company_id + db provided)
  2. Server env var  (GEMINI_API_KEY / MISTRAL_API_KEY / GROQ_API_KEY)
  3. Empty string    (caller should skip that provider)

Never raises. Logs which path was taken.
"""

import logging
import os
from typing import Callable, Awaitable, Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Auth-style error signals (case-insensitive substring match)
_AUTH_ERROR_SIGNALS = (
    "401",
    "403",
    "invalid api key",
    "api_key_invalid",
    "unauthorized",
    "permission_denied",
    "invalid_api_key",
)


def _is_auth_error(exc: Exception) -> bool:
    """Return True if exception looks like an API authentication failure."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _AUTH_ERROR_SIGNALS)


async def resolve_api_key(
    provider: str,
    company_id: int | None,
    db: AsyncSession | None,
) -> str:
    """Return the best available API key for the given provider.

    1. Company-specific key from DB (if company_id + db provided and row exists).
    2. Server env var fallback.
    3. Empty string if neither is set.

    Never raises.
    """
    if company_id is not None and db is not None:
        try:
            from sqlalchemy import select
            from app.models.company_api_key import CompanyApiKey
            from app.utils.crypto import decrypt, is_encrypted

            row = await db.scalar(
                select(CompanyApiKey).where(
                    CompanyApiKey.company_id == company_id,
                    CompanyApiKey.provider == provider,
                )
            )
            if row is not None:
                stored = row.encrypted_key
                if is_encrypted(stored):
                    decrypted = decrypt(stored)
                    # decrypt() returns input unchanged on failure — detect that
                    if decrypted != stored and decrypted:
                        logger.info(
                            "BYOK: using company key for provider=%s company_id=%d",
                            provider, company_id,
                        )
                        return decrypted
                    else:
                        logger.error(
                            "BYOK: decrypt failed for provider=%s company_id=%d — falling back to server key",
                            provider, company_id,
                        )
                else:
                    logger.error(
                        "BYOK: stored key is not encrypted for provider=%s company_id=%d — falling back",
                        provider, company_id,
                    )
        except Exception as exc:
            logger.error("BYOK: DB lookup error for provider=%s: %s — falling back", provider, exc)

    env_key = os.environ.get(f"{provider.upper()}_API_KEY", "").strip()
    logger.info("BYOK: using server key for provider=%s", provider)
    return env_key


async def call_with_byok_fallback(
    provider: str,
    company_id: int | None,
    db: AsyncSession | None,
    fn: Callable[[str], Awaitable[Any]],
) -> Any:
    """Call fn(api_key=<company_key>). If it raises an auth-style error and we used
    a company key, retry once with the server env-var key.

    fn must accept a single positional argument: the api_key string.
    """
    api_key = await resolve_api_key(provider, company_id, db)

    # Determine if we resolved a company key (vs server key)
    # by checking whether a row exists — re-use same logic cheaply
    used_company_key = False
    if company_id is not None and db is not None:
        try:
            from sqlalchemy import select
            from app.models.company_api_key import CompanyApiKey
            row = await db.scalar(
                select(CompanyApiKey).where(
                    CompanyApiKey.company_id == company_id,
                    CompanyApiKey.provider == provider,
                )
            )
            if row is not None:
                from app.utils.crypto import is_encrypted
                used_company_key = is_encrypted(row.encrypted_key)
        except Exception:
            pass

    try:
        return await fn(api_key)
    except Exception as exc:
        if used_company_key and _is_auth_error(exc):
            server_key = os.environ.get(f"{provider.upper()}_API_KEY", "").strip()
            logger.warning(
                "BYOK: company key auth error for provider=%s (company_id=%d), retrying with server key: %s",
                provider, company_id, exc,
            )
            return await fn(server_key)
        raise
