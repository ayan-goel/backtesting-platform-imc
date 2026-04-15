"""D2 tests: registry count helpers for delete previews."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from server.storage import registry


async def _seed(db: Any) -> None:
    # Two runs for strategy-a, one run for strategy-b.
    await db[registry.RUNS_COLLECTION].insert_many(
        [
            {"_id": "r1", "strategy_id": "strat-a", "round": 0, "day": -2},
            {"_id": "r2", "strategy_id": "strat-a", "round": 0, "day": -1},
            {"_id": "r3", "strategy_id": "strat-b", "round": 0, "day": -2},
        ]
    )
    # Two batches for strategy-a, one of which has a task at (0, -2) and (0, -1).
    await db[registry.BATCHES_COLLECTION].insert_many(
        [
            {
                "_id": "b1",
                "strategy_id": "strat-a",
                "tasks": [
                    {"round": 0, "day": -2, "status": "succeeded"},
                    {"round": 0, "day": -1, "status": "succeeded"},
                ],
            },
            {
                "_id": "b2",
                "strategy_id": "strat-a",
                "tasks": [{"round": 0, "day": -2, "status": "succeeded"}],
            },
            {
                "_id": "b3",
                "strategy_id": "strat-b",
                "tasks": [{"round": 1, "day": 0, "status": "succeeded"}],
            },
        ]
    )
    # One study for strategy-a at (0, -2), one for strategy-b at (0, -2).
    await db[registry.STUDIES_COLLECTION].insert_many(
        [
            {"_id": "s1", "strategy_id": "strat-a", "round": 0, "day": -2},
            {"_id": "s2", "strategy_id": "strat-b", "round": 0, "day": -2},
        ]
    )


@pytest.mark.asyncio
async def test_count_runs_by_strategy(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    assert await registry.count_runs_by_strategy(db, strategy_id="strat-a") == 2
    assert await registry.count_runs_by_strategy(db, strategy_id="strat-b") == 1
    assert await registry.count_runs_by_strategy(db, strategy_id="missing") == 0


@pytest.mark.asyncio
async def test_count_runs_by_dataset(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    assert await registry.count_runs_by_dataset(db, round_num=0, day=-2) == 2
    assert await registry.count_runs_by_dataset(db, round_num=0, day=-1) == 1
    assert await registry.count_runs_by_dataset(db, round_num=9, day=9) == 0


@pytest.mark.asyncio
async def test_count_batches_by_strategy(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    assert await registry.count_batches_by_strategy(db, strategy_id="strat-a") == 2
    assert await registry.count_batches_by_strategy(db, strategy_id="strat-b") == 1


@pytest.mark.asyncio
async def test_count_batches_by_dataset(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    # b1 + b2 both reference (0, -2).
    assert await registry.count_batches_by_dataset(db, round_num=0, day=-2) == 2
    # Only b1 references (0, -1).
    assert await registry.count_batches_by_dataset(db, round_num=0, day=-1) == 1
    # b3 references (1, 0).
    assert await registry.count_batches_by_dataset(db, round_num=1, day=0) == 1
    assert await registry.count_batches_by_dataset(db, round_num=9, day=9) == 0


@pytest.mark.asyncio
async def test_count_studies_by_strategy(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    assert await registry.count_studies_by_strategy(db, strategy_id="strat-a") == 1
    assert await registry.count_studies_by_strategy(db, strategy_id="strat-b") == 1


@pytest.mark.asyncio
async def test_count_studies_by_dataset(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await _seed(db)
    assert await registry.count_studies_by_dataset(db, round_num=0, day=-2) == 2
    assert await registry.count_studies_by_dataset(db, round_num=1, day=0) == 0
