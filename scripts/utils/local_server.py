"""Local creator app — slim FastAPI on localhost:5222.

Five top-level pages:
  /auth/callback  — OAuth JWT handoff from hosted server
  /connect        — Platform connection (LinkedIn / Facebook / Reddit)
  /keys           — API key management (Gemini / Mistral / Groq / Cloudflare / Together)
  /drafts         — Draft review (all campaigns)
  /drafts/{id}    — Draft review (single campaign)

Sub-actions under /drafts/:
  POST /drafts/{id}/approve
  POST /drafts/{id}/reject
  POST /drafts/{id}/restore
  POST /drafts/{id}/unapprove
  POST /drafts/{id}/edit
  GET  /drafts/{id}/image

Other:
  GET  /healthz
  POST /connect/{platform}
  POST /keys
  POST /keys/test
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "config" / ".env")

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from utils.local_db import (
    approve_draft,
    get_all_drafts,
    get_draft,
    get_setting,
    init_db,
    reject_draft,
    set_setting,
    update_draft_text,
)
from utils.guard import filter_disabled

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SERVER_BASE_URL = os.getenv("CAMPAIGN_SERVER_URL", "http://127.0.0.1:8000")
HOSTED_BASE_URL = os.getenv("AMPLIFIER_HOSTED_URL", SERVER_BASE_URL)

PLATFORM_LABELS: dict[str, str] = {
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "reddit": "Reddit",
}
CONNECTABLE_PLATFORMS = filter_disabled(["linkedin", "facebook", "reddit"])

AI_KEY_FIELDS: list[tuple[str, str, str]] = [
    ("gemini_api_key", "Gemini", "AIza..."),
    ("mistral_api_key", "Mistral", "..."),
    ("groq_api_key", "Groq", "gsk_..."),
    ("cloudflare_api_key", "Cloudflare Workers AI", "..."),
    ("together_api_key", "Together AI", "..."),
]


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    app = FastAPI(title="Amplifier Local", docs_url=None, redoc_url=None)

    templates_dir = ROOT / "scripts" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    static_dir = ROOT / "scripts" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        init_db()

    # ── Custom Jinja2 filters ─────────────────────────────────────────────────

    def display_status(draft: dict) -> str:
        """Human-readable status string for a draft dict."""
        if draft.get("posted"):
            return "posted"
        approved = draft.get("approved", 0)
        if approved == 1:
            return "approved"
        if approved == -1:
            return "rejected"
        return "pending"

    templates.env.filters["display_status"] = display_status

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_authed() -> bool:
        from utils.server_client import is_logged_in
        return is_logged_in()

    def _fire_and_forget(coro) -> None:
        """Schedule a coroutine without awaiting; errors are logged only."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(coro)
        except Exception as exc:
            logger.warning("fire_and_forget scheduling error: %s", exc)

    async def _sync_draft_to_server(draft_id: int, status: str,
                                    text: str | None = None) -> None:
        """Background: PATCH server draft. Errors are logged, not raised."""
        try:
            # Import here to avoid circular at module load
            from utils.server_client import update_draft_status_remote
            draft = get_draft(draft_id)
            if not draft or not draft.get("server_draft_id"):
                return
            server_id = draft["server_draft_id"]
            kwargs: dict = {"status": status}
            if text is not None:
                kwargs["text"] = text
            await asyncio.to_thread(update_draft_status_remote, server_id, **kwargs)
            logger.info("Synced draft %d → server draft %d status=%s", draft_id, server_id, status)
        except Exception as exc:
            logger.warning("Server sync for draft %d failed (will retry): %s", draft_id, exc)

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    # ── Auth callback ─────────────────────────────────────────────────────────

    @app.get("/auth/callback")
    async def auth_callback(token: Optional[str] = None) -> Response:
        if not token:
            raise HTTPException(status_code=400, detail="Missing token parameter")
        # Structural JWT validation: must be 3 dot-separated base64url segments
        parts = token.split(".")
        if len(parts) != 3 or not all(parts):
            raise HTTPException(status_code=400, detail="Invalid token format")

        # Store JWT in the auth file (daemon uses this for API calls)
        try:
            from utils.server_client import _save_auth
            _save_auth({"access_token": token, "email": ""})
        except Exception as exc:
            logger.warning("Failed to save auth to server_client: %s", exc)

        # Also store in local SQLite settings so AC8 can query it
        try:
            from utils.crypto import encrypt_if_needed
            set_setting("jwt", encrypt_if_needed(token))
        except Exception as exc:
            logger.warning("Failed to save jwt to settings: %s", exc)
            set_setting("jwt", token)

        logger.info("Auth callback: JWT stored, redirecting to onboarding step 2")
        return RedirectResponse(url=f"{HOSTED_BASE_URL}/user/onboarding/step2", status_code=302)

    # ── Connect ───────────────────────────────────────────────────────────────

    @app.get("/connect")
    async def connect_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "user/connect.html",
            {
                "request": request,
                "platforms": CONNECTABLE_PLATFORMS,
                "platform_labels": PLATFORM_LABELS,
            },
        )

    @app.post("/connect/{platform}")
    async def connect_platform(platform: str, request: Request) -> HTMLResponse:
        platform = platform.lower()
        if platform not in CONNECTABLE_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Platform '{platform}' is not connectable")

        # Launch Playwright browser in a background thread so the HTTP response
        # is not blocked (the browser can take minutes for manual login).
        async def _launch() -> None:
            try:
                from login_setup import run_login
                await run_login(platform)
            except Exception as exc:
                logger.error("Platform login for %s failed: %s", platform, exc)

        asyncio.ensure_future(_launch())

        label = PLATFORM_LABELS.get(platform, platform.capitalize())
        return HTMLResponse(
            content=f"""
            <div class="rounded-lg bg-blue-900/40 border border-blue-500/30 p-4 text-blue-200 text-sm">
              <strong>{label}</strong> browser opened — log in manually, then close the browser window.
              The session will be saved automatically.
            </div>
            """,
            status_code=200,
        )

    # ── Keys ──────────────────────────────────────────────────────────────────

    @app.get("/keys")
    async def keys_page(request: Request) -> HTMLResponse:
        key_statuses = {k: bool(get_setting(k)) for k, _, _ in AI_KEY_FIELDS}
        return templates.TemplateResponse(
            "user/keys.html",
            {
                "request": request,
                "key_fields": AI_KEY_FIELDS,
                "key_statuses": key_statuses,
            },
        )

    @app.post("/keys")
    async def keys_save(request: Request) -> HTMLResponse:
        form = await request.form()
        saved = []
        for key, label, _ in AI_KEY_FIELDS:
            val = (form.get(key) or "").strip()
            if val:
                set_setting(key, val)
                saved.append(label)
        msg = f"Saved: {', '.join(saved)}" if saved else "No keys provided — nothing saved."

        # If the user arrived from the hosted onboarding flow, surface a CTA
        # to return and continue to step 4. Detected via ?from=onboarding
        # on the page load (referer query string preserved by browser).
        referer = request.headers.get("referer", "")
        from_onboarding = "from=onboarding" in referer

        return_cta = ""
        if saved and from_onboarding:
            return_cta = f"""
            <a href="{HOSTED_BASE_URL}/user/onboarding/step4"
               class="inline-block mt-3 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors">
              Return to onboarding &rarr;
            </a>
            """

        return HTMLResponse(
            content=f"""
            <div class="rounded-lg bg-green-900/40 border border-green-500/30 p-4 text-green-200 text-sm mb-4">
              {msg}
              {return_cta}
            </div>
            """,
        )

    @app.post("/keys/test")
    async def keys_test(request: Request) -> HTMLResponse:
        form = await request.form()
        key_name = (form.get("key_name") or "").strip()
        # HTMX submits the input under its own field name (e.g., gemini_api_key=...).
        # Fall back to "key_value" for direct curl/test invocations.
        key_value = (form.get(key_name) or form.get("key_value") or "").strip() if key_name else ""

        # If nothing typed, fall back to the saved (encrypted) value in the DB —
        # so the Test button works for "✓ Configured" providers without forcing
        # the user to re-type a key they've already saved.
        if key_name and not key_value:
            saved = get_setting(key_name)
            if saved:
                try:
                    from utils.crypto import decrypt_safe
                    key_value = decrypt_safe(saved) or ""
                except Exception:
                    key_value = ""

        if not key_name or not key_value:
            return HTMLResponse(
                content='<span class="text-red-400 text-sm">No key to test — type a key first.</span>'
            )

        ok = await asyncio.to_thread(_test_ai_key, key_name, key_value)
        if ok:
            return HTMLResponse(
                content='<span class="text-green-400 text-sm font-medium">✓ Key valid</span>'
            )
        return HTMLResponse(
            content='<span class="text-red-400 text-sm font-medium">✗ Key invalid or unreachable</span>'
        )

    # ── Drafts ────────────────────────────────────────────────────────────────

    @app.get("/drafts")
    async def drafts_all(request: Request) -> HTMLResponse:
        drafts = get_all_drafts()
        # Group by campaign_id
        grouped: dict[int, dict] = {}
        for d in drafts:
            cid = d.get("campaign_id") or 0
            if cid not in grouped:
                grouped[cid] = {
                    "campaign_id": cid,
                    "campaign_title": d.get("campaign_title") or f"Campaign #{cid}",
                    "drafts": [],
                }
            grouped[cid]["drafts"].append(d)
        return templates.TemplateResponse(
            "user/drafts.html",
            {
                "request": request,
                "grouped": list(grouped.values()),
                "campaign_id": None,
            },
        )

    @app.get("/drafts/{campaign_id}")
    async def drafts_for_campaign(campaign_id: int, request: Request) -> HTMLResponse:
        drafts = get_all_drafts(campaign_id=campaign_id)
        title = drafts[0].get("campaign_title") if drafts else f"Campaign #{campaign_id}"
        grouped = [{"campaign_id": campaign_id, "campaign_title": title, "drafts": drafts}]
        return templates.TemplateResponse(
            "user/drafts.html",
            {
                "request": request,
                "grouped": grouped,
                "campaign_id": campaign_id,
            },
        )

    @app.get("/drafts/{draft_id}/image")
    async def draft_image(draft_id: int) -> Response:
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        image_path = draft.get("image_path")
        if not image_path or not Path(image_path).is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        return FileResponse(image_path)

    # Draft actions — return partial HTML for HTMX swap

    @app.post("/drafts/{draft_id}/approve")
    async def draft_approve(draft_id: int, request: Request) -> HTMLResponse:
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        approve_draft(draft_id)
        _fire_and_forget(_sync_draft_to_server(draft_id, "approved"))
        draft = get_draft(draft_id)
        return _render_draft_card(request, templates, draft)

    @app.post("/drafts/{draft_id}/reject")
    async def draft_reject(draft_id: int, request: Request) -> HTMLResponse:
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        reject_draft(draft_id)
        _fire_and_forget(_sync_draft_to_server(draft_id, "rejected"))
        draft = get_draft(draft_id)
        return _render_draft_card(request, templates, draft)

    @app.post("/drafts/{draft_id}/restore")
    async def draft_restore(draft_id: int, request: Request) -> HTMLResponse:
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        # restore: set approved=0 (pending)
        _set_draft_approved_raw(draft_id, 0)
        _fire_and_forget(_sync_draft_to_server(draft_id, "pending"))
        draft = get_draft(draft_id)
        return _render_draft_card(request, templates, draft)

    @app.post("/drafts/{draft_id}/unapprove")
    async def draft_unapprove(draft_id: int, request: Request) -> HTMLResponse:
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        _set_draft_approved_raw(draft_id, 0)
        _fire_and_forget(_sync_draft_to_server(draft_id, "pending"))
        draft = get_draft(draft_id)
        return _render_draft_card(request, templates, draft)

    @app.post("/drafts/{draft_id}/edit")
    async def draft_edit(draft_id: int, request: Request) -> HTMLResponse:
        form = await request.form()
        new_text = (form.get("text") or "").strip()
        draft = get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if new_text:
            update_draft_text(draft_id, new_text)
            _fire_and_forget(_sync_draft_to_server(draft_id, "pending", text=new_text))
        draft = get_draft(draft_id)
        return _render_draft_card(request, templates, draft)

    return app


