"""Study creation, lookup, listing, cancellation.

The study runner (ask/tell loop) lives in study_runner.py — this module only
writes the queued study doc, answers queries, flips status flags, and
bootstraps optuna SQLite storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import optuna

from server.schemas.studies import StudyCreateRequest
from server.services import dataset_service, strategy_service
from server.services.run_service import DatasetNotFoundError, StrategyNotFoundError
from server.services.study_runner import StudyRunnerState, start_study_loop
from server.services.study_space import parse_space
from server.settings import Settings
from server.storage import registry


class StudyBusyError(Exception):
    """Raised when a delete is attempted on a still-queued/running study."""


def _build_study_id(stem: str, round_num: int, day: int) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}__{stem}__r{round_num}d{day}__study"


def optuna_storage_root(settings: Settings) -> Path:
    return settings.storage_root / "optuna"


def optuna_db_path(settings: Settings, study_id: str) -> Path:
    return optuna_storage_root(settings) / f"{study_id}.db"


def optuna_storage_url(path: Path) -> str:
    return f"sqlite:///{path}"


async def create_study(
    *,
    req: StudyCreateRequest,
    settings: Settings,
    db: Any,
    runner_state: StudyRunnerState | None = None,
) -> dict[str, Any]:
    """Validate inputs, create the optuna SQLite file, insert the Mongo doc.

    Raises:
        StrategyNotFoundError / DatasetNotFoundError — 404-mapped in the router.
        SpaceValidationError — 400-mapped in the router.
    """
    strategy_doc = await strategy_service.get_strategy(db, req.strategy_id)
    if strategy_doc is None:
        raise StrategyNotFoundError(
            f"no strategy {req.strategy_id!r}. upload via POST /strategies first."
        )

    dataset_doc = await dataset_service.get_dataset(db, round_num=req.round, day=req.day)
    if dataset_doc is None:
        raise DatasetNotFoundError(
            f"no dataset uploaded for round={req.round} day={req.day}. "
            "upload it via POST /datasets first."
        )

    # Validate (and coerce to models) before touching disk.
    parse_space(req.space)

    study_id = _build_study_id(strategy_doc["stem"], req.round, req.day)
    db_path = optuna_db_path(settings, study_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    optuna.create_study(
        study_name=study_id,
        storage=optuna_storage_url(db_path),
        direction=req.direction,
        load_if_exists=True,
    )

    storage_subpath = str(db_path.relative_to(settings.storage_root))

    doc = {
        "_id": study_id,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": req.strategy_id,
        "strategy_hash": strategy_doc["sha256"],
        "strategy_filename": strategy_doc["filename"],
        "round": req.round,
        "day": req.day,
        "matcher": req.matcher,
        "trade_matching_mode": req.trade_matching_mode,
        "position_limit": req.position_limit,
        "space": req.space,
        "objective": req.objective,
        "direction": req.direction,
        "n_trials": req.n_trials,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "storage_path": storage_subpath,
        "progress": {
            "total": req.n_trials,
            "completed": 0,
            "failed": 0,
            "running": 0,
        },
        "best_trial": None,
    }
    await registry.insert_study(db, doc)
    if runner_state is not None:
        start_study_loop(runner_state, study_id=study_id, db=db, settings=settings)
    return doc


async def resume_running_studies(
    *,
    db: Any,
    settings: Settings,
    runner_state: StudyRunnerState,
) -> int:
    """On startup, re-spawn loops for any study still marked running.

    Returns the number of studies resumed. Optuna's SQLite storage holds
    completed trial results; the ask/tell loop continues from there. A trial
    that was mid-flight when the process died is dropped by optuna on
    reopen (its TrialState stays RUNNING and TPE skips past it).
    """
    resumed = 0
    studies = await registry.list_studies(db, skip=0, limit=10_000)
    for study in studies:
        if study.get("status") != "running":
            continue
        start_study_loop(
            runner_state, study_id=study["_id"], db=db, settings=settings
        )
        resumed += 1
    return resumed


async def get_study(db: Any, study_id: str) -> dict[str, Any] | None:
    return await registry.get_study(db, study_id)


async def list_studies(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    return await registry.list_studies(db, skip=skip, limit=limit)


async def list_trials(db: Any, study_id: str) -> list[dict[str, Any]]:
    """Return trial summaries for a study, sorted by trial_number.

    Queries the runs collection for docs stamped with this study_id.
    Each summary exposes the trial number, status, objective value,
    params, run_id, and duration.
    """
    study = await registry.get_study(db, study_id)
    if study is None:
        return []
    objective = study.get("objective", "pnl_total")
    cursor = db[registry.RUNS_COLLECTION].find({"study_id": study_id})
    trials: list[dict[str, Any]] = []
    async for run in cursor:
        value = _extract_objective_value(run, objective)
        trials.append(
            {
                "trial_number": run.get("trial_number"),
                "status": "succeeded",
                "value": value,
                "params": run.get("params", {}),
                "run_id": run.get("_id"),
                "duration_ms": run.get("duration_ms"),
            }
        )
    trials.sort(key=lambda t: (t["trial_number"] is None, t["trial_number"]))
    return trials


def _extract_objective_value(run_doc: dict[str, Any], objective: str) -> float | None:
    if objective == "pnl_total":
        val = run_doc.get("pnl_total")
        return None if val is None else float(val)
    if objective.startswith("pnl_by_product."):
        symbol = objective.split(".", 1)[1]
        by_product = run_doc.get("pnl_by_product") or {}
        val = by_product.get(symbol)
        return None if val is None else float(val)
    return None


async def delete_study(
    *,
    db: Any,
    settings: Settings,
    study_id: str,
) -> bool:
    """Remove the study doc and its optuna SQLite storage file.

    Leaves child runs stamped with this study_id untouched. Raises
    StudyBusyError if the study is queued or running (caller should cancel
    first). Idempotent on the filesystem side.
    """
    doc = await registry.get_study(db, study_id)
    if doc is None:
        return False
    if doc.get("status") in {"queued", "running"}:
        raise StudyBusyError(
            f"study {study_id!r} is {doc.get('status')}; cancel it first"
        )
    storage_subpath = doc.get("storage_path")
    if storage_subpath:
        (settings.storage_root / storage_subpath).unlink(missing_ok=True)
    await registry.delete_study(db, study_id)
    return True


async def cancel_study(db: Any, study_id: str) -> dict[str, Any] | None:
    """Flip a non-terminal study to cancelled. Returns the updated doc or None."""
    study = await registry.get_study(db, study_id)
    if study is None:
        return None
    if study["status"] in {"succeeded", "failed", "cancelled"}:
        return study
    await registry.mark_study_status(
        db,
        study_id=study_id,
        status="cancelled",
        finished_at=datetime.now(UTC).isoformat(),
    )
    return await registry.get_study(db, study_id)
