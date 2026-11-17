import logging

import grpc
from tracker_service.config import settings
from tracker_service.proto import auth_pb2, auth_pb2_grpc

logger = logging.getLogger(__name__)


class AuthGrpcClient:
    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or settings.AUTH_GRPC_HOST
        self.port = port or settings.AUTH_GRPC_PORT
        self._channel: grpc.aio.Channel | None = None

    def _get_channel(self) -> grpc.aio.Channel:
        if self._channel is None:
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(target)
        return self._channel

    async def check_user_exists(self, user_id: int) -> tuple[bool, dict]:
        channel = self._get_channel()
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        req = auth_pb2.UserCheckRequest(user_id=user_id)
        try:
            response: auth_pb2.UserCheckResponse = await stub.CheckUserExists(
                req, timeout=3.0
            )
            return response.exists, {
                "user_id": response.user_id,
                "username": response.username,
                "email": response.email,
                "role": response.role,
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC call check_user_exists({user_id}) failed: {e}")
            return False, {"error": str(e)}

    async def check_project_quota(
        self, user_id: int, current_project_count: int
    ) -> tuple[bool, str, int]:
        channel = self._get_channel()
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        req = auth_pb2.QuotaCheckRequest(
            user_id=user_id, current_project_count=current_project_count
        )
        try:
            response: auth_pb2.QuotaCheckResponse = await stub.CheckProjectQuota(
                req, timeout=3.0
            )
            return response.allowed, response.reason, response.max_projects
        except grpc.RpcError as e:
            logger.error(f"gRPC call check_project_quota({user_id}) failed: {e}")
            return False, f"gRPC error: {e}", 0

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()


auth_grpc_client = AuthGrpcClient()
