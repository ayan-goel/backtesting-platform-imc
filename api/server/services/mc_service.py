"""Monte Carlo simulation creation, lookup, and listing.

Creates a queued mc_simulations doc; the background runner in
`mc_runner.py` picks it up and drives the paths to completion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from server.schemas.mc import McCreateRequest
from server.services import dataset_service, strategy_service
from server.services.run_service import (
    DatasetNotFoundError,
    StrategyNotFoundError,
)
from server.settings import Settings
from server.storage import mc_artifacts, registry


class McBusyError(Exception):
    """Raised when a delete is attempted on a still-queued/running mc simulation."""


def _build_mc_id(stem: str, round_num: int, day: int, n_paths: int) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}__{stem}__r{round_num}d{day}__mc{n_paths}"


async def create_mc_simulation(
    *,
    req: McCreateRequest,
    settings: Settings,
    db: Any,
) -> dict[str, Any]:
    """Validate refs, insert a queued mc doc, return it.

    Raises StrategyNotFoundError / DatasetNotFoundError on missing refs.
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

    strategy_path = strategy_service.resolve_strategy_path(settings, strategy_doc)
    if not strategy_path.is_file():
        raise StrategyNotFoundError(
            f"strategy file missing on disk for {req.strategy_id!r}: {strategy_path}"
        )

    mc_id = _build_mc_id(strategy_doc["stem"], req.round, req.day, req.n_paths)

    generator_spec = req.generator.model_dump()
    doc: dict[str, Any] = {
        "_id": mc_id,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": req.strategy_id,
        "strategy_hash": strategy_doc["sha256"],
        "strategy_filename": strategy_doc["filename"],
        "round": req.round,
        "day": req.day,
        "matcher": req.matcher,
        "trade_matching_mode": req.trade_matching_mode,
        "position_limit": req.position_limit,
        "params": req.params,
        "generator": generator_spec,
        "n_paths": req.n_paths,
        "seed": req.seed,
        "num_workers": req.num_workers,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "progress": {
            "total": req.n_paths,
            "completed": 0,
            "failed": 0,
            "running": 0,
        },
        "paths": [{"index": i, "status": "queued"} for i in range(req.n_paths)],
        "aggregate": None,
        "reference_run_id": None,
        "error": None,
    }

    mc_artifacts.write_config(settings.storage_root, mc_id, {
        "mc_id": mc_id,
        "strategy_id": req.strategy_id,
        "strategy_filename": strategy_doc["filename"],
        "strategy_hash": strategy_doc["sha256"],
        "round": req.round,
        "day": req.day,
        "matcher": req.matcher,
        "trade_matching_mode": req.trade_matching_mode,
        "position_limit": req.position_limit,
        "params": req.params,
        "generator": generator_spec,
        "n_paths": req.n_paths,
        "seed": req.seed,
        "num_workers": req.num_workers,
    })

    await registry.insert_mc(db, doc)
    return doc


async def get_mc_simulation(db: Any, mc_id: str) -> dict[str, Any] | None:
    return await registry.get_mc(db, mc_id)


async def list_mc_simulations(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    return await registry.list_mc(db, skip=skip, limit=limit)


async def cancel_mc_simulation(db: Any, mc_id: str) -> dict[str, Any] | None:
    doc = await registry.get_mc(db, mc_id)
    if doc is None:
        return None
    if doc.get("status") in {"queued", "running"}:
        await registry.mark_mc_status(
            db,
            mc_id=mc_id,
            status="cancelled",
            finished_at=datetime.now(UTC).isoformat(),
        )
        return await registry.get_mc(db, mc_id)
    return doc


async def delete_mc_simulation(
    *, db: Any, settings: Settings, mc_id: str
) -> bool:
    doc = await registry.get_mc(db, mc_id)
    if doc is None:
        return False
    if doc.get("status") in {"queued", "running"}:
        raise McBusyError(
            f"mc simulation {mc_id!r} is {doc.get('status')}; cancel it first"
        )
    await registry.delete_mc(db, mc_id)
    mc_artifacts.delete_mc_dir(settings.storage_root, mc_id)
    return True
