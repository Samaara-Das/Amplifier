from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.database import init_tables
from app.routers import auth, campaigns, users, metrics, admin, company_dashboard, admin_pages, company_pages

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (idempotent — safe for both SQLite and PostgreSQL)
    await init_tables()
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
app.include_router(company_dashboard.router, prefix="/api", tags=["company-dashboard"])
app.include_router(admin_pages.router, prefix="/admin", tags=["admin-pages"])
app.include_router(company_pages.router, prefix="/company", tags=["company-pages"])


APP_VERSION = "0.1.0"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug/db")
async def debug_db():
    """Temporary debug endpoint — test database connection."""
    import os
    from app.core.database import engine
    info = {"database_url_set": bool(os.environ.get("DATABASE_URL")), "engine_url": str(engine.url).split("@")[-1]}
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            info["connection"] = "ok"
            info["result"] = result.scalar()
    except Exception as e:
        info["connection"] = "failed"
        info["error"] = f"{type(e).__name__}: {e}"
    return info


@app.get("/api/version")
async def version():
    """Version endpoint for auto-update checks."""
    return {
        "version": APP_VERSION,
        "download_url": "",  # Set when installer is hosted
        "changelog": "Initial release",
    }
