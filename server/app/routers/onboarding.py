"""User registration and onboarding flow.

Routes:
    GET  /register               — registration form (optional ?agent=true)
    POST /register               — create user, set cookie, redirect
    GET  /user/onboarding        — legacy alias → 302 to /user/onboarding/step2
    GET  /user/onboarding/step2  — platform connection (SSE-driven)
    GET  /user/onboarding/step3  — API keys setup
    GET  /user/onboarding/step4  — 302 redirect to /user/campaigns
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, create_access_token
from app.models.user import User

router = APIRouter()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


def _render(template_name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    tpl = _env.get_template(template_name)
    return HTMLResponse(tpl.render(**ctx), status_code=status_code)


# ── Registration ──────────────────────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, agent: bool = False):
    return _render("auth/register.html", agent=agent)


@router.post("/register")
@limiter.limit("5/minute")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    accept_tos: bool = Form(False),
    agent: bool = False,
    db: AsyncSession = Depends(get_db),
):
    # ToS validation — re-render form with error, do NOT crash to error page
    if not accept_tos:
        return _render(
            "auth/register.html",
            status_code=400,
            error="You must accept the Terms of Service and Privacy Policy to register",
            agent=agent,
            email=email,
            accepted_tos=False,
        )

    # Duplicate email check — return 400 (existing auth.py pattern uses 400 for both)
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return _render(
            "auth/register.html",
            status_code=400,
            error="Email already registered",
            agent=agent,
            email=email,
            accepted_tos=True,
        )

    # Create user
    user = User(
        email=email,
        password_hash=hash_password(password),
        tos_accepted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "type": "user"})

    # Determine redirect target
    skip_local = os.environ.get("AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF") == "1"

    if agent and not skip_local:
        # Daemon-present path: hand off to localhost:5222 which will store the JWT
        # and redirect back to the hosted onboarding step 2.
        redirect_url = f"http://localhost:5222/auth/callback?token={token}"
    else:
        # UAT / no-daemon path: go directly to step 2
        redirect_url = "/user/onboarding/step2"

    response = RedirectResponse(url=redirect_url, status_code=302)
    # Always set the cookie so step2/SSE auth works whether the daemon
    # redirects back or we go directly.
    response.set_cookie(
        key="user_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


# ── Onboarding steps ──────────────────────────────────────────────────────────

@router.get("/user/onboarding", response_class=HTMLResponse)
async def onboarding_legacy(request: Request):
    """Legacy alias — redirect to step 2."""
    return RedirectResponse(url="/user/onboarding/step2", status_code=302)


@router.get("/user/onboarding/step2", response_class=HTMLResponse)
async def onboarding_step2(request: Request):
    return _render("onboarding/step2.html")


@router.get("/user/onboarding/step3", response_class=HTMLResponse)
async def onboarding_step3(request: Request):
    return _render("onboarding/step3.html")


@router.get("/user/onboarding/step4")
async def onboarding_step4(request: Request):
    """Final step — redirect to campaigns page.

    Auth check is omitted intentionally: /user/campaigns enforces auth itself.
    Adding a second check here would be duplicate logic.
    """
    return RedirectResponse(url="/user/campaigns", status_code=302)
