"""Per-study asyncio task: optuna ask → execute_run → tell → update progress.

Design
------
Each study owns one asyncio task that drives the ask/tell loop sequentially.
Sequential ask/tell is deliberate: optuna's TPE sampler is designed around
it, and the batch_runner pool already saturates CPU with 2 workers. To run
multiple studies in parallel, submit multiple studies.

Trials execute via `run_service.execute_run` directly (not via the batch
queue). `RunCreateRequest.study_id` tells execute_run to skip its
idempotency short-circuit and stamp the produced run with study_id /
trial_number / params.

Cancellation: the loop re-reads the Mongo doc at the top of each iteration
and exits cleanly if `status == cancelled`. Already-running trials finish
naturally — we don't kill mid-simulation.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import optuna
import structlog

from server.schemas.runs import RunCreateRequest
from server.schemas.studies import StudyDoc
from server.services.run_service import (
    DatasetNotFoundError,
    StrategyNotFoundError,
    execute_run,
)
from server.services.study_space import apply_space, parse_space
from server.settings import Settings
from server.storage import registry

log = structlog.get_logger(__name__)


@dataclass
class StudyRunnerState:
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    stopping: asyncio.Event = field(default_factory=asyncio.Event)


def start_study_loop(
    state: StudyRunnerState,
    *,
    study_id: str,
    db: Any,
    settings: Settings,
) -> asyncio.Task[None]:
    """Spawn the loop task and register it in shared state."""
    task = asyncio.create_task(_study_loop(study_id, state, db, settings))
    state.tasks[study_id] = task
    return task


async def stop_all(state: StudyRunnerState) -> None:
    state.stopping.set()
    for task in list(state.tasks.values()):
        task.cancel()
    for task in list(state.tasks.values()):
        with contextlib.suppress(asyncio.CancelledError):
            await task
    state.tasks.clear()


async def _study_loop(
    study_id: str, state: StudyRunnerState, db: Any, settings: Settings
) -> None:
    """Main ask/tell loop for a single study."""
    try:
        await _run_study(study_id, state, db, settings)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("study loop crashed", study_id=study_id, err=str(e))
        await registry.mark_study_status(
            db,
            study_id=study_id,
            status="failed",
            finished_at=datetime.now(UTC).isoformat(),
        )
    finally:
        state.tasks.pop(study_id, None)


async def _run_study(
    study_id: str, state: StudyRunnerState, db: Any, settings: Settings
) -> None:
    doc = await registry.get_study(db, study_id)
    if doc is None:
        log.warning("study disappeared before loop start", study_id=study_id)
        return
    study_doc = StudyDoc.model_validate(doc)

    # Flip queued → running on first entry.
    if study_doc.status == "queued":
        await registry.mark_study_status(
            db,
            study_id=study_id,
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )

    storage_url = f"sqlite:///{(settings.storage_root / study_doc.storage_path).resolve()}"
    study = optuna.load_study(study_name=study_id, storage=storage_url)
    space = parse_space(study_doc.space)

    while not state.stopping.is_set():
        current = await registry.get_study(db, study_id)
        if current is None:
            return
        status = current.get("status")
        if status in {"cancelled", "failed"}:
            return
        progress = current.get("progress", {})
        completed = int(progress.get("completed", 0))
        failed = int(progress.get("failed", 0))
        if completed + failed >= study_doc.n_trials:
            break

        trial = study.ask()
        params = apply_space(trial, space)

        await registry.increment_study_progress(db, study_id=study_id, running=1)

        req = RunCreateRequest(
            strategy_id=study_doc.strategy_id,
            round=study_doc.round,
            day=study_doc.day,
            matcher=study_doc.matcher,
            trade_matching_mode=getattr(study_doc, "trade_matching_mode", "all"),
            position_limit=study_doc.position_limit,
            params=params,
            study_id=study_id,
            trial_number=trial.number,
        )

        try:
            run_doc = await execute_run(req=req, settings=settings, db=db)
        except (StrategyNotFoundError, DatasetNotFoundError, FileNotFoundError) as e:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            await registry.increment_study_progress(
                db, study_id=study_id, failed=1, running=-1
            )
            log.warning(
                "study trial failed (infra)", study_id=study_id, trial=trial.number, err=str(e)
            )
            continue
        except Exception as e:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            await registry.increment_study_progress(
                db, study_id=study_id, failed=1, running=-1
            )
            log.warning(
                "study trial failed", study_id=study_id, trial=trial.number, err=str(e)
            )
            continue

        value = _extract_objective(run_doc, study_doc.objective)
        study.tell(trial, value)

        await registry.increment_study_progress(
            db, study_id=study_id, completed=1, running=-1
        )
        await registry.update_study_best(
            db,
            study_id=study_id,
            direction=study_doc.direction,
            trial={
                "number": trial.number,
                "value": float(value),
                "params": params,
                "run_id": run_doc.get("_id"),
            },
        )

    await _finalize(db, study_id)


def _extract_objective(run_doc: dict[str, Any], objective: str) -> float:
    """Pull the objective value out of a run doc.

    Supports 'pnl_total' and 'pnl_by_product.<SYMBOL>'.
    """
    if objective == "pnl_total":
        return float(run_doc.get("pnl_total", 0.0))
    if objective.startswith("pnl_by_product."):
        symbol = objective.split(".", 1)[1]
        by_product: dict[str, Any] = run_doc.get("pnl_by_product", {}) or {}
        return float(by_product.get(symbol, 0.0))
    raise ValueError(f"unknown objective: {objective}")


async def _finalize(db: Any, study_id: str) -> None:
    doc = await registry.get_study(db, study_id)
    if doc is None:
        return
    if doc.get("status") in {"cancelled", "failed"}:
        return
    progress = doc.get("progress", {})
    final_status = "failed" if int(progress.get("failed", 0)) > 0 and int(progress.get("completed", 0)) == 0 else "succeeded"
    await registry.mark_study_status(
        db,
        study_id=study_id,
        status=final_status,
        finished_at=datetime.now(UTC).isoformat(),
    )


