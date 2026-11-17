import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/notification_db",
    )
    RABBITMQ_URL: str = os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"
    )
    RABBITMQ_EXCHANGE: str = "tracker.events"
    RABBITMQ_QUEUE: str = "notification.queue"
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-task-tracker-token-2026")
    JWT_ALGORITHM: str = "HS256"
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8003"))
    ROOT_PATH: str = os.getenv("ROOT_PATH", "")


settings = Settings()