# ── Helpers outside the factory (importable by tests) ─────────────────────────


def _set_draft_approved_raw(draft_id: int, value: int) -> None:
    """Set agent_draft.approved to an arbitrary integer (0, 1, or -1)."""
    from utils.local_db import _get_db
    conn = _get_db()
    conn.execute("UPDATE agent_draft SET approved = ? WHERE id = ?", (value, draft_id))
    conn.commit()
    conn.close()


def _render_draft_card(request: Request, templates: Jinja2Templates, draft: dict) -> HTMLResponse:
    """Render a single draft card partial for HTMX swap."""
    def display_status(d: dict) -> str:
        if d.get("posted"):
            return "posted"
        approved = d.get("approved", 0)
        if approved == 1:
            return "approved"
        if approved == -1:
            return "rejected"
        return "pending"

    status = display_status(draft)
    return templates.TemplateResponse(
        "user/draft_card.html",
        {"request": request, "draft": draft, "status": status},
    )


def _test_ai_key(key_name: str, key_value: str) -> bool:
    """Lightweight key validity test. Returns True if usable."""
    try:
        if key_name == "gemini_api_key":
            import httpx
            resp = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key_value}",
                timeout=10,
            )
            return resp.status_code == 200
        if key_name == "groq_api_key":
            import httpx
            resp = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key_value}"},
                timeout=10,
            )
            return resp.status_code == 200
        if key_name == "mistral_api_key":
            import httpx
            resp = httpx.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {key_value}"},
                timeout=10,
            )
            return resp.status_code == 200
        # For Cloudflare / Together — just check non-empty
        return bool(key_value)
    except Exception:
        return False
