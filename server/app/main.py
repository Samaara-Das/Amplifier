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
    """Temporary: test DB connectivity and run admin overview queries."""
    from app.core.database import async_session
    from sqlalchemy import text
    import traceback
    results = {}
    async with async_session() as db:
        queries = {
            "tables": "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
            "user_count": "SELECT count(*) FROM users",
            "campaign_count": "SELECT count(*) FROM campaigns",
            "post_count": "SELECT count(*) FROM posts",
            "payout_sum": "SELECT coalesce(sum(amount), 0) FROM payouts",
            "budget_spent": "SELECT coalesce(sum(budget_total - budget_remaining), 0) FROM campaigns",
            "recent_assignments": "SELECT ca.id, u.email, c.title, ca.status, ca.assigned_at FROM campaign_assignments ca JOIN users u ON ca.user_id = u.id JOIN campaigns c ON ca.campaign_id = c.id ORDER BY ca.assigned_at DESC LIMIT 5",
        }
        for name, sql in queries.items():
            try:
                r = await db.execute(text(sql))
                rows = r.fetchall()
                results[name] = [list(row) for row in rows]
            except Exception as e:
                results[name] = f"ERROR: {e}\n{traceback.format_exc()}"
    return results


@app.get("/api/version")
async def version():
    """Version endpoint for auto-update checks."""
    return {
        "version": APP_VERSION,
        "download_url": "",  # Set when installer is hosted
        "changelog": "Initial release",
    }
