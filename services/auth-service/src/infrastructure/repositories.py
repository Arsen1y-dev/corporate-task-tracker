from auth_service.domain.models import RefreshToken, User
from auth_service.infrastructure.models import RefreshTokenModel, UserModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user_model = result.scalar_one_or_none()
        return user_model.to_domain() if user_model else None

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.username == username))
        user_model = result.scalar_one_or_none()
        return user_model.to_domain() if user_model else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(UserModel).where(UserModel.email == email))
        user_model = result.scalar_one_or_none()
        return user_model.to_domain() if user_model else None

    async def create(self, user: User) -> User:
        user_model = UserModel(
            username=user.username,
            email=user.email,
            hashed_password=user.hashed_password,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            is_active=user.is_active,
            max_projects=user.max_projects,
        )
        self.session.add(user_model)
        await self.session.commit()
        await self.session.refresh(user_model)
        return user_model.to_domain()


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        token_model = RefreshTokenModel(
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked=token.revoked,
        )
        self.session.add(token_model)
        await self.session.commit()
        await self.session.refresh(token_model)
        return RefreshToken(
            id=token_model.id,
            user_id=token_model.user_id,
            token_hash=token_model.token_hash,
            expires_at=token_model.expires_at,
            revoked=token_model.revoked,
            created_at=token_model.created_at,
        )

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        token_model = result.scalar_one_or_none()
        if not token_model:
            return None
        return RefreshToken(
            id=token_model.id,
            user_id=token_model.user_id,
            token_hash=token_model.token_hash,
            expires_at=token_model.expires_at,
            revoked=token_model.revoked,
            created_at=token_model.created_at,
        )

    async def revoke(self, token_hash: str) -> None:
        await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .values(revoked=True)
        )
        await self.session.commit()
