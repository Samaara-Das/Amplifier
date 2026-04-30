"""Company settings page."""

import httpx
import asyncio

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.company_api_key import CompanyApiKey
from app.routers.company import _render, _login_redirect, get_company_from_cookie
from app.utils.crypto import encrypt, is_encrypted

router = APIRouter()

_PROVIDERS = ("gemini", "mistral", "groq")


async def _get_configured_providers(company_id: int, db: AsyncSession) -> set[str]:
    """Return set of provider names that have a configured key for this company."""
    rows = await db.execute(
        select(CompanyApiKey.provider).where(CompanyApiKey.company_id == company_id)
    )
    return {r[0] for r in rows.fetchall()}


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    configured = await _get_configured_providers(company.id, db)
    return _render(
        "company/settings.html",
        company=company,
        active_page="settings",
        configured_providers=configured,
    )


@router.post("/settings")
async def settings_update(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    if not company:
        return _login_redirect()

    if email != company.email:
        existing = await db.execute(select(Company).where(Company.email == email))
        if existing.scalar_one_or_none():
            configured = await _get_configured_providers(company.id, db)
            return _render(
                "company/settings.html",
                status_code=400,
                company=company,
                active_page="settings",
                error="Email already in use by another account",
                configured_providers=configured,
            )

    company.name = name
    company.email = email
    await db.flush()

    configured = await _get_configured_providers(company.id, db)
    return _render(
        "company/settings.html",
        company=company,
        active_page="settings",
        success="Profile updated successfully",
        configured_providers=configured,
    )


@router.post("/settings/api-keys")
async def api_keys_save(
    request: Request,
    gemini_key: str = Form(default=""),
    mistral_key: str = Form(default=""),
    groq_key: str = Form(default=""),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Upsert company API keys. Empty value = leave existing row untouched."""
    if not company:
        return _login_redirect()

    raw_keys = {
        "gemini": gemini_key.strip(),
        "mistral": mistral_key.strip(),
        "groq": groq_key.strip(),
    }

    saved = []
    for provider, raw_key in raw_keys.items():
        if not raw_key:
            continue  # empty → no change (no clear in v1)

        encrypted = encrypt(raw_key)

        # Upsert: update if row exists, insert otherwise
        existing = await db.scalar(
            select(CompanyApiKey).where(
                CompanyApiKey.company_id == company.id,
                CompanyApiKey.provider == provider,
            )
        )
        if existing:
            existing.encrypted_key = encrypted
        else:
            db.add(CompanyApiKey(
                company_id=company.id,
                provider=provider,
                encrypted_key=encrypted,
            ))
        saved.append(provider)

    await db.flush()

    configured = await _get_configured_providers(company.id, db)
    msg = f"Saved keys for: {', '.join(saved)}" if saved else "No keys provided — nothing changed."
    return _render(
        "company/settings.html",
        company=company,
        active_page="settings",
        success=msg,
        configured_providers=configured,
    )


@router.post("/settings/api-keys/test")
async def api_keys_test(
    request: Request,
    provider: str = Form(...),
    company: Company | None = Depends(get_company_from_cookie),
    db: AsyncSession = Depends(get_db),
):
    """Test whether the company's stored key for a provider actually works.

    Returns JSON {success: bool, message: str} for HTMX display.
    """
    if not company:
        return JSONResponse({"success": False, "message": "Not authenticated"}, status_code=401)

    if provider not in _PROVIDERS:
        return JSONResponse({"success": False, "message": f"Unknown provider: {provider}"})

    from app.services.api_keys import resolve_api_key

    # Only test the company key specifically — don't fall through to server key
    row = await db.scalar(
        select(CompanyApiKey).where(
            CompanyApiKey.company_id == company.id,
            CompanyApiKey.provider == provider,
        )
    )
    if not row:
        return JSONResponse({"success": False, "message": "No key configured for this provider"})

    from app.utils.crypto import decrypt
    api_key = decrypt(row.encrypted_key)
    if not api_key or api_key == row.encrypted_key:
        return JSONResponse({"success": False, "message": "Key decrypt failed — try saving again"})

    try:
        if provider == "gemini":
            success, message = await _test_gemini(api_key)
        else:
            base_url = "https://api.mistral.ai/v1" if provider == "mistral" else "https://api.groq.com/openai/v1"
            model = "mistral-large-latest" if provider == "mistral" else "llama-3.3-70b-versatile"
            success, message = await _test_openai_compat(api_key, base_url, model, provider)
        return JSONResponse({"success": success, "message": message})
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"Test error: {str(exc)[:120]}"})


async def _test_gemini(api_key: str) -> tuple[bool, str]:
    """Make a minimal Gemini call to verify the key."""
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # Small single-token generation — cheapest possible test
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents="Reply with the single word: ok",
        )
        _ = response.text  # access to force any error
        return True, "Gemini key is valid"
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg or "API_KEY_INVALID" in msg or "invalid" in msg.lower():
            return False, "Invalid API key"
        return False, f"Test failed: {msg[:120]}"


async def _test_openai_compat(api_key: str, base_url: str, model: str, provider: str) -> tuple[bool, str]:
    """Make a minimal chat completions call to verify the key."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "max_tokens": 5,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code == 200:
        return True, f"{provider.capitalize()} key is valid"
    if resp.status_code in (401, 403):
        return False, "Invalid API key"
    return False, f"Test failed: HTTP {resp.status_code}"
