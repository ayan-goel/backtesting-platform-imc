"""Shared httpx client used by the API-facing CLI commands.

Reads `PLATFORM_API_URL` (default http://localhost:8000) and
`PLATFORM_API_KEY` (required) from env. Errors loudly and early if the
key is unset so users see a clear message before any network call.
"""

from __future__ import annotations

import os

import httpx


class MissingApiKeyError(RuntimeError):
    """Raised when PLATFORM_API_KEY is not set in the environment."""


def build_client(timeout: float = 30.0) -> httpx.Client:
    """Return a preconfigured httpx.Client that talks to the platform API."""
    base_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")
    api_key = os.environ.get("PLATFORM_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "PLATFORM_API_KEY is not set. Export it before running this command "
            "(same value your server uses). See platform/api/.env.example."
        )
    return httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )
