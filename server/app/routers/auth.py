from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.models.company import Company
from app.schemas.auth import UserRegister, CompanyRegister, LoginRequest, TokenResponse

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register_user(data: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login_user(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.status == "banned":
        raise HTTPException(status_code=403, detail="Account banned")

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return TokenResponse(access_token=token)


@router.post("/company/register", response_model=TokenResponse)
async def register_company(data: CompanyRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    company = Company(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(company)
    await db.flush()

    token = create_access_token({"sub": str(company.id), "type": "company"})
    return TokenResponse(access_token=token)


@router.post("/company/login", response_model=TokenResponse)
async def login_company(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.email == data.email))
    company = result.scalar_one_or_none()
    if not company or not verify_password(data.password, company.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(company.id), "type": "company"})
    return TokenResponse(access_token=token)
