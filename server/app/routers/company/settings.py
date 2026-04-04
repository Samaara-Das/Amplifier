"""Company settings page."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.routers.company import _render, _login_redirect, get_company_from_cookie

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    company: Company | None = Depends(get_company_from_cookie),
):
    if not company:
        return _login_redirect()

    return _render("company/settings.html", company=company, active_page="settings")


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
            return _render(
                "company/settings.html",
                status_code=400,
                company=company,
                active_page="settings",
                error="Email already in use by another account",
            )

    company.name = name
    company.email = email
    await db.flush()

    return _render("company/settings.html", company=company, active_page="settings", success="Profile updated successfully")
