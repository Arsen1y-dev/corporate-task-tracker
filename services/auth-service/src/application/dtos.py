from datetime import datetime

from auth_service.domain.models import Role
from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=72)
    role: Role = Role.DEVELOPER
    max_projects: int = 5


class UserLoginRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: Role
    is_active: bool
    max_projects: int
    created_at: datetime | None = None
