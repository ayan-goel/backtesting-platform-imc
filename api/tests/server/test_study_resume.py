"""O6 tests: resume_running_studies picks up mid-study state across restart."""

from __future__ import annotations

import asyncio
from typing import Any

import optuna
import pytest
from fastapi import FastAPI

from server.services import study_service
from server.services.study_runner import StudyRunnerState, stop_all
from server.services.study_service import resume_running_studies
from server.settings import get_settings


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


@pytest.mark.asyncio
async def test_resume_picks_up_running_study(
    test_app: FastAPI,
    seeded_dataset: dict[str, Any],
    seeded_strategy: dict[str, Any],
    tmp_path: Any,
) -> None:
    """Simulate a process restart mid-study.

    Seed a study doc marked running with 2 of 5 trials already complete +
    a real optuna SQLite file reflecting that state. Call
    resume_running_studies and verify the runner picks up where it left
    off, producing 3 new child runs (trial numbers 2, 3, 4) and a
    terminal succeeded status.
    """
    db = test_app.state.mongo_db
    settings = get_settings()

    # Build an optuna SQLite file with 2 completed trials.
    optuna_dir = settings.storage_root / "optuna"
    optuna_dir.mkdir(parents=True, exist_ok=True)
    study_id = "resume-test-study"
    db_path = optuna_dir / f"{study_id}.db"
    storage_url = f"sqlite:///{db_path}"
    pre = optuna.create_study(
        study_name=study_id, storage=storage_url, direction="maximize"
    )

    def _seed_objective(trial: optuna.Trial) -> float:
        edge = trial.suggest_int("edge", 0, 5)
        return float(edge)

    pre.optimize(_seed_objective, n_trials=2)

    # Mongo doc: pretend the previous process ran 2 trials and died.
    doc = {
        "_id": study_id,
        "created_at": "2026-04-14T00:00:00Z",
        "strategy_id": seeded_strategy["_id"],
        "strategy_hash": seeded_strategy["sha256"],
        "strategy_filename": seeded_strategy["filename"],
        "round": 0,
        "day": -2,
        "matcher": "depth_only",
        "position_limit": 50,
        "space": {"edge": {"type": "int", "low": 0, "high": 5}},
        "objective": "pnl_total",
        "direction": "maximize",
        "n_trials": 5,
        "status": "running",
        "started_at": "2026-04-14T00:00:00Z",
        "finished_at": None,
        "storage_path": f"optuna/{study_id}.db",
        "progress": {"total": 5, "completed": 2, "failed": 0, "running": 0},
        "best_trial": None,
    }
    await db["studies"].insert_one(doc)

    runner = StudyRunnerState()
    test_app.state.study_runner = runner
    try:
        resumed = await resume_running_studies(
            db=db, settings=settings, runner_state=runner
        )
        assert resumed == 1

        final = await _wait_until(
            lambda s: s.get("status") in {"succeeded", "failed"}, db, study_id
        )
        assert final["status"] == "succeeded"
        # 5 total — 3 new (the runner picks up from trial 2) + 2 pre-seeded in optuna.
        assert final["progress"]["completed"] == 5

        # New child runs got stamped with study_id; there should be 3 of them
        # (trial numbers 2, 3, 4 — the 2 pre-seeded optuna trials had no
        # corresponding run doc since they came from a fake earlier process).
        child_runs = [r async for r in db["runs"].find({"study_id": study_id})]
        assert len(child_runs) == 3
    finally:
        await stop_all(runner)


@pytest.mark.asyncio
async def test_resume_ignores_terminal_studies(
    test_app: FastAPI,
    seeded_strategy: dict[str, Any],
) -> None:
    """Studies in succeeded/failed/cancelled are not re-spawned."""
    db = test_app.state.mongo_db
    settings = get_settings()

    for status in ("succeeded", "failed", "cancelled"):
        await db["studies"].insert_one(
            {
                "_id": f"terminal-{status}",
                "created_at": "2026-04-14T00:00:00Z",
                "strategy_id": seeded_strategy["_id"],
                "strategy_hash": seeded_strategy["sha256"],
                "strategy_filename": seeded_strategy["filename"],
                "round": 0,
                "day": -2,
                "matcher": "depth_only",
                "position_limit": 50,
                "space": {"edge": {"type": "int", "low": 0, "high": 5}},
                "objective": "pnl_total",
                "direction": "maximize",
                "n_trials": 5,
                "status": status,
                "started_at": "2026-04-14T00:00:00Z",
                "finished_at": "2026-04-14T00:01:00Z",
                "storage_path": f"optuna/terminal-{status}.db",
                "progress": {"total": 5, "completed": 5, "failed": 0, "running": 0},
                "best_trial": None,
            }
        )

    runner = StudyRunnerState()
    try:
        resumed = await resume_running_studies(
            db=db, settings=settings, runner_state=runner
        )
        assert resumed == 0
        assert runner.tasks == {}
    finally:
        await stop_all(runner)
