"""Background executor for batch tasks.

Design
------
- N asyncio workers started from the FastAPI lifespan, each in its own task.
- Each worker loops: atomically claim one queued task via the registry (which
  flips it to running in a single Mongo op), execute it, write the result,
  repeat.
- When the queue is empty, workers wait on a shared `wakeup` asyncio.Event.
  batch_service.create_batch sets this event after inserting so submissions
  don't wait for the idle poll.
- Failures are recorded on the task; the batch finishes when
  completed + failed == total.
- `simulate_day` is sync CPU-bound — we trust it to block the event loop for
  the run's duration (~1s per tutorial day) given two workers and the user
  base. If this becomes a real problem, wrap the inner call with
  asyncio.to_thread as a follow-up.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from server.schemas.runs import RunCreateRequest
from server.services.run_service import (
    DatasetNotFoundError,
    StrategyNotFoundError,
    execute_run,
)
from server.settings import Settings
from server.storage import registry

log = structlog.get_logger(__name__)

DEFAULT_NUM_WORKERS = 2
IDLE_POLL_SECONDS = 0.5


@dataclass
class WorkersState:
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    stopping: asyncio.Event = field(default_factory=asyncio.Event)


async def start_workers(
    *,
    db: Any,
    settings: Settings,
    num_workers: int = DEFAULT_NUM_WORKERS,
) -> WorkersState:
    """Spawn `num_workers` asyncio tasks and return handles for cleanup."""
    state = WorkersState()
    for i in range(num_workers):
        task = asyncio.create_task(_worker_loop(i, state, db, settings))
        state.tasks.append(task)
    return state


async def stop_workers(state: WorkersState) -> None:
    """Signal workers to stop and await their exit."""
    state.stopping.set()
    state.wakeup.set()  # kick any idle waiters so they observe stopping
    for task in state.tasks:
        task.cancel()
    for task in state.tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    state.tasks.clear()


def signal_new_work(state: WorkersState) -> None:
    """Wake idle workers after a new batch is inserted."""
    state.wakeup.set()


async def _worker_loop(
    worker_id: int, state: WorkersState, db: Any, settings: Settings
) -> None:
    """Main loop: claim → execute → repeat until stopping."""
    while not state.stopping.is_set():
        claim = await registry.claim_next_queued_task(db)
        if claim is None:
            state.wakeup.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(state.wakeup.wait(), timeout=IDLE_POLL_SECONDS)
            continue

        try:
            await _execute_task(claim=claim, db=db, settings=settings)
        except Exception as e:
            log.exception("worker crashed on task", worker=worker_id, claim=claim, err=str(e))


async def _execute_task(
    *, claim: dict[str, Any], db: Any, settings: Settings
) -> None:
    """Run a single claimed task end-to-end and update the batch doc."""
    batch_id = claim["batch_id"]
    round_num = claim["round"]
    day = claim["day"]

    req = RunCreateRequest(
        strategy_id=claim["strategy_id"],
        round=round_num,
        day=day,
        matcher=claim["matcher"],
        trade_matching_mode=claim.get("trade_matching_mode", "all"),
        position_limit=claim["position_limit"],
        params=claim.get("params") or {},
    )

    try:
        run_doc = await execute_run(req=req, settings=settings, db=db)
    except (StrategyNotFoundError, DatasetNotFoundError, FileNotFoundError) as e:
        await _fail_task(db, batch_id, round_num, day, str(e))
        return
    except Exception as e:
        await _fail_task(db, batch_id, round_num, day, f"{type(e).__name__}: {e}")
        return

    await registry.update_batch_task(
        db,
        batch_id=batch_id,
        round_num=round_num,
        day=day,
        updates={
            "status": "succeeded",
            "run_id": run_doc.get("_id"),
            "pnl_total": float(run_doc.get("pnl_total", 0.0)),
            "duration_ms": int(run_doc.get("duration_ms", 0)),
            "error": None,
        },
    )
    await registry.increment_batch_progress(db, batch_id=batch_id, succeeded=1)
    await _maybe_finalize_batch(db, batch_id)


async def _fail_task(
    db: Any, batch_id: str, round_num: int, day: int, error: str
) -> None:
    await registry.update_batch_task(
        db,
        batch_id=batch_id,
        round_num=round_num,
        day=day,
        updates={"status": "failed", "error": error},
    )
    await registry.increment_batch_progress(db, batch_id=batch_id, failed=1)
    await _maybe_finalize_batch(db, batch_id)


async def _maybe_finalize_batch(db: Any, batch_id: str) -> None:
    """If every task reached a terminal state, mark the batch done."""
    batch = await registry.get_batch(db, batch_id)
    if batch is None:
        return
    progress = batch.get("progress", {})
    total = int(progress.get("total", 0))
    done = int(progress.get("completed", 0)) + int(progress.get("failed", 0))
    if done < total:
        return

    final_status = "failed" if progress.get("failed", 0) > 0 else "succeeded"
    await registry.mark_batch_status(
        db,
        batch_id=batch_id,
        status=final_status,
        finished_at=datetime.now(UTC).isoformat(),
    )


async def recover_orphaned_tasks(db: Any) -> int:
    """Reset tasks stuck in `running` (e.g. after a process crash) to `queued`.

    Returns the number of tasks that were recovered.
    """
    recovered = 0
    batches = await registry.list_batches(db, skip=0, limit=10_000)
    for batch in batches:
        if batch.get("status") not in {"queued", "running"}:
            continue
        for task in batch.get("tasks", []):
            if task.get("status") == "running":
                await registry.update_batch_task(
                    db,
                    batch_id=batch["_id"],
                    round_num=task["round"],
                    day=task["day"],
                    updates={"status": "queued"},
                )
                recovered += 1
        # If the batch had running tasks, drop it back to queued so a worker
        # picks it up again. Leave already-completed batches alone.
        if batch.get("status") == "running":
            await registry.mark_batch_status(db, batch_id=batch["_id"], status="queued")
    return recovered
