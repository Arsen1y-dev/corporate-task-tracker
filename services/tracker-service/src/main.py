import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from tracker_service.application.outbox import outbox_publisher_service
from tracker_service.config import settings
from tracker_service.infrastructure.database import init_db
from tracker_service.infrastructure.grpc_client import auth_grpc_client
from tracker_service.infrastructure.rabbitmq import rabbitmq_publisher
from tracker_service.infrastructure.redis_cache import cache_service
from tracker_service.presentation.api import router as tracker_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracker-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Tracker Service...")
    await init_db()
    await rabbitmq_publisher.connect()
    outbox_publisher_service.start()
    yield
    logger.info("Shutting down Tracker Service...")
    await outbox_publisher_service.stop()
    await rabbitmq_publisher.close()
    await cache_service.close()
    await auth_grpc_client.close()


app = FastAPI(
    title="Corporate Task Tracker - Tracker Service",
    version="1.0.0",
    root_path=settings.ROOT_PATH,
    lifespan=lifespan,
)

app.include_router(tracker_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "tracker-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tracker_service.main:app", host="0.0.0.0", port=settings.HTTP_PORT, reload=False)
