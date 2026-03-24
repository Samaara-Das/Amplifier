from datetime import datetime, timedelta, timezone

import hashlib
import secrets
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()

security_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 (pure Python, no C extensions needed)."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000)
    return f"pbkdf2:sha256:260000${salt}${h.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash. Supports both PBKDF2 and legacy bcrypt."""
    if hashed.startswith("pbkdf2:"):
        # New PBKDF2 format
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        salt = parts[1]
        expected = parts[2]
        h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260000)
        return secrets.compare_digest(h.hex(), expected)
    elif hashed.startswith("$2"):
        # Legacy bcrypt hash — try passlib, fall back to bcrypt
        try:
            from passlib.context import CryptContext
            ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return ctx.verify(plain, hashed)
        except Exception:
            try:
                import bcrypt
                return bcrypt.checkpw(plain.encode(), hashed.encode())
            except Exception:
                return False
    return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency that extracts and validates the current user from JWT."""
    from app.models.user import User

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "user":
        raise HTTPException(status_code=403, detail="Not a user token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status == "banned":
        raise HTTPException(status_code=403, detail="Account banned")
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")

    return user


async def get_current_company(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency that extracts and validates the current company from JWT."""
    from app.models.company import Company

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "company":
        raise HTTPException(status_code=403, detail="Not a company token")

    company_id = payload.get("sub")
    if not company_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(Company).where(Company.id == int(company_id)))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company
