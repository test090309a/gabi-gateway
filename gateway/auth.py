"""Bearer token authentication for HTTP endpoints."""
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from gateway.config import config

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(authorization: str = Depends(api_key_header)) -> str:
    """Verify the Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]  # Remove "Bearer " prefix
    expected_key = config.get("api_key")

    if not expected_key or token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
