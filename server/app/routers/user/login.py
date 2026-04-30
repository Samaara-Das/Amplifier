"""Creator login / logout routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.models.user import User
from app.routers.user import _render

router = APIRouter()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return _render("user/login.html", error=error)


@router.post("/login")
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return _render("user/login.html", status_code=401, error="Invalid email or password")
    if user.status == "banned":
        return _render("user/login.html", status_code=403, error="Account has been banned")
    if user.status == "suspended":
        return _render("user/login.html", status_code=403, error="Account is suspended")

    token = create_access_token({"sub": str(user.id), "type": "user"})
    response = RedirectResponse(url="/user/", status_code=302)
    response.set_cookie(
        key="user_token",
        value=token,
        httponly=True,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/user/login", status_code=302)
    response.delete_cookie("user_token")
    return response
