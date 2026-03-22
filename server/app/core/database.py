import os
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()

# On Vercel serverless, use /tmp/ for SQLite (only writable directory)
_db_url = settings.database_url
if _db_url.startswith("sqlite") and os.environ.get("VERCEL"):
    _db_url = "sqlite+aiosqlite:////tmp/amplifier.db"

# Engine kwargs vary by backend
_engine_kwargs = {"echo": settings.debug}
if _db_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = StaticPool
elif _db_url.startswith("postgresql"):
    # Supabase (and most cloud PostgreSQL) requires SSL
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {
        "ssl": _ssl_ctx,
        # Required for pgbouncer (Supabase transaction pooler on port 6543)
        "prepared_statement_cache_size": 0,
    }
    # Serverless: keep pool small, pre-ping to detect stale connections
    _engine_kwargs["pool_size"] = 2
    _engine_kwargs["max_overflow"] = 3
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(_db_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_tables():
    """Create all tables (for SQLite dev/testing — use Alembic for PostgreSQL)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
