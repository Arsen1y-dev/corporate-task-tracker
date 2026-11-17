import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/auth_db",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-task-tracker-token-2026")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", "50051"))
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8001"))
    ROOT_PATH: str = os.getenv("ROOT_PATH", "")


settings = Settings()
