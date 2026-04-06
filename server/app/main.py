from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.database import init_tables
from app.routers import auth, campaigns, users, metrics, admin, invitations
from app.routers.admin import router as admin_pages_router
from app.routers.company import router as company_pages_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Skip init_tables on Vercel (tables managed via Supabase migrations)
    # Only run for local SQLite development
    import os
    if not os.environ.get("VERCEL"):
        try:
            await init_tables()
        except Exception:
            pass
    yield


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    lifespan=lifespan,
    title="Amplifier API",
    description="Social media campaign distribution platform",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF protection for HTML form routes (double-submit cookie pattern)
from app.core.csrf import CSRFMiddleware
app.add_middleware(CSRFMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(campaigns.router, prefix="/api", tags=["campaigns"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(admin_pages_router, prefix="/admin", tags=["admin-pages"])
app.include_router(company_pages_router, prefix="/company", tags=["company-pages"])
app.include_router(invitations.router, prefix="/api/campaigns", tags=["invitations"])


APP_VERSION = "0.1.0"


from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    tb = traceback.format_exc()
    import logging
    logging.getLogger("app").error("Unhandled: %s\n%s", exc, tb)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "traceback": tb},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}





@app.get("/api/version")
async def version():
    """Version endpoint for auto-update checks."""
    return {
        "version": APP_VERSION,
        "download_url": "",  # Set when installer is hosted
        "changelog": "Initial release",
    }
