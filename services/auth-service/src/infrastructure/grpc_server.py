import logging

import grpc
from auth_service.infrastructure.database import AsyncSessionLocal
from auth_service.infrastructure.repositories import SqlAlchemyUserRepository
from auth_service.proto import auth_pb2, auth_pb2_grpc

logger = logging.getLogger(__name__)


class AuthServiceServicer(auth_pb2_grpc.AuthServiceServicer):
    async def CheckUserExists(
        self,
        request: auth_pb2.UserCheckRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UserCheckResponse:
        async with AsyncSessionLocal() as session:
            user_repo = SqlAlchemyUserRepository(session)
            user = await user_repo.get_by_id(request.user_id)
            if not user or not user.is_active:
                return auth_pb2.UserCheckResponse(
                    exists=False,
                    user_id=request.user_id,
                    username="",
                    email="",
                    role="",
                )
            return auth_pb2.UserCheckResponse(
                exists=True,
                user_id=user.id,
                username=user.username,
                email=user.email,
                role=user.role.value if hasattr(user.role, "value") else str(user.role),
            )

    async def CheckProjectQuota(
        self,
        request: auth_pb2.QuotaCheckRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.QuotaCheckResponse:
        async with AsyncSessionLocal() as session:
            user_repo = SqlAlchemyUserRepository(session)
            user = await user_repo.get_by_id(request.user_id)
            if not user:
                return auth_pb2.QuotaCheckResponse(
                    allowed=False,
                    max_projects=0,
                    reason=f"User ID {request.user_id} does not exist",
                )

            if request.current_project_count >= user.max_projects:
                return auth_pb2.QuotaCheckResponse(
                    allowed=False,
                    max_projects=user.max_projects,
                    reason=(
                        f"Quota limit reached. User has {request.current_project_count} "
                        f"active projects (max: {user.max_projects})"
                    ),
                )

            return auth_pb2.QuotaCheckResponse(
                allowed=True,
                max_projects=user.max_projects,
                reason="Quota check passed successfully",
            )


async def start_grpc_server(host: str = "0.0.0.0", port: int = 50051) -> grpc.aio.Server:
    server = grpc.aio.server()
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServiceServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    logger.info(f"gRPC AuthService server running on {host}:{port}")
    return server
