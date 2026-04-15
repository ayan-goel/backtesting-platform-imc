"""Execute a backtest via the engine and persist it to Mongo + disk.

Run execution is synchronous inside the POST /runs request handler for Phase 1. A
background queue is a Phase 2 concern.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from engine.config.rounds import resolve_limits
from engine.market.loader import load_round_day
from engine.matching.factory import resolve_matcher
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import load_trader
from server.schemas.runs import RunCreateRequest
from server.services import dataset_service, strategy_service
from server.settings import Settings
from server.storage import artifacts, registry


class DatasetNotFoundError(Exception):
    """Raised when no dataset has been uploaded for the requested (round, day)."""


class StrategyNotFoundError(Exception):
    """Raised when the referenced strategy has not been uploaded."""


class RunBusyError(Exception):
    """Raised when a delete is attempted on a still-running run."""


async def execute_run(
    *,
    req: RunCreateRequest,
    settings: Settings,
    db: Any,
) -> dict[str, Any]:
    """Run a backtest, write artifacts, and upsert the summary doc.

    Idempotent: if a run for the same (strategy sha256, round, day) already exists,
    returns the existing doc without re-running.
    """
    strategy_doc = await strategy_service.get_strategy(db, req.strategy_id)
    if strategy_doc is None:
        raise StrategyNotFoundError(
            f"no strategy {req.strategy_id!r}. upload via POST /strategies first."
        )

    dataset = await dataset_service.get_dataset(db, round_num=req.round, day=req.day)
    if dataset is None:
        raise DatasetNotFoundError(
            f"no dataset uploaded for round={req.round} day={req.day}. "
            "upload it via POST /datasets first."
        )

    strategy_path = strategy_service.resolve_strategy_path(settings, strategy_doc)
    if not strategy_path.is_file():
        # Mongo doc present but file missing — storage drift. Refuse rather than hide it.
        raise StrategyNotFoundError(
            f"strategy file missing on disk for {req.strategy_id!r}: {strategy_path}"
        )
    strategy_hash: str = strategy_doc["sha256"]

    # Study trials bypass the idempotency short-circuit: every trial must
    # produce a distinct run even when strategy_hash/round/day repeat.
    if req.study_id is None:
        existing = await registry.find_by_strategy_day(
            db, strategy_hash=strategy_hash, round_num=req.round, day=req.day
        )
        if existing is not None:
            return existing

    trader = load_trader(strategy_path)
    md = load_round_day(req.round, req.day, dataset_service.dataset_root_for(settings))

    run_id = _build_run_id(strategy_doc["stem"], req.round, req.day, req.trial_number)
    output_dir = (settings.storage_root / "runs" / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    matcher = resolve_matcher(req.matcher, req.trade_matching_mode)
    config = RunConfig(
        run_id=run_id,
        strategy_path=strategy_doc["filename"],  # display name from the upload
        strategy_hash=strategy_hash,
        round=req.round,
        day=req.day,
        matcher_name=req.matcher,
        position_limits=resolve_limits(req.round, md.products, req.position_limit),
        output_dir=output_dir,
        params=req.params,
    )

    result = simulate_day(
        trader=trader, market_data=md, matcher=matcher, config=config
    )

    config_json_path = output_dir / "config.json"
    config_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "strategy_id": req.strategy_id,
                "strategy_filename": strategy_doc["filename"],
                "strategy_hash": strategy_hash,
                "round": req.round,
                "day": req.day,
                "matcher": req.matcher,
                "position_limits": config.position_limits,
                "engine_version": config.engine_version,
                "params": req.params,
            },
            indent=2,
        )
    )

    doc = result.summary.model_dump(by_alias=True)
    doc["strategy_id"] = req.strategy_id
    if req.study_id is not None:
        doc["study_id"] = req.study_id
        doc["trial_number"] = req.trial_number
        doc["params"] = req.params
    await registry.upsert_run(db, doc)
    return doc


async def delete_run(
    *,
    db: Any,
    settings: Settings,
    run_id: str,
) -> bool:
    """Remove a run's Mongo doc + on-disk artifact dir.

    Returns False if the run doesn't exist. Raises RunBusyError if the run
    is currently executing (status='running'). Idempotent on the filesystem
    side — missing dirs are a no-op.
    """
    doc = await registry.get_run(db, run_id)
    if doc is None:
        return False
    if doc.get("status") == "running":
        raise RunBusyError(f"run {run_id!r} is currently running")
    await registry.delete_run(db, run_id)
    artifacts.delete_run_dir(settings.storage_root, run_id)
    return True


def _build_run_id(stem: str, round_num: int, day: int, trial_number: int | None = None) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"{ts}__{stem}__r{round_num}d{day}"
    if trial_number is not None:
        return f"{base}__t{trial_number}"
    return base


