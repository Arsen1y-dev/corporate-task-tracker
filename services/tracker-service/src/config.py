import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/tracker_db",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/1")
    RABBITMQ_URL: str = os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"
    )
    RABBITMQ_EXCHANGE: str = "tracker.events"
    AUTH_GRPC_HOST: str = os.getenv("AUTH_GRPC_HOST", "auth-service")
    AUTH_GRPC_PORT: int = int(os.getenv("AUTH_GRPC_PORT", "50051"))
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-task-tracker-token-2026")
    JWT_ALGORITHM: str = "HS256"
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8002"))
    ROOT_PATH: str = os.getenv("ROOT_PATH", "")
    OUTBOX_POLL_INTERVAL_SECONDS: float = float(
        os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "2.0")
    )


settings = Settings()
