"""Public unauthenticated pages — /terms and /privacy."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

router = APIRouter()

_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    tpl = _env.get_template("public/terms.html")
    return HTMLResponse(tpl.render(request=request))


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    tpl = _env.get_template("public/privacy.html")
    return HTMLResponse(tpl.render(request=request))
