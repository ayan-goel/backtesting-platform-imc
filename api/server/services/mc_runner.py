"""Background executor for Monte Carlo simulations.

Design
------
One async worker loops: claim a queued mc doc, load the strategy +
historical data, compute calibration once, then drive each path through
`run_mc_path` sequentially. Progress is written to Mongo after every path.

Parallelism is added in T6 — for T1 we run paths serially inside the
worker task. `simulate_day` is sync + CPU-bound, so each path blocks the
event loop for its duration. That's fine while n_paths is small and is
the same trade-off `batch_runner` accepts.

Cancellation: between paths, the worker re-reads the mc doc and exits
early if the user flipped status to `cancelled`.

Recovery: on startup, `recover_orphaned_mc` resets any `running`
simulations back to `queued` so the next worker tick picks them up.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

# Guards load_trader against concurrent sys.modules mutation. The loader
# temporarily registers synthetic "strategies" / "strategies.datamodel"
# entries while importing — two threads racing that setup can end up
# with one thread's registrations visible to the other's import.
_STRATEGY_LOAD_LOCK = threading.Lock()

from engine.market.loader import MarketData, load_round_day
from engine.matching.factory import resolve_matcher
from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.generators import resolve_generator
from engine.montecarlo.rng import rng_for_path
from engine.simulator.runner import RunConfig
from engine.simulator.strategy_loader import load_trader
from server.services import dataset_service, strategy_service
from server.services.mc_path_runner import PathResult, run_mc_path
from server.settings import Settings
from server.storage import mc_artifacts, registry

log = structlog.get_logger(__name__)

IDLE_POLL_SECONDS = 0.5


@dataclass
class McWorkersState:
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    stopping: asyncio.Event = field(default_factory=asyncio.Event)


async def start_mc_worker(*, db: Any, settings: Settings) -> McWorkersState:
    state = McWorkersState()
    state.task = asyncio.create_task(_worker_loop(state, db, settings))
    return state


async def stop_mc_worker(state: McWorkersState) -> None:
    state.stopping.set()
    state.wakeup.set()
    if state.task is not None:
        state.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.task
        state.task = None


def signal_new_mc_work(state: McWorkersState) -> None:
    state.wakeup.set()


async def _worker_loop(state: McWorkersState, db: Any, settings: Settings) -> None:
    while not state.stopping.is_set():
        claim = await _claim_next_queued_mc(db)
        if claim is None:
            state.wakeup.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(state.wakeup.wait(), timeout=IDLE_POLL_SECONDS)
            continue
        try:
            await _execute_mc(mc_id=claim["_id"], db=db, settings=settings, state=state)
        except Exception as e:
            log.exception("mc worker crashed", mc_id=claim.get("_id"), err=str(e))
            await registry.mark_mc_status(
                db,
                mc_id=claim["_id"],
                status="failed",
                finished_at=datetime.now(UTC).isoformat(),
                error=f"{type(e).__name__}: {e}",
            )


async def _claim_next_queued_mc(db: Any) -> dict[str, Any] | None:
    """Atomically flip the oldest queued mc doc to running and return it."""
    now = datetime.now(UTC).isoformat()
    doc = await db[registry.MC_COLLECTION].find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "running", "started_at": now}},
        sort=[("created_at", 1)],
    )
    return doc  # type: ignore[no-any-return]


async def _execute_mc(
    *,
    mc_id: str,
    db: Any,
    settings: Settings,
    state: McWorkersState,
) -> None:
    doc = await registry.get_mc(db, mc_id)
    if doc is None:
        return

    strategy_doc = await strategy_service.get_strategy(db, doc["strategy_id"])
    if strategy_doc is None:
        await _fail_mc(db, mc_id, f"strategy {doc['strategy_id']!r} missing")
        return
    strategy_path = strategy_service.resolve_strategy_path(settings, strategy_doc)
    if not strategy_path.is_file():
        await _fail_mc(db, mc_id, f"strategy file missing: {strategy_path}")
        return

    dataset = await dataset_service.get_dataset(
        db, round_num=doc["round"], day=doc["day"]
    )
    if dataset is None:
        await _fail_mc(
            db,
            mc_id,
            f"dataset r{doc['round']}d{doc['day']} missing",
        )
        return

    try:
        historical = load_round_day(
            doc["round"], doc["day"], dataset_service.dataset_root_for(settings)
        )
    except Exception as e:
        await _fail_mc(db, mc_id, f"failed to load market data: {e}")
        return

    calibration = _maybe_calibrate(doc["generator"], historical)

    generator = resolve_generator(doc["generator"])
    generator_params = dict(doc["generator"])
    generator_params.pop("type", None)

    position_limits_map = _resolve_limits(
        round_num=doc["round"],
        products=historical.products,
        default_limit=doc["position_limit"],
    )

    reference_run_id = await _find_reference_run(db, doc, strategy_doc["sha256"])
    if reference_run_id is not None:
        await db[registry.MC_COLLECTION].update_one(
            {"_id": mc_id}, {"$set": {"reference_run_id": reference_run_id}}
        )

    mc_artifacts.ensure_mc_dir(settings.storage_root, mc_id)

    num_workers = max(1, int(doc.get("num_workers") or 1))
    sem = asyncio.Semaphore(num_workers)
    path_results: list[PathResult | None] = [None] * doc["n_paths"]

    async def _run_one(index: int) -> None:
        async with sem:
            if state.stopping.is_set() or await _is_cancelled(db, mc_id):
                return
            await registry.increment_mc_progress(db, mc_id=mc_id, running=1)
            try:
                result = await asyncio.to_thread(
                    _execute_path_blocking,
                    index=index,
                    strategy_path=strategy_path,
                    strategy_doc=strategy_doc,
                    historical=historical,
                    generator=generator,
                    calibration=calibration,
                    generator_params=generator_params,
                    seed=int(doc["seed"]),
                    matcher_name=doc["matcher"],
                    matcher_mode=doc.get("trade_matching_mode", "all"),
                    position_limits_map=position_limits_map,
                    params=doc.get("params") or {},
                    round_num=doc["round"],
                    day=doc["day"],
                    mc_id=mc_id,
                )
            except Exception as e:
                log.exception("mc path failed", mc_id=mc_id, index=index, err=str(e))
                await registry.update_mc_path(
                    db,
                    mc_id=mc_id,
                    index=index,
                    updates={"status": "failed", "error": f"{type(e).__name__}: {e}"},
                )
                await registry.increment_mc_progress(
                    db, mc_id=mc_id, failed=1, running=-1
                )
                return

            mc_artifacts.write_path_curve(
                settings.storage_root, mc_id, index, result.pnl_curve
            )
            await registry.update_mc_path(
                db,
                mc_id=mc_id,
                index=index,
                updates={
                    "status": "succeeded",
                    "pnl_total": result.metrics.pnl_total,
                    "pnl_by_product": result.metrics.pnl_by_product,
                    "max_drawdown": result.metrics.max_drawdown,
                    "max_inventory_by_product": result.metrics.max_inventory_by_product,
                    "turnover_by_product": result.metrics.turnover_by_product,
                    "num_fills": result.metrics.num_fills,
                    "sharpe_intraday": result.metrics.sharpe_intraday,
                    "duration_ms": result.metrics.duration_ms,
                    "error": None,
                },
            )
            await registry.increment_mc_progress(
                db, mc_id=mc_id, completed=1, running=-1
            )
            path_results[index] = result

    await asyncio.gather(*(_run_one(i) for i in range(doc["n_paths"])))

    if await _is_cancelled(db, mc_id):
        log.info("mc cancelled during run", mc_id=mc_id)
        return

    completed_results = [r for r in path_results if r is not None]
    await _finalize(db, mc_id, settings=settings, path_results=completed_results)


def _execute_path_blocking(
    *,
    index: int,
    strategy_path: Any,
    strategy_doc: dict[str, Any],
    historical: MarketData,
    generator: Any,
    calibration: Any,
    generator_params: dict[str, Any],
    seed: int,
    matcher_name: str,
    matcher_mode: str,
    position_limits_map: dict[str, int],
    params: dict[str, Any],
    round_num: int,
    day: int,
    mc_id: str,
) -> PathResult:
    """Synchronously execute one MC path. Designed to run in a worker thread."""
    rng = rng_for_path(run_seed=seed, path_index=index)
    synthetic = build_synthetic_market_data(
        historical=historical,
        generator=generator,
        calibration=calibration,
        params=generator_params,
        rng=rng,
    )
    # load_trader mutates sys.modules while importing — serialize that step.
    with _STRATEGY_LOAD_LOCK:
        trader = load_trader(strategy_path)
    run_cfg = RunConfig(
        run_id=f"{mc_id}__path{index}",
        strategy_path=strategy_doc["filename"],
        strategy_hash=strategy_doc["sha256"],
        round=round_num,
        day=day,
        matcher_name=matcher_name,
        position_limits=position_limits_map,
        # simulate_day_mc never writes to output_dir; RunConfig just requires a Path.
        output_dir=Path("/tmp/mc-unused"),
        params=params,
    )
    matcher = resolve_matcher(matcher_name, matcher_mode)
    return run_mc_path(
        index=index,
        trader=trader,
        market_data=synthetic,
        matcher=matcher,
        config=run_cfg,
    )


async def _fail_mc(db: Any, mc_id: str, reason: str) -> None:
    await registry.mark_mc_status(
        db,
        mc_id=mc_id,
        status="failed",
        finished_at=datetime.now(UTC).isoformat(),
        error=reason,
    )


async def _is_cancelled(db: Any, mc_id: str) -> bool:
    doc = await registry.get_mc(db, mc_id)
    if doc is None:
        return True
    return doc.get("status") == "cancelled"


async def _finalize(
    db: Any,
    mc_id: str,
    *,
    settings: Settings,
    path_results: list[PathResult],
) -> None:
    from server.services import mc_aggregation

    doc = await registry.get_mc(db, mc_id)
    if doc is None:
        return
    if doc.get("status") in {"cancelled", "failed"}:
        return

    progress = doc.get("progress", {})
    completed = int(progress.get("completed", 0))
    failed = int(progress.get("failed", 0))

    if completed > 0:
        try:
            aggregate = mc_aggregation.compute_aggregate(
                settings.storage_root, mc_id, path_results=path_results
            )
            if aggregate is not None:
                await registry.set_mc_aggregate(
                    db, mc_id=mc_id, aggregate=aggregate
                )
        except Exception as e:
            log.warning("mc aggregate failed", mc_id=mc_id, err=str(e))

    final_status = "failed" if failed > 0 and completed == 0 else "succeeded"
    await registry.mark_mc_status(
        db,
        mc_id=mc_id,
        status=final_status,
        finished_at=datetime.now(UTC).isoformat(),
    )


def _resolve_limits(
    *, round_num: int, products: tuple[str, ...], default_limit: int
) -> dict[str, int]:
    from engine.config.rounds import resolve_limits

    return resolve_limits(round_num, products, default_limit)


def _maybe_calibrate(generator_spec: dict[str, Any], historical: MarketData) -> Any:
    gen_type = generator_spec.get("type")
    if gen_type in {"block_bootstrap", "gbm", "ou"}:
        from engine.montecarlo.calibration import calibrate

        return calibrate(historical)
    return None


async def _find_reference_run(
    db: Any, doc: dict[str, Any], strategy_hash: str
) -> str | None:
    existing = await registry.find_by_strategy_day(
        db,
        strategy_hash=strategy_hash,
        round_num=doc["round"],
        day=doc["day"],
    )
    if existing is None:
        return None
    return str(existing.get("_id"))


async def recover_orphaned_mc(db: Any) -> int:
    """Reset any running mc docs to queued so the worker picks them up."""
    recovered = 0
    cursor = db[registry.MC_COLLECTION].find({"status": "running"})
    async for doc in cursor:
        await db[registry.MC_COLLECTION].update_one(
            {"_id": doc["_id"]}, {"$set": {"status": "queued"}}
        )
        recovered += 1
    return recovered
