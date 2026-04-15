"""B1 tests: batches registry helpers + indexes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from server.storage import registry


def _make_batch_doc(
    batch_id: str = "batch-1",
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if tasks is None:
        tasks = [
            {"round": 0, "day": -2, "status": "queued", "run_id": None, "error": None,
             "duration_ms": None, "pnl_total": None},
            {"round": 0, "day": -1, "status": "queued", "run_id": None, "error": None,
             "duration_ms": None, "pnl_total": None},
            {"round": 1, "day": 0, "status": "queued", "run_id": None, "error": None,
             "duration_ms": None, "pnl_total": None},
        ]
    return {
        "_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": "noop-abc",
        "strategy_hash": "sha256:deadbeef",
        "strategy_filename": "noop.py",
        "matcher": "depth_only",
        "position_limit": 50,
        "params": {},
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "tasks": tasks,
        "progress": {"total": len(tasks), "completed": 0, "failed": 0},
    }


@pytest.mark.asyncio
async def test_ensure_indexes_creates_batches_collection(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    index_info = await db[registry.BATCHES_COLLECTION].index_information()
    key_tuples = {tuple(tuple(pair) for pair in info["key"]) for info in index_info.values()}
    assert (("created_at", -1),) in key_tuples
    assert (("status", 1),) in key_tuples


@pytest.mark.asyncio
async def test_insert_and_get_batch(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    doc = _make_batch_doc()
    await registry.insert_batch(db, doc)
    got = await registry.get_batch(db, "batch-1")
    assert got is not None
    assert got["_id"] == "batch-1"
    assert len(got["tasks"]) == 3


@pytest.mark.asyncio
async def test_get_batch_missing(test_app: FastAPI) -> None:
    assert await registry.get_batch(test_app.state.mongo_db, "nope") is None


@pytest.mark.asyncio
async def test_list_batches_sorted_desc(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    early = _make_batch_doc("batch-early")
    late = _make_batch_doc("batch-late")
    early["created_at"] = "2026-01-01T00:00:00+00:00"
    late["created_at"] = "2026-04-13T00:00:00+00:00"
    await registry.insert_batch(db, early)
    await registry.insert_batch(db, late)

    listed = await registry.list_batches(db)
    assert [b["_id"] for b in listed] == ["batch-late", "batch-early"]


@pytest.mark.asyncio
async def test_update_batch_task_mutates_one_task(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())

    modified = await registry.update_batch_task(
        db,
        batch_id="batch-1",
        round_num=0,
        day=-1,
        updates={"status": "succeeded", "run_id": "run-xyz", "pnl_total": 123.45},
    )
    assert modified == 1

    got = await registry.get_batch(db, "batch-1")
    assert got is not None
    by_key = {(t["round"], t["day"]): t for t in got["tasks"]}
    assert by_key[(0, -1)]["status"] == "succeeded"
    assert by_key[(0, -1)]["run_id"] == "run-xyz"
    assert by_key[(0, -1)]["pnl_total"] == 123.45
    # siblings untouched
    assert by_key[(0, -2)]["status"] == "queued"
    assert by_key[(1, 0)]["status"] == "queued"


@pytest.mark.asyncio
async def test_update_batch_task_no_match(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())
    modified = await registry.update_batch_task(
        db, batch_id="batch-1", round_num=99, day=99, updates={"status": "failed"}
    )
    assert modified == 0


@pytest.mark.asyncio
async def test_mark_batch_status(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())
    modified = await registry.mark_batch_status(
        db, batch_id="batch-1", status="succeeded", finished_at="2026-04-13T10:00:00Z"
    )
    assert modified == 1
    got = await registry.get_batch(db, "batch-1")
    assert got is not None
    assert got["status"] == "succeeded"
    assert got["finished_at"] == "2026-04-13T10:00:00Z"


@pytest.mark.asyncio
async def test_increment_batch_progress(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())

    await registry.increment_batch_progress(db, batch_id="batch-1", succeeded=2)
    await registry.increment_batch_progress(db, batch_id="batch-1", failed=1)

    got = await registry.get_batch(db, "batch-1")
    assert got is not None
    assert got["progress"]["completed"] == 2
    assert got["progress"]["failed"] == 1
    assert got["progress"]["total"] == 3


@pytest.mark.asyncio
async def test_increment_batch_progress_noop(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())
    modified = await registry.increment_batch_progress(db, batch_id="batch-1")
    assert modified == 0


@pytest.mark.asyncio
async def test_claim_next_queued_task_returns_first(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_batch(db, _make_batch_doc())

    claim = await registry.claim_next_queued_task(db)
    assert claim is not None
    assert claim["batch_id"] == "batch-1"
    assert claim["strategy_id"] == "noop-abc"
    assert claim["matcher"] == "depth_only"
    assert claim["position_limit"] == 50

    # The batch should now be marked running + started_at populated,
    # and the claimed task should be status=running.
    got = await registry.get_batch(db, "batch-1")
    assert got is not None
    assert got["status"] == "running"
    assert got["started_at"] is not None
    running_tasks = [t for t in got["tasks"] if t["status"] == "running"]
    assert len(running_tasks) == 1


@pytest.mark.asyncio
async def test_claim_next_queued_task_exhausts(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    tasks = [
        {"round": 0, "day": -2, "status": "queued", "run_id": None, "error": None,
         "duration_ms": None, "pnl_total": None},
    ]
    await registry.insert_batch(db, _make_batch_doc("single", tasks=tasks))

    first = await registry.claim_next_queued_task(db)
    assert first is not None
    second = await registry.claim_next_queued_task(db)
    assert second is None


@pytest.mark.asyncio
async def test_claim_next_queued_task_none_available(test_app: FastAPI) -> None:
    assert await registry.claim_next_queued_task(test_app.state.mongo_db) is None
