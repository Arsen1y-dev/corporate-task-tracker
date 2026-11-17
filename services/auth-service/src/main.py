import logging
from contextlib import asynccontextmanager

from auth_service.config import settings
from auth_service.infrastructure.database import init_db
from auth_service.infrastructure.grpc_server import start_grpc_server
from auth_service.infrastructure.redis_cache import blacklist_service
from auth_service.presentation.api import router as auth_router
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Auth Service...")
    await init_db()
    grpc_server = await start_grpc_server(port=settings.GRPC_PORT)
    yield
    logger.info("Shutting down Auth Service...")
    await grpc_server.stop(grace=1.0)
    await blacklist_service.close()


app = FastAPI(
    title="Corporate Task Tracker - Auth Service",
    version="1.0.0",
    root_path=settings.ROOT_PATH,
    lifespan=lifespan,
)

app.include_router(auth_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "auth-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("auth_service.main:app", host="0.0.0.0", port=settings.HTTP_PORT, reload=False)
