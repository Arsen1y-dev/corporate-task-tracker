from typing import Protocol

from auth_service.domain.models import RefreshToken, User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: int) -> User | None:
        ...

    async def get_by_username(self, username: str) -> User | None:
        ...

    async def get_by_email(self, email: str) -> User | None:
        ...

    async def create(self, user: User) -> User:
        ...

    async def update(self, user: User) -> User:
        ...


class RefreshTokenRepository(Protocol):
    async def create(self, token: RefreshToken) -> RefreshToken:
        ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        ...

    async def revoke(self, token_hash: str) -> None:
        ...
