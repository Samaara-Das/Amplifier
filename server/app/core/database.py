import os
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

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
    # Supabase requires SSL
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _engine_kwargs["connect_args"] = {"ssl": _ssl_ctx}
    # NullPool is recommended for serverless — no persistent connections
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(_db_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_tables():
    """Create all tables (idempotent — safe for both SQLite and PostgreSQL)."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        # Log but don't crash the app — tables may already exist
        import logging
        logging.getLogger(__name__).warning(f"init_tables failed: {e}")


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
