"""O5 tests: study runner ask/tell loop end-to-end."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI

from server.schemas.studies import StudyCreateRequest
from server.services import study_service
from server.services.study_runner import StudyRunnerState, stop_all
from server.settings import get_settings

BROKEN_TRADER = b"""
class Trader:
    def run(self, state):
        raise RuntimeError("boom")
"""


async def _wait_until(
    predicate: Any, db: Any, study_id: str, timeout: float = 20.0
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        last = await study_service.get_study(db, study_id) or {}
        if predicate(last):
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting. last doc: {last}")


@pytest_asyncio.fixture
async def runner(test_app: FastAPI) -> AsyncIterator[StudyRunnerState]:
    state = StudyRunnerState()
    test_app.state.study_runner = state
    try:
        yield state
    finally:
        await stop_all(state)


@pytest_asyncio.fixture
async def broken_strategy(test_app: FastAPI, tmp_path: Path) -> dict[str, Any]:
    """Seed a strategy that raises at trader.run time."""
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    content = BROKEN_TRADER
    sha256 = hashlib.sha256(content).hexdigest()
    strategy_id = f"broken-{sha256[:8]}"
    storage_path = strategies_dir / f"{strategy_id}.py"
    storage_path.write_bytes(content)
    doc = {
        "_id": strategy_id,
        "filename": "broken.py",
        "stem": "broken",
        "sha256": f"sha256:{sha256}",
        "uploaded_at": "2026-04-14T00:00:00Z",
        "size_bytes": len(content),
        "storage_subpath": f"strategies/{storage_path.name}",
    }
    await test_app.state.mongo_db["strategies"].insert_one(doc)
    return doc


def _make_req(strategy_id: str, n_trials: int = 3) -> StudyCreateRequest:
    return StudyCreateRequest(
        strategy_id=strategy_id,
        round=0,
        day=-2,
        matcher="depth_only",
        position_limit=50,
        space={"edge": {"type": "int", "low": 0, "high": 5}},
        objective="pnl_total",
        direction="maximize",
        n_trials=n_trials,
    )


@pytest.mark.asyncio
async def test_study_runs_end_to_end(
    test_app: FastAPI,
    runner: StudyRunnerState,
    seeded_dataset: dict[str, Any],
    seeded_strategy: dict[str, Any],
) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await study_service.create_study(
        req=_make_req(seeded_strategy["_id"], n_trials=3),
        settings=settings,
        db=db,
        runner_state=runner,
    )
    study_id = doc["_id"]

    final = await _wait_until(
        lambda s: s.get("status") in {"succeeded", "failed"}, db, study_id
    )
    assert final["status"] == "succeeded", final
    assert final["progress"]["completed"] == 3
    assert final["progress"]["failed"] == 0
    assert final["progress"]["running"] == 0
    assert final["best_trial"] is not None
    assert final["best_trial"]["run_id"] is not None

    # Three distinct run docs stamped with study_id + trial_number.
    runs = [r async for r in db["runs"].find({"study_id": study_id})]
    assert len(runs) == 3
    trial_numbers = sorted(r["trial_number"] for r in runs)
    assert trial_numbers == [0, 1, 2]
    assert all("params" in r for r in runs)


@pytest.mark.asyncio
async def test_study_failure_path(
    test_app: FastAPI,
    runner: StudyRunnerState,
    seeded_dataset: dict[str, Any],
    broken_strategy: dict[str, Any],
) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await study_service.create_study(
        req=_make_req(broken_strategy["_id"], n_trials=2),
        settings=settings,
        db=db,
        runner_state=runner,
    )
    final = await _wait_until(
        lambda s: s.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "failed"
    assert final["progress"]["failed"] == 2
    assert final["progress"]["completed"] == 0
    assert final["best_trial"] is None


@pytest.mark.asyncio
async def test_study_cancellation_halts_loop(
    test_app: FastAPI,
    runner: StudyRunnerState,
    seeded_dataset: dict[str, Any],
    seeded_strategy: dict[str, Any],
) -> None:
    """Cancel immediately after create — the runner should observe the
    cancel flag within a trial or two and exit with status=cancelled
    before completing all n_trials."""
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await study_service.create_study(
        req=_make_req(seeded_strategy["_id"], n_trials=20),
        settings=settings,
        db=db,
        runner_state=runner,
    )
    study_id = doc["_id"]

    # Cancel before the runner can plausibly complete 20 trials.
    await study_service.cancel_study(db, study_id)

    final = await _wait_until(
        lambda s: s.get("status") in {"cancelled", "succeeded", "failed"}, db, study_id
    )
    assert final["status"] == "cancelled"
    assert final["progress"]["completed"] < 20


@pytest.mark.asyncio
async def test_normal_runs_still_idempotent(
    test_app: FastAPI,
    seeded_dataset: dict[str, Any],
    seeded_strategy: dict[str, Any],
) -> None:
    """A plain (non-study) RunCreateRequest must still short-circuit on duplicate."""
    db = test_app.state.mongo_db
    settings = get_settings()

    from server.schemas.runs import RunCreateRequest
    from server.services.run_service import execute_run

    req = RunCreateRequest(
        strategy_id=seeded_strategy["_id"],
        round=0,
        day=-2,
        matcher="depth_only",
        position_limit=50,
        params={},
    )
    first = await execute_run(req=req, settings=settings, db=db)
    second = await execute_run(req=req, settings=settings, db=db)
    assert first["_id"] == second["_id"]
