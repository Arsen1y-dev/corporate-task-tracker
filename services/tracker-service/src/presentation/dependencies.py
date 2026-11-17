import jwt
from fastapi import Header, HTTPException, status
from tracker_service.config import settings


async def get_current_user(
    authorization: str | None = Header(None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload.get("role", "developer"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature or payload",
        )
