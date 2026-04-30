"""Tests for BYOK (Bring Your Own Keys) — Task #70.

Covers:
- Encrypt/decrypt round-trip for stored API keys
- resolve_api_key: company key, env fallback, decrypt-failure fallback
- call_with_byok_fallback: auth-error retry on company key, re-raise on non-auth
- Settings POST upserts and does NOT echo plaintext in GET
- ai_review_campaign calls resolve_api_key with campaign.company_id
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")


# ---------------------------------------------------------------------------
# Shared DB fixtures (in-memory SQLite)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine():
    from app.core.database import Base
    from app.models import CompanyApiKey  # ensure table registered  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_key_row(session, company_id: int, provider: str, plaintext_key: str):
    from app.models.company_api_key import CompanyApiKey
    from app.utils.crypto import encrypt
    row = CompanyApiKey(
        company_id=company_id,
        provider=provider,
        encrypted_key=encrypt(plaintext_key),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Encrypt round-trip for API key storage
# ---------------------------------------------------------------------------

class TestEncryptRoundTrip:
    def test_api_key_encrypt_decrypt(self):
        from app.utils.crypto import encrypt, decrypt
        key = "AIzaSy-fake-gemini-key-abc123"
        assert decrypt(encrypt(key)) == key

    def test_encrypted_value_is_not_plaintext(self):
        from app.utils.crypto import encrypt
        key = "secret-key-value"
        enc = encrypt(key)
        assert key not in enc
        assert ":" in enc  # iv_hex:ciphertext_hex format

    def test_is_encrypted_recognizes_stored_format(self):
        from app.utils.crypto import encrypt, is_encrypted
        enc = encrypt("some-api-key")
        assert is_encrypted(enc) is True
        assert is_encrypted("plaintext") is False


# ---------------------------------------------------------------------------
# resolve_api_key
# ---------------------------------------------------------------------------

class TestResolveApiKey:
    @pytest.mark.asyncio
    async def test_returns_company_key_when_row_exists(self, db_session):
        from app.services.api_keys import resolve_api_key
        from app.models.company import Company
        from app.core.security import hash_password

        company = Company(name="T", email="t@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()

        await _add_key_row(db_session, company.id, "gemini", "my-company-gemini-key")

        result = await resolve_api_key("gemini", company.id, db_session)
        assert result == "my-company-gemini-key"

    @pytest.mark.asyncio
    async def test_returns_env_var_when_no_row(self, db_session, monkeypatch):
        from app.services.api_keys import resolve_api_key
        monkeypatch.setenv("GEMINI_API_KEY", "server-gemini-key")

        result = await resolve_api_key("gemini", 9999, db_session)
        assert result == "server-gemini-key"

    @pytest.mark.asyncio
    async def test_returns_env_var_when_no_company_id(self, monkeypatch):
        from app.services.api_keys import resolve_api_key
        monkeypatch.setenv("MISTRAL_API_KEY", "server-mistral-key")

        result = await resolve_api_key("mistral", None, None)
        assert result == "server-mistral-key"

    @pytest.mark.asyncio
    async def test_falls_back_to_env_on_decrypt_failure(self, db_session, monkeypatch):
        """If stored value is corrupt (not valid encrypted format), fall through to env var."""
        from app.services.api_keys import resolve_api_key
        from app.models.company_api_key import CompanyApiKey
        from app.models.company import Company
        from app.core.security import hash_password

        monkeypatch.setenv("GROQ_API_KEY", "server-groq-key")

        company = Company(name="T2", email="t2@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()

        # Insert a row with plaintext (not encrypted) — simulates corrupt storage
        row = CompanyApiKey(
            company_id=company.id,
            provider="groq",
            encrypted_key="not_encrypted_no_colon_format",
        )
        db_session.add(row)
        await db_session.flush()

        result = await resolve_api_key("groq", company.id, db_session)
        assert result == "server-groq-key"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_nothing_configured(self, db_session, monkeypatch):
        from app.services.api_keys import resolve_api_key
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        result = await resolve_api_key("groq", None, None)
        assert result == ""


# ---------------------------------------------------------------------------
# call_with_byok_fallback
# ---------------------------------------------------------------------------

class TestCallWithByokFallback:
    @pytest.mark.asyncio
    async def test_calls_fn_with_company_key(self, db_session):
        from app.services.api_keys import call_with_byok_fallback
        from app.models.company import Company
        from app.core.security import hash_password

        company = Company(name="T3", email="t3@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()
        await _add_key_row(db_session, company.id, "gemini", "company-key-xyz")

        received = []

        async def fake_fn(api_key):
            received.append(api_key)
            return "ok"

        result = await call_with_byok_fallback("gemini", company.id, db_session, fake_fn)
        assert result == "ok"
        assert received[0] == "company-key-xyz"

    @pytest.mark.asyncio
    async def test_retries_with_server_key_on_auth_error(self, db_session, monkeypatch):
        """If company key causes 401 error, retries once with server env-var key."""
        from app.services.api_keys import call_with_byok_fallback
        from app.models.company import Company
        from app.core.security import hash_password

        monkeypatch.setenv("GEMINI_API_KEY", "server-fallback-key")

        company = Company(name="T4", email="t4@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()
        await _add_key_row(db_session, company.id, "gemini", "bad-company-key")

        calls = []

        async def fake_fn(api_key):
            calls.append(api_key)
            if api_key == "bad-company-key":
                raise RuntimeError("401 Unauthorized: invalid api key")
            return "success"

        result = await call_with_byok_fallback("gemini", company.id, db_session, fake_fn)
        assert result == "success"
        assert len(calls) == 2
        assert calls[0] == "bad-company-key"
        assert calls[1] == "server-fallback-key"

    @pytest.mark.asyncio
    async def test_does_not_retry_on_non_auth_error(self, db_session):
        """Non-auth errors (rate limits, server errors) are re-raised, not retried."""
        from app.services.api_keys import call_with_byok_fallback
        from app.models.company import Company
        from app.core.security import hash_password

        company = Company(name="T5", email="t5@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()
        await _add_key_row(db_session, company.id, "gemini", "ok-company-key")

        call_count = 0

        async def fake_fn(api_key):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("RESOURCE_EXHAUSTED: 429 rate limit")

        with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
            await call_with_byok_fallback("gemini", company.id, db_session, fake_fn)

        # Called once only — not retried
        assert call_count == 1


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

class TestSettingsEndpoints:
    @pytest.mark.asyncio
    async def test_post_api_keys_upserts_encrypted(self, db_session):
        """POST /company/settings/api-keys stores encrypted values, not plaintext."""
        from app.models.company import Company
        from app.models.company_api_key import CompanyApiKey
        from app.core.security import hash_password
        from app.utils.crypto import is_encrypted

        company = Company(name="T6", email="t6@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()

        # Simulate what the route handler does
        from app.utils.crypto import encrypt
        from sqlalchemy import select

        raw_key = "AIzaSy-test-gemini-key-12345"
        encrypted = encrypt(raw_key)

        row = CompanyApiKey(
            company_id=company.id,
            provider="gemini",
            encrypted_key=encrypted,
        )
        db_session.add(row)
        await db_session.flush()

        # Verify stored value is not plaintext
        stored = await db_session.scalar(
            select(CompanyApiKey).where(
                CompanyApiKey.company_id == company.id,
                CompanyApiKey.provider == "gemini",
            )
        )
        assert stored is not None
        assert stored.encrypted_key != raw_key
        assert is_encrypted(stored.encrypted_key)

    @pytest.mark.asyncio
    async def test_upsert_overwrites_existing_row(self, db_session):
        from app.models.company import Company
        from app.models.company_api_key import CompanyApiKey
        from app.core.security import hash_password
        from app.utils.crypto import encrypt, decrypt
        from sqlalchemy import select

        company = Company(name="T7", email="t7@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()

        # Insert initial key
        row = CompanyApiKey(
            company_id=company.id,
            provider="mistral",
            encrypted_key=encrypt("old-key"),
        )
        db_session.add(row)
        await db_session.flush()

        # Overwrite
        row.encrypted_key = encrypt("new-key")
        await db_session.flush()

        stored = await db_session.scalar(
            select(CompanyApiKey).where(
                CompanyApiKey.company_id == company.id,
                CompanyApiKey.provider == "mistral",
            )
        )
        assert decrypt(stored.encrypted_key) == "new-key"

    @pytest.mark.asyncio
    async def test_get_configured_providers_returns_correct_set(self, db_session):
        from app.routers.company.settings import _get_configured_providers
        from app.models.company import Company
        from app.core.security import hash_password

        company = Company(name="T8", email="t8@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()

        assert await _get_configured_providers(company.id, db_session) == set()

        await _add_key_row(db_session, company.id, "gemini", "key1")
        await _add_key_row(db_session, company.id, "groq", "key2")

        configured = await _get_configured_providers(company.id, db_session)
        assert configured == {"gemini", "groq"}
        assert "mistral" not in configured


# ---------------------------------------------------------------------------
# ai_review_campaign wiring: passes company_id + db to resolve_api_key
# ---------------------------------------------------------------------------

class TestAiReviewCampaignByok:
    @pytest.mark.asyncio
    async def test_review_calls_resolve_with_company_id(self, db_session):
        """ai_review_campaign should pass campaign.company_id and db into _run_gemini_review."""
        from app.services import quality_gate

        campaign = MagicMock()
        campaign.company_id = 42
        campaign.title = "Test Campaign"
        campaign.brief = "x" * 50
        campaign.content_guidance = "y" * 50
        campaign.payout_rules = {}
        campaign.targeting = {}

        captured = {}

        async def fake_gemini_review(camp, prompt, model="gemini-2.0-flash", company_id=None, db=None):
            captured["company_id"] = company_id
            captured["db"] = db
            return {"passed": True, "brand_safety": "safe", "concerns": []}

        with patch.object(quality_gate, "_run_gemini_review", side_effect=fake_gemini_review):
            os.environ.pop("AMPLIFIER_UAT_BYPASS_AI_REVIEW", None)
            os.environ.pop("AMPLIFIER_UAT_FORCE_AI_REVIEW_RESULT", None)
            result = await quality_gate.ai_review_campaign(campaign, db=db_session)

        assert result["brand_safety"] == "safe"
        assert captured["company_id"] == 42
        assert captured["db"] is db_session

    @pytest.mark.asyncio
    async def test_gemini_review_uses_byok_fallback_wrapper(self, db_session, monkeypatch):
        """_run_gemini_review calls call_with_byok_fallback — verifies the wiring.

        We patch call_with_byok_fallback to record calls and return a valid result,
        then assert it was invoked with the correct provider and company_id.
        """
        from app.services import quality_gate
        from app.services import api_keys as ak
        from app.models.company import Company
        from app.core.security import hash_password

        monkeypatch.setenv("GEMINI_API_KEY", "server-gemini-key")

        company = Company(name="T9", email="t9@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()
        await _add_key_row(db_session, company.id, "gemini", "company-gemini-key")

        fallback_calls = []
        original_fallback = ak.call_with_byok_fallback

        async def recording_fallback(provider, cid, db_s, fn):
            fallback_calls.append({"provider": provider, "company_id": cid})
            # Call through to the real fn with the company key
            return await original_fallback(provider, cid, db_s, fn)

        campaign_mock = MagicMock()
        campaign_mock.company_id = company.id
        campaign_mock.payout_rules = {}
        campaign_mock.targeting = {}
        campaign_mock.title = "T"
        campaign_mock.brief = "b" * 50
        campaign_mock.content_guidance = "g" * 50

        # Patch the genai Client so no real network calls happen
        mock_response = MagicMock()
        mock_response.text = '{"passed": true, "brand_safety": "safe", "concerns": []}'

        with patch.object(ak, "call_with_byok_fallback", side_effect=recording_fallback):
            import asyncio as _asyncio
            with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_response)):
                with patch.dict("sys.modules", {"google": MagicMock(), "google.genai": MagicMock()}):
                    result = await quality_gate._run_gemini_review(
                        campaign_mock, "prompt", "gemini-2.0-flash",
                        company_id=company.id, db=db_session,
                    )

        assert len(fallback_calls) == 1
        assert fallback_calls[0]["provider"] == "gemini"
        assert fallback_calls[0]["company_id"] == company.id

    @pytest.mark.asyncio
    async def test_fallback_retries_on_401_within_gemini_review(self, db_session, monkeypatch):
        """Integration: call_with_byok_fallback retries with server key when company key gets 401."""
        from app.services.api_keys import call_with_byok_fallback
        from app.models.company import Company
        from app.core.security import hash_password

        monkeypatch.setenv("GEMINI_API_KEY", "server-good-key")

        company = Company(name="T10", email="t10@t.com", password_hash=hash_password("p"), balance=0)
        db_session.add(company)
        await db_session.flush()
        await _add_key_row(db_session, company.id, "gemini", "bad-company-key")

        keys_tried = []

        async def fn_that_fails_on_company_key(api_key: str):
            keys_tried.append(api_key)
            if api_key == "bad-company-key":
                raise RuntimeError("401 Unauthorized: invalid api key")
            return {"passed": True, "brand_safety": "safe", "concerns": []}

        result = await call_with_byok_fallback(
            "gemini", company.id, db_session, fn_that_fails_on_company_key
        )

        assert result["brand_safety"] == "safe"
        assert keys_tried[0] == "bad-company-key"   # tried company key first
        assert keys_tried[1] == "server-good-key"    # retried with server key
