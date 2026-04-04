"""Admin login/logout routes."""

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routers.admin import _render, ADMIN_PASSWORD, ADMIN_TOKEN_VALUE

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return _render("admin/login.html", error=error)


@router.post("/login")
async def login_submit(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin/", status_code=303)
        response.set_cookie("admin_token", ADMIN_TOKEN_VALUE, httponly=True, samesite="lax")
        return response
    return RedirectResponse(url="/admin/login?error=Invalid+password", status_code=303)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_token")
    return response
