"""O3 tests: studies registry helpers + indexes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from server.storage import registry


def _make_study_doc(
    study_id: str = "study-1",
    best_trial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "_id": study_id,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": "noop-abc",
        "strategy_hash": "sha256:deadbeef",
        "strategy_filename": "noop.py",
        "round": 0,
        "day": -2,
        "matcher": "depth_only",
        "position_limit": 50,
        "space": {"edge": {"type": "int", "low": 0, "high": 5}},
        "objective": "pnl_total",
        "direction": "maximize",
        "n_trials": 10,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "storage_path": f"optuna/{study_id}.db",
        "progress": {"total": 10, "completed": 0, "failed": 0, "running": 0},
        "best_trial": best_trial,
    }


@pytest.mark.asyncio
async def test_ensure_indexes_creates_studies_collection(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    index_info = await db[registry.STUDIES_COLLECTION].index_information()
    key_tuples = {tuple(tuple(pair) for pair in info["key"]) for info in index_info.values()}
    assert (("created_at", -1),) in key_tuples
    assert (("status", 1),) in key_tuples


@pytest.mark.asyncio
async def test_insert_and_get_study(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    doc = _make_study_doc()
    await registry.insert_study(db, doc)
    got = await registry.get_study(db, "study-1")
    assert got is not None
    assert got["_id"] == "study-1"
    assert got["direction"] == "maximize"


@pytest.mark.asyncio
async def test_list_studies_sorted_by_created_at_desc(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    doc_a = _make_study_doc("study-a")
    doc_b = _make_study_doc("study-b")
    doc_b["created_at"] = "2099-01-01T00:00:00+00:00"
    await registry.insert_study(db, doc_a)
    await registry.insert_study(db, doc_b)

    studies = await registry.list_studies(db)
    ids = [s["_id"] for s in studies]
    assert ids.index("study-b") < ids.index("study-a")


@pytest.mark.asyncio
async def test_mark_study_status_sets_timestamps(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_study(db, _make_study_doc())
    await registry.mark_study_status(
        db, study_id="study-1", status="running", started_at="t-start"
    )
    got = await registry.get_study(db, "study-1")
    assert got is not None
    assert got["status"] == "running"
    assert got["started_at"] == "t-start"


@pytest.mark.asyncio
async def test_increment_study_progress(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_study(db, _make_study_doc())
    await registry.increment_study_progress(db, study_id="study-1", completed=2, running=1)
    await registry.increment_study_progress(db, study_id="study-1", completed=1, failed=1, running=-1)
    got = await registry.get_study(db, "study-1")
    assert got is not None
    progress = got["progress"]
    assert progress["completed"] == 3
    assert progress["failed"] == 1
    assert progress["running"] == 0


@pytest.mark.asyncio
async def test_update_study_best_maximize_keeps_higher(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_study(db, _make_study_doc())

    trial_a = {"number": 0, "value": 100.0, "params": {"edge": 2}, "run_id": "run-a"}
    trial_b = {"number": 1, "value": 50.0, "params": {"edge": 3}, "run_id": "run-b"}
    trial_c = {"number": 2, "value": 200.0, "params": {"edge": 4}, "run_id": "run-c"}

    assert await registry.update_study_best(
        db, study_id="study-1", direction="maximize", trial=trial_a
    ) is True
    assert await registry.update_study_best(
        db, study_id="study-1", direction="maximize", trial=trial_b
    ) is False
    assert await registry.update_study_best(
        db, study_id="study-1", direction="maximize", trial=trial_c
    ) is True

    got = await registry.get_study(db, "study-1")
    assert got is not None
    assert got["best_trial"]["number"] == 2
    assert got["best_trial"]["value"] == 200.0


@pytest.mark.asyncio
async def test_update_study_best_minimize_keeps_lower(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    await registry.insert_study(db, _make_study_doc())

    trial_a = {"number": 0, "value": 100.0, "params": {"edge": 2}, "run_id": "run-a"}
    trial_b = {"number": 1, "value": 150.0, "params": {"edge": 3}, "run_id": "run-b"}
    trial_c = {"number": 2, "value": 50.0, "params": {"edge": 4}, "run_id": "run-c"}

    assert await registry.update_study_best(
        db, study_id="study-1", direction="minimize", trial=trial_a
    ) is True
    assert await registry.update_study_best(
        db, study_id="study-1", direction="minimize", trial=trial_b
    ) is False
    assert await registry.update_study_best(
        db, study_id="study-1", direction="minimize", trial=trial_c
    ) is True

    got = await registry.get_study(db, "study-1")
    assert got is not None
    assert got["best_trial"]["number"] == 2
    assert got["best_trial"]["value"] == 50.0
