"""Shared-secret API key auth. Every non-/health route requires X-API-Key."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from server.settings import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not x_api_key or x_api_key != settings.platform_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
