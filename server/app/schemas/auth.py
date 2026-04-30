from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    accept_tos: bool = Field(False, description="Must be true; user must accept the ToS to register")


class CompanyRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    accept_tos: bool = Field(False, description="Must be true; company must accept the ToS to register")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: str
    current_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
