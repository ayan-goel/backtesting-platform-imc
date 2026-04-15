"""B3 tests: batch executor runs tasks end-to-end against seeded fixtures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI

from server.schemas.batches import BatchCreateRequest, DatasetKey
from server.services import batch_runner, batch_service
from server.settings import get_settings


async def _wait_until(
    predicate: Any, db: Any, batch_id: str, timeout: float = 15.0
) -> dict[str, Any]:
    """Poll the batch doc until predicate returns True or we time out."""
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        last = await batch_service.get_batch(db, batch_id) or {}
        if predicate(last):
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting. last doc: {last}")


@pytest_asyncio.fixture
async def workers(test_app: FastAPI) -> AsyncIterator[batch_runner.WorkersState]:
    """Start a 1-worker executor bound to the test app's db."""
    settings = get_settings()
    state = await batch_runner.start_workers(
        db=test_app.state.mongo_db, settings=settings, num_workers=1
    )
    test_app.state.batch_workers = state
    try:
        yield state
    finally:
        await batch_runner.stop_workers(state)


@pytest.mark.asyncio
async def test_batch_runs_end_to_end(
    test_app: FastAPI,
    workers: batch_runner.WorkersState,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await batch_service.create_batch(
        req=BatchCreateRequest(
            strategy_id=seeded_strategy["_id"],
            datasets=[DatasetKey(round=0, day=-2)],
            matcher="depth_only",
            position_limit=50,
            params={},
        ),
        settings=settings,
        db=db,
    )
    batch_runner.signal_new_work(workers)

    final = await _wait_until(
        lambda b: b.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "succeeded", final
    assert final["progress"] == {"total": 1, "completed": 1, "failed": 0}
    assert final["finished_at"] is not None
    assert final["started_at"] is not None

    task = final["tasks"][0]
    assert task["status"] == "succeeded"
    assert task["run_id"] is not None
    assert task["pnl_total"] is not None
    assert task["duration_ms"] is not None
    assert task["error"] is None


@pytest.mark.asyncio
async def test_batch_with_missing_dataset_fails_task(
    test_app: FastAPI,
    workers: batch_runner.WorkersState,
    seeded_strategy: dict,
) -> None:
    """Injecting a dataset into the batch doc directly (bypassing create_batch
    validation) simulates a run-time dataset deletion between submission and
    execution. The worker should mark that task failed and finalize the
    batch."""
    db = test_app.state.mongo_db

    doc: dict[str, Any] = {
        "_id": "batch-missing-dataset",
        "created_at": "2026-04-13T00:00:00Z",
        "strategy_id": seeded_strategy["_id"],
        "strategy_hash": seeded_strategy["sha256"],
        "strategy_filename": seeded_strategy["filename"],
        "matcher": "depth_only",
        "position_limit": 50,
        "params": {},
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "tasks": [
            {
                "round": 99,
                "day": 99,
                "status": "queued",
                "run_id": None,
                "error": None,
                "duration_ms": None,
                "pnl_total": None,
            }
        ],
        "progress": {"total": 1, "completed": 0, "failed": 0},
    }
    await db["batches"].insert_one(doc)
    batch_runner.signal_new_work(workers)

    final = await _wait_until(
        lambda b: b.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "failed"
    assert final["progress"] == {"total": 1, "completed": 0, "failed": 1}
    task = final["tasks"][0]
    assert task["status"] == "failed"
    assert task["error"] is not None
    assert "dataset" in task["error"].lower()


@pytest.mark.asyncio
async def test_recover_orphaned_tasks(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    doc: dict[str, Any] = {
        "_id": "batch-orphan",
        "created_at": "2026-04-13T00:00:00Z",
        "strategy_id": "noop-abc",
        "strategy_hash": "sha256:deadbeef",
        "strategy_filename": "noop.py",
        "matcher": "depth_only",
        "position_limit": 50,
        "params": {},
        "status": "running",
        "started_at": "2026-04-13T00:00:00Z",
        "finished_at": None,
        "tasks": [
            {"round": 0, "day": -2, "status": "succeeded", "run_id": "run-a",
             "error": None, "duration_ms": 100, "pnl_total": 10.0},
            {"round": 0, "day": -1, "status": "running", "run_id": None,
             "error": None, "duration_ms": None, "pnl_total": None},
            {"round": 1, "day": 0, "status": "queued", "run_id": None,
             "error": None, "duration_ms": None, "pnl_total": None},
        ],
        "progress": {"total": 3, "completed": 1, "failed": 0},
    }
    await db["batches"].insert_one(doc)

    recovered = await batch_runner.recover_orphaned_tasks(db)
    assert recovered == 1

    restored = await batch_service.get_batch(db, "batch-orphan")
    assert restored is not None
    statuses = {(t["round"], t["day"]): t["status"] for t in restored["tasks"]}
    assert statuses == {(0, -2): "succeeded", (0, -1): "queued", (1, 0): "queued"}
    assert restored["status"] == "queued"
