from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.models.company import Company
from app.schemas.auth import UserRegister, CompanyRegister, LoginRequest, PasswordResetRequest, TokenResponse

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register_user(request: Request, data: UserRegister, db: AsyncSession = Depends(get_db)):
    if not data.accept_tos:
        raise HTTPException(status_code=400, detail="You must accept the Terms of Service and Privacy Policy to register")

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        tos_accepted_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_user(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.status == "banned":
        raise HTTPException(status_code=403, detail="Account banned")

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return TokenResponse(access_token=token)


@router.post("/reset-password")
@limiter.limit("3/minute")
async def reset_password(request: Request, data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using current password as verification."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or current password")

    user.password_hash = hash_password(data.new_password)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return {"message": "Password reset successfully", "access_token": token}


@router.post("/company/reset-password")
@limiter.limit("3/minute")
async def reset_company_password(request: Request, data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Reset company password using current password as verification."""
    result = await db.execute(select(Company).where(Company.email == data.email))
    company = result.scalar_one_or_none()
    if not company or not verify_password(data.current_password, company.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or current password")

    company.password_hash = hash_password(data.new_password)
    await db.flush()

    token = create_access_token({"sub": str(company.id), "type": "company"})
    return {"message": "Password reset successfully", "access_token": token}


@router.post("/company/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register_company(request: Request, data: CompanyRegister, db: AsyncSession = Depends(get_db)):
    if not data.accept_tos:
        raise HTTPException(status_code=400, detail="You must accept the Terms of Service and Privacy Policy to register")

    result = await db.execute(select(Company).where(Company.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    company = Company(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        tos_accepted_at=datetime.now(timezone.utc),
    )
    db.add(company)
    await db.flush()

    token = create_access_token({"sub": str(company.id), "type": "company"})
    return TokenResponse(access_token=token)


@router.post("/company/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_company(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.email == data.email))
    company = result.scalar_one_or_none()
    if not company or not verify_password(data.password, company.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(company.id), "type": "company"})
    return TokenResponse(access_token=token)
