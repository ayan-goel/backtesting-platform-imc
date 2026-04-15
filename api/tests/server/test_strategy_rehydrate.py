"""Tests for `ensure_strategy_on_disk` rehydration.

Heroku/Railway-style deploys have an ephemeral filesystem — strategy
files uploaded in one dyno lifecycle disappear on the next restart while
the Mongo doc persists. We fix that by caching the raw source bytes on
the strategy doc at upload time and rehydrating them on demand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from engine.errors import StrategyLoadError
from server.services import strategy_service
from server.settings import get_settings

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""


@pytest.mark.asyncio
async def test_upload_persists_source_bytes_in_doc(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()
    doc = await strategy_service.upload_strategy(
        filename="noop.py",
        content=MINIMAL_TRADER,
        settings=settings,
        db=db,
    )
    # The bytes should land in Mongo for later rehydration.
    stored = await db["strategies"].find_one({"_id": doc["_id"]})
    assert stored is not None
    assert stored["source_bytes"] == MINIMAL_TRADER


@pytest.mark.asyncio
async def test_rehydrate_restores_file_when_wiped(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()
    doc = await strategy_service.upload_strategy(
        filename="noop.py",
        content=MINIMAL_TRADER,
        settings=settings,
        db=db,
    )
    strategy_path = strategy_service.resolve_strategy_path(settings, doc)
    assert strategy_path.is_file()

    # Simulate an ephemeral-fs wipe: delete the file on disk. The Mongo doc
    # (with source_bytes) persists.
    strategy_path.unlink()
    assert not strategy_path.is_file()

    doc_from_db = await db["strategies"].find_one({"_id": doc["_id"]})
    assert doc_from_db is not None

    rehydrated = strategy_service.ensure_strategy_on_disk(settings, doc_from_db)
    assert rehydrated == strategy_path
    assert strategy_path.is_file()
    assert strategy_path.read_bytes() == MINIMAL_TRADER


def test_rehydrate_raises_for_doc_without_source_bytes(
    tmp_path: Path, test_app: FastAPI
) -> None:
    # Legacy docs uploaded before this change have no `source_bytes` field.
    # ensure_strategy_on_disk should raise a clear actionable error.
    settings = get_settings()
    ghost_doc: dict[str, Any] = {
        "_id": "ghost-12345678",
        "filename": "ghost.py",
        "stem": "ghost",
        "sha256": "sha256:deadbeef",
        "uploaded_at": "2026-01-01T00:00:00Z",
        "size_bytes": 10,
        "storage_subpath": "strategies/ghost-12345678.py",
    }
    with pytest.raises(StrategyLoadError, match="Re-upload"):
        strategy_service.ensure_strategy_on_disk(settings, ghost_doc)


@pytest.mark.asyncio
async def test_mc_create_rehydrates_when_file_missing(
    test_app: FastAPI,
) -> None:
    """End-to-end: upload a strategy, wipe its file, submit an MC — it should
    succeed because mc_service rehydrates from Mongo before queueing.
    """
    from server.schemas.mc import McCreateRequest
    from server.services import mc_service
    from tests.server._mc_csv_fixtures import dataset_doc_for, write_synthetic_csvs

    db = test_app.state.mongo_db
    settings = get_settings()

    # Seed a dataset
    datasets_dir = settings.storage_root / "data"
    prices, trades, products = write_synthetic_csvs(
        datasets_dir=datasets_dir, round_num=0, day=0
    )
    await db["datasets"].insert_one(
        dataset_doc_for(
            round_num=0,
            day=0,
            prices_path=prices,
            trades_path=trades,
            products=products,
            num_timestamps=80,
        )
    )

    # Upload a strategy (this persists source_bytes in Mongo).
    strat_doc = await strategy_service.upload_strategy(
        filename="noop.py",
        content=MINIMAL_TRADER,
        settings=settings,
        db=db,
    )
    strategy_path = strategy_service.resolve_strategy_path(settings, strat_doc)

    # Ephemeral-fs wipe.
    strategy_path.unlink()
    assert not strategy_path.is_file()

    # MC submit should succeed (file gets rehydrated in create_mc_simulation).
    mc_doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=strat_doc["_id"], round=0, day=0, n_paths=1
        ),
        settings=settings,
        db=db,
    )
    assert mc_doc["status"] == "queued"
    assert strategy_path.is_file(), "file should have been rehydrated"
