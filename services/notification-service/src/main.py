import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from notification_service.config import settings
from notification_service.infrastructure.database import init_db
from notification_service.infrastructure.rabbitmq_consumer import rabbitmq_consumer
from notification_service.presentation.api import router as notification_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Notification Service...")
    await init_db()
    rabbitmq_consumer.start()
    yield
    logger.info("Shutting down Notification Service...")
    await rabbitmq_consumer.stop()


app = FastAPI(
    title="Corporate Task Tracker - Notification Service",
    version="1.0.0",
    root_path=settings.ROOT_PATH,
    lifespan=lifespan,
)

app.include_router(notification_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "notification-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("notification_service.main:app", host="0.0.0.0", port=settings.HTTP_PORT, reload=False)
