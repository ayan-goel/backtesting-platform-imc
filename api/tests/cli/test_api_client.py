"""L1 tests: shared http client helper for the CLI."""

from __future__ import annotations

import pytest

from cli.api_client import MissingApiKeyError, build_client


def test_build_client_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_API_URL", "https://example.test")
    monkeypatch.setenv("PLATFORM_API_KEY", "abc")
    client = build_client()
    try:
        assert str(client.base_url).rstrip("/") == "https://example.test"
        assert client.headers["X-API-Key"] == "abc"
    finally:
        client.close()


def test_build_client_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="PLATFORM_API_KEY"):
        build_client()


def test_build_client_default_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLATFORM_API_URL", raising=False)
    monkeypatch.setenv("PLATFORM_API_KEY", "abc")
    client = build_client()
    try:
        assert "localhost" in str(client.base_url)
    finally:
        client.close()
