"""Batch creation, lookup, and listing.

A batch groups N (round, day) tasks that run one strategy. Execution is handled
by the background executor in batch_runner.py — this module only writes the
queued batch doc and answers queries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from server.schemas.batches import BatchCreateRequest
from server.services import dataset_service, strategy_service
from server.services.run_service import DatasetNotFoundError, StrategyNotFoundError
from server.settings import Settings
from server.storage import registry


class BatchBusyError(Exception):
    """Raised when a delete is attempted on a still-queued/running batch."""


def _build_batch_id(stem: str, num_tasks: int) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}__{stem}__batch{num_tasks}"


async def create_batch(
    *,
    req: BatchCreateRequest,
    settings: Settings,
    db: Any,
) -> dict[str, Any]:
    """Validate refs and insert a queued batch doc. Raises on missing strategy/dataset."""
    strategy_doc = await strategy_service.get_strategy(db, req.strategy_id)
    if strategy_doc is None:
        raise StrategyNotFoundError(
            f"no strategy {req.strategy_id!r}. upload via POST /strategies first."
        )

    # Confirm every referenced dataset exists before inserting the batch.
    for ds in req.datasets:
        dataset_doc = await dataset_service.get_dataset(
            db, round_num=ds.round, day=ds.day
        )
        if dataset_doc is None:
            raise DatasetNotFoundError(
                f"no dataset uploaded for round={ds.round} day={ds.day}. "
                "upload it via POST /datasets first."
            )

    tasks = [
        {
            "round": ds.round,
            "day": ds.day,
            "status": "queued",
            "run_id": None,
            "error": None,
            "duration_ms": None,
            "pnl_total": None,
        }
        for ds in req.datasets
    ]

    batch_id = _build_batch_id(strategy_doc["stem"], len(tasks))
    doc = {
        "_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": req.strategy_id,
        "strategy_hash": strategy_doc["sha256"],
        "strategy_filename": strategy_doc["filename"],
        "matcher": req.matcher,
        "trade_matching_mode": req.trade_matching_mode,
        "position_limit": req.position_limit,
        "params": req.params,
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "tasks": tasks,
        "progress": {"total": len(tasks), "completed": 0, "failed": 0},
    }
    await registry.insert_batch(db, doc)
    return doc


async def get_batch(db: Any, batch_id: str) -> dict[str, Any] | None:
    return await registry.get_batch(db, batch_id)


async def list_batches(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    return await registry.list_batches(db, skip=skip, limit=limit)


async def delete_batch(*, db: Any, batch_id: str) -> bool:
    """Remove a batch doc. Leaves child runs alone.

    Raises BatchBusyError if the batch is still queued or running.
    """
    doc = await registry.get_batch(db, batch_id)
    if doc is None:
        return False
    if doc.get("status") in {"queued", "running"}:
        raise BatchBusyError(
            f"batch {batch_id!r} is {doc.get('status')}; cancel it first"
        )
    await registry.delete_batch(db, batch_id)
    return True
