from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.database import init_tables
from app.routers import auth, campaigns, users, metrics, admin, invitations
from app.routers.admin import router as admin_pages_router
from app.routers.company import router as company_pages_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (idempotent — safe for both SQLite and PostgreSQL)
    try:
        await init_tables()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("init_tables failed (tables may already exist): %s", e)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Amplifier API",
    description="Social media campaign distribution platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(campaigns.router, prefix="/api", tags=["campaigns"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(admin_pages_router, prefix="/admin", tags=["admin-pages"])
app.include_router(company_pages_router, prefix="/company", tags=["company-pages"])
app.include_router(invitations.router, prefix="/api/campaigns", tags=["invitations"])


APP_VERSION = "0.1.0"


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    return {"error": str(exc), "traceback": traceback.format_exc()}


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
