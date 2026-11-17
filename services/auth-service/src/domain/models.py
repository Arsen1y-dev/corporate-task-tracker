from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"
    GUEST = "guest"


@dataclass
class User:
    id: int | None
    username: str
    email: str
    hashed_password: str
    role: Role = Role.DEVELOPER
    is_active: bool = True
    max_projects: int = 5
    created_at: datetime | None = None


@dataclass
class RefreshToken:
    id: int | None
    user_id: int
    token_hash: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime | None = None
