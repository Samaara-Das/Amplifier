"""Company login/register/logout routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.company import Company
from app.routers.company import _render

router = APIRouter()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return _render("company/login.html", error=error)


@router.post("/login")
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Company).where(Company.email == email))
    company = result.scalar_one_or_none()
    if not company or not verify_password(password, company.password_hash):
        return _render("company/login.html", status_code=401, error="Invalid email or password")

    token = create_access_token({"sub": str(company.id), "type": "company"})
    response = RedirectResponse(url="/company/", status_code=302)
    response.set_cookie(
        key="company_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


@router.post("/register")
@limiter.limit("5/minute")
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    accept_tos: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    if not accept_tos:
        return _render("company/login.html", status_code=400, error="You must accept the Terms of Service and Privacy Policy to register", show_register=True)

    existing = await db.execute(select(Company).where(Company.email == email))
    if existing.scalar_one_or_none():
        return _render("company/login.html", status_code=400, error="Email already registered", show_register=True)

    company = Company(
        name=name,
        email=email,
        password_hash=hash_password(password),
        tos_accepted_at=datetime.now(timezone.utc),
    )
    db.add(company)
    await db.flush()

    token = create_access_token({"sub": str(company.id), "type": "company"})
    response = RedirectResponse(url="/company/", status_code=302)
    response.set_cookie(
        key="company_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/company/login", status_code=302)
    response.delete_cookie("company_token")
    return response
