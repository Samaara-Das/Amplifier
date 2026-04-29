from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database (SQLite for dev/testing, PostgreSQL for production)
    # On Vercel serverless, SQLite uses /tmp/ (ephemeral — use PostgreSQL for production)
    database_url: str = "sqlite+aiosqlite:///./amplifier.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # Platform
    platform_cut_percent: float = 20.0
    min_payout_threshold: float = 10.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    server_url: str = "http://localhost:8000"

    # Stripe (optional — test mode)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Supabase Storage (for campaign asset uploads)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Admin
    admin_password: str = "admin"

    # AI providers (also read directly via os.environ in services)
    gemini_api_key: str = ""
    mistral_api_key: str = ""
    groq_api_key: str = ""

    # Encryption (also read directly via os.environ in app/utils/crypto.py)
    encryption_key: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # don't fail on unknown env vars
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
