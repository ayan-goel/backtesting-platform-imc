"""Shared API fixtures. Uses mongomock-motor instead of real Mongo."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

REPO_ROOT = Path(__file__).resolve().parents[4]
TUTORIAL_DATA = REPO_ROOT / "tutorial-round-data"

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URL", "mongodb://mock")
    monkeypatch.setenv("MONGO_DB", "test")
    monkeypatch.setenv("PLATFORM_API_KEY", "test-key")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))

    # Bust the lru_cache so settings re-read env.
    from server import settings as settings_mod

    settings_mod.get_settings.cache_clear()


@pytest_asyncio.fixture
async def test_app() -> AsyncIterator[FastAPI]:
    """Construct a fresh FastAPI app wired to an in-memory mongomock client."""
    from server.main import app
    from server.storage.registry import ensure_indexes

    client = AsyncMongoMockClient()
    db = client["test"]
    app.state.mongo_client = client
    app.state.mongo_db = db
    await ensure_indexes(db)
    yield app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": os.environ["PLATFORM_API_KEY"]}


@pytest_asyncio.fixture
async def seeded_dataset(test_app: FastAPI, tmp_path: Path) -> dict:
    """Seed the tutorial round=0 day=-2 dataset into Mongo + storage so run tests can
    post against it without re-running an upload through the HTTP layer.
    """
    datasets_dir = tmp_path / "data"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    prices_src = TUTORIAL_DATA / "prices_round_0_day_-2.csv"
    trades_src = TUTORIAL_DATA / "trades_round_0_day_-2.csv"
    prices_dst = datasets_dir / "prices_round_0_day_-2.csv"
    trades_dst = datasets_dir / "trades_round_0_day_-2.csv"
    shutil.copy(prices_src, prices_dst)
    shutil.copy(trades_src, trades_dst)

    doc = {
        "_id": "r0d-2",
        "round": 0,
        "day": -2,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "products": ["EMERALDS", "TOMATOES"],
        "num_timestamps": 10000,
        "prices_filename": prices_dst.name,
        "trades_filename": trades_dst.name,
        "prices_bytes": prices_dst.stat().st_size,
        "trades_bytes": trades_dst.stat().st_size,
    }
    await test_app.state.mongo_db["datasets"].insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def seeded_dataset_day_neg1(test_app: FastAPI, tmp_path: Path) -> dict:
    """Second tutorial dataset (round=0, day=-1) for multi-task batch tests."""
    datasets_dir = tmp_path / "data"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    prices_src = TUTORIAL_DATA / "prices_round_0_day_-1.csv"
    trades_src = TUTORIAL_DATA / "trades_round_0_day_-1.csv"
    prices_dst = datasets_dir / "prices_round_0_day_-1.csv"
    trades_dst = datasets_dir / "trades_round_0_day_-1.csv"
    shutil.copy(prices_src, prices_dst)
    shutil.copy(trades_src, trades_dst)

    doc = {
        "_id": "r0d-1",
        "round": 0,
        "day": -1,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "products": ["EMERALDS", "TOMATOES"],
        "num_timestamps": 10000,
        "prices_filename": prices_dst.name,
        "trades_filename": trades_dst.name,
        "prices_bytes": prices_dst.stat().st_size,
        "trades_bytes": trades_dst.stat().st_size,
    }
    await test_app.state.mongo_db["datasets"].insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def seeded_strategy(test_app: FastAPI, tmp_path: Path) -> dict:
    """Seed a synthetic no-op strategy into storage/strategies."""
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)

    content = MINIMAL_TRADER
    sha256 = hashlib.sha256(content).hexdigest()
    strategy_id = f"noop-{sha256[:8]}"
    storage_path = strategies_dir / f"{strategy_id}.py"
    storage_path.write_bytes(content)

    doc = {
        "_id": strategy_id,
        "filename": "noop.py",
        "stem": "noop",
        "sha256": f"sha256:{sha256}",
        "uploaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": len(content),
        "storage_subpath": f"strategies/{storage_path.name}",
    }
    await test_app.state.mongo_db["strategies"].insert_one(doc)
    return doc
