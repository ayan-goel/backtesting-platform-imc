"""Mongo collection helpers: `runs` + `datasets` + `strategies` + `batches`. Motor-based, async."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

RUNS_COLLECTION = "runs"
DATASETS_COLLECTION = "datasets"
STRATEGIES_COLLECTION = "strategies"
BATCHES_COLLECTION = "batches"
STUDIES_COLLECTION = "studies"
MC_COLLECTION = "mc_simulations"


async def ensure_indexes(db: Any) -> None:
    """Create indexes idempotently. Called at lifespan startup."""
    runs = db[RUNS_COLLECTION]
    await runs.create_index([("created_at", -1)])
    await runs.create_index([("strategy_path", 1), ("round", 1), ("day", 1)])
    await runs.create_index([("status", 1)])

    datasets = db[DATASETS_COLLECTION]
    await datasets.create_index([("round", 1), ("day", 1)], unique=True)
    await datasets.create_index([("uploaded_at", -1)])

    strategies = db[STRATEGIES_COLLECTION]
    await strategies.create_index([("uploaded_at", -1)])
    await strategies.create_index([("sha256", 1)])

    batches = db[BATCHES_COLLECTION]
    await batches.create_index([("created_at", -1)])
    await batches.create_index([("status", 1)])

    studies = db[STUDIES_COLLECTION]
    await studies.create_index([("created_at", -1)])
    await studies.create_index([("status", 1)])

    mc = db[MC_COLLECTION]
    await mc.create_index([("created_at", -1)])
    await mc.create_index([("status", 1)])
    await mc.create_index([("strategy_id", 1)])


async def insert_run(db: Any, doc: dict[str, Any]) -> None:
    await db[RUNS_COLLECTION].insert_one(doc)


async def upsert_run(db: Any, doc: dict[str, Any]) -> None:
    await db[RUNS_COLLECTION].replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def get_run(db: Any, run_id: str) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await db[RUNS_COLLECTION].find_one({"_id": run_id})
    return doc


async def list_runs(db: Any, *, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    cursor = db[RUNS_COLLECTION].find().sort("created_at", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def find_by_strategy_day(
    db: Any, *, strategy_hash: str, round_num: int, day: int
) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await db[RUNS_COLLECTION].find_one(
        {
            "strategy_hash": strategy_hash,
            "round": round_num,
            "day": day,
        }
    )
    return doc


async def delete_run(db: Any, run_id: str) -> int:
    result = await db[RUNS_COLLECTION].delete_one({"_id": run_id})
    return int(result.deleted_count)


async def find_runs_by_strategy(
    db: Any, *, strategy_id: str
) -> list[dict[str, Any]]:
    cursor = db[RUNS_COLLECTION].find({"strategy_id": strategy_id})
    return [doc async for doc in cursor]


async def find_runs_by_dataset(
    db: Any, *, round_num: int, day: int
) -> list[dict[str, Any]]:
    cursor = db[RUNS_COLLECTION].find({"round": round_num, "day": day})
    return [doc async for doc in cursor]


async def count_runs_by_strategy(db: Any, *, strategy_id: str) -> int:
    return int(
        await db[RUNS_COLLECTION].count_documents({"strategy_id": strategy_id})
    )


async def count_runs_by_dataset(db: Any, *, round_num: int, day: int) -> int:
    return int(
        await db[RUNS_COLLECTION].count_documents({"round": round_num, "day": day})
    )


async def count_batches_by_strategy(db: Any, *, strategy_id: str) -> int:
    return int(
        await db[BATCHES_COLLECTION].count_documents({"strategy_id": strategy_id})
    )


async def count_batches_by_dataset(db: Any, *, round_num: int, day: int) -> int:
    return int(
        await db[BATCHES_COLLECTION].count_documents(
            {"tasks": {"$elemMatch": {"round": round_num, "day": day}}}
        )
    )


async def count_studies_by_strategy(db: Any, *, strategy_id: str) -> int:
    return int(
        await db[STUDIES_COLLECTION].count_documents({"strategy_id": strategy_id})
    )


async def count_studies_by_dataset(db: Any, *, round_num: int, day: int) -> int:
    return int(
        await db[STUDIES_COLLECTION].count_documents(
            {"round": round_num, "day": day}
        )
    )


async def find_batches_by_strategy(
    db: Any, *, strategy_id: str
) -> list[dict[str, Any]]:
    cursor = db[BATCHES_COLLECTION].find({"strategy_id": strategy_id})
    return [doc async for doc in cursor]


async def find_batches_by_dataset(
    db: Any, *, round_num: int, day: int
) -> list[dict[str, Any]]:
    cursor = db[BATCHES_COLLECTION].find(
        {"tasks": {"$elemMatch": {"round": round_num, "day": day}}}
    )
    return [doc async for doc in cursor]


async def find_studies_by_strategy(
    db: Any, *, strategy_id: str
) -> list[dict[str, Any]]:
    cursor = db[STUDIES_COLLECTION].find({"strategy_id": strategy_id})
    return [doc async for doc in cursor]


async def find_studies_by_dataset(
    db: Any, *, round_num: int, day: int
) -> list[dict[str, Any]]:
    cursor = db[STUDIES_COLLECTION].find({"round": round_num, "day": day})
    return [doc async for doc in cursor]


async def delete_batch(db: Any, batch_id: str) -> int:
    result = await db[BATCHES_COLLECTION].delete_one({"_id": batch_id})
    return int(result.deleted_count)


async def delete_study(db: Any, study_id: str) -> int:
    result = await db[STUDIES_COLLECTION].delete_one({"_id": study_id})
    return int(result.deleted_count)


# ---- datasets ----------------------------------------------------------------


async def upsert_dataset(db: Any, doc: dict[str, Any]) -> None:
    await db[DATASETS_COLLECTION].replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def get_dataset(db: Any, *, round_num: int, day: int) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await db[DATASETS_COLLECTION].find_one(
        {"round": round_num, "day": day}
    )
    return doc


async def list_datasets(db: Any) -> list[dict[str, Any]]:
    cursor = db[DATASETS_COLLECTION].find().sort([("round", 1), ("day", 1)])
    return [doc async for doc in cursor]


async def delete_dataset(db: Any, *, round_num: int, day: int) -> int:
    result = await db[DATASETS_COLLECTION].delete_one(
        {"round": round_num, "day": day}
    )
    return int(result.deleted_count)


# ---- strategies --------------------------------------------------------------


async def upsert_strategy(db: Any, doc: dict[str, Any]) -> None:
    await db[STRATEGIES_COLLECTION].replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def get_strategy(db: Any, strategy_id: str) -> dict[str, Any] | None:
    doc: dict[str, Any] | None = await db[STRATEGIES_COLLECTION].find_one(
        {"_id": strategy_id}
    )
    return doc


async def list_strategies(db: Any) -> list[dict[str, Any]]:
    cursor = db[STRATEGIES_COLLECTION].find().sort("uploaded_at", -1)
    return [doc async for doc in cursor]


async def delete_strategy(db: Any, strategy_id: str) -> int:
    result = await db[STRATEGIES_COLLECTION].delete_one({"_id": strategy_id})
    return int(result.deleted_count)


# ---- batches -----------------------------------------------------------------


async def insert_batch(db: Any, doc: dict[str, Any]) -> None:
    await db[BATCHES_COLLECTION].insert_one(doc)


async def get_batch(db: Any, batch_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await db[BATCHES_COLLECTION].find_one({"_id": batch_id})
    return result


async def list_batches(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    cursor = (
        db[BATCHES_COLLECTION].find().sort("created_at", -1).skip(skip).limit(limit)
    )
    return [doc async for doc in cursor]


async def update_batch_task(
    db: Any,
    *,
    batch_id: str,
    round_num: int,
    day: int,
    updates: dict[str, Any],
) -> int:
    """Atomically mutate a single task inside a batch doc.

    `updates` keys are applied as `tasks.$.<key>` via $set. Returns the
    modified_count so callers can assert the match.
    """
    set_doc = {f"tasks.$.{k}": v for k, v in updates.items()}
    result = await db[BATCHES_COLLECTION].update_one(
        {
            "_id": batch_id,
            "tasks": {"$elemMatch": {"round": round_num, "day": day}},
        },
        {"$set": set_doc},
    )
    return int(result.modified_count)


async def mark_batch_status(
    db: Any,
    *,
    batch_id: str,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> int:
    updates: dict[str, Any] = {"status": status}
    if started_at is not None:
        updates["started_at"] = started_at
    if finished_at is not None:
        updates["finished_at"] = finished_at
    result = await db[BATCHES_COLLECTION].update_one(
        {"_id": batch_id}, {"$set": updates}
    )
    return int(result.modified_count)


async def increment_batch_progress(
    db: Any, *, batch_id: str, succeeded: int = 0, failed: int = 0
) -> int:
    inc: dict[str, int] = {}
    if succeeded:
        inc["progress.completed"] = succeeded
    if failed:
        inc["progress.failed"] = failed
    if not inc:
        return 0
    result = await db[BATCHES_COLLECTION].update_one({"_id": batch_id}, {"$inc": inc})
    return int(result.modified_count)


async def claim_next_queued_task(db: Any) -> dict[str, Any] | None:
    """Atomically find one queued task in any batch and mark it running.

    Returns `{batch_id, round, day, strategy_id, matcher, position_limit, params}`
    for the executor to act on, or None if nothing is queued. Uses the
    positional `$` operator so a single write updates the matched task and
    bumps batch status + started_at in one atomic step.
    """
    now = datetime.now(UTC).isoformat()
    doc = await db[BATCHES_COLLECTION].find_one_and_update(
        {
            "status": {"$in": ["queued", "running"]},
            "tasks": {"$elemMatch": {"status": "queued"}},
        },
        {
            "$set": {
                "tasks.$.status": "running",
                "status": "running",
                "started_at": now,
            }
        },
        sort=[("created_at", 1)],
    )
    if doc is None:
        return None

    # `doc` is the pre-update document — find the first queued task, which is
    # the one the positional $ operator just flipped to running.
    task = next((t for t in doc.get("tasks", []) if t.get("status") == "queued"), None)
    if task is None:
        return None
    return {
        "batch_id": doc["_id"],
        "round": task["round"],
        "day": task["day"],
        "strategy_id": doc["strategy_id"],
        "matcher": doc["matcher"],
        "trade_matching_mode": doc.get("trade_matching_mode", "all"),
        "position_limit": doc["position_limit"],
        "params": doc.get("params", {}),
    }


# ---- studies -----------------------------------------------------------------


async def insert_study(db: Any, doc: dict[str, Any]) -> None:
    await db[STUDIES_COLLECTION].insert_one(doc)


async def get_study(db: Any, study_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await db[STUDIES_COLLECTION].find_one({"_id": study_id})
    return result


async def list_studies(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    cursor = (
        db[STUDIES_COLLECTION].find().sort("created_at", -1).skip(skip).limit(limit)
    )
    return [doc async for doc in cursor]


async def mark_study_status(
    db: Any,
    *,
    study_id: str,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> int:
    updates: dict[str, Any] = {"status": status}
    if started_at is not None:
        updates["started_at"] = started_at
    if finished_at is not None:
        updates["finished_at"] = finished_at
    result = await db[STUDIES_COLLECTION].update_one(
        {"_id": study_id}, {"$set": updates}
    )
    return int(result.modified_count)


async def increment_study_progress(
    db: Any,
    *,
    study_id: str,
    completed: int = 0,
    failed: int = 0,
    running: int = 0,
) -> int:
    inc: dict[str, int] = {}
    if completed:
        inc["progress.completed"] = completed
    if failed:
        inc["progress.failed"] = failed
    if running:
        inc["progress.running"] = running
    if not inc:
        return 0
    result = await db[STUDIES_COLLECTION].update_one({"_id": study_id}, {"$inc": inc})
    return int(result.modified_count)


# ---- mc simulations ---------------------------------------------------------


async def insert_mc(db: Any, doc: dict[str, Any]) -> None:
    await db[MC_COLLECTION].insert_one(doc)


async def get_mc(db: Any, mc_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await db[MC_COLLECTION].find_one({"_id": mc_id})
    return result


async def list_mc(
    db: Any, *, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    cursor = db[MC_COLLECTION].find().sort("created_at", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def delete_mc(db: Any, mc_id: str) -> int:
    result = await db[MC_COLLECTION].delete_one({"_id": mc_id})
    return int(result.deleted_count)


async def mark_mc_status(
    db: Any,
    *,
    mc_id: str,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    error: str | None = None,
) -> int:
    updates: dict[str, Any] = {"status": status}
    if started_at is not None:
        updates["started_at"] = started_at
    if finished_at is not None:
        updates["finished_at"] = finished_at
    if error is not None:
        updates["error"] = error
    result = await db[MC_COLLECTION].update_one({"_id": mc_id}, {"$set": updates})
    return int(result.modified_count)


async def update_mc_path(
    db: Any,
    *,
    mc_id: str,
    index: int,
    updates: dict[str, Any],
) -> int:
    set_doc = {f"paths.$.{k}": v for k, v in updates.items()}
    result = await db[MC_COLLECTION].update_one(
        {"_id": mc_id, "paths": {"$elemMatch": {"index": index}}},
        {"$set": set_doc},
    )
    return int(result.modified_count)


async def increment_mc_progress(
    db: Any,
    *,
    mc_id: str,
    completed: int = 0,
    failed: int = 0,
    running: int = 0,
) -> int:
    inc: dict[str, int] = {}
    if completed:
        inc["progress.completed"] = completed
    if failed:
        inc["progress.failed"] = failed
    if running:
        inc["progress.running"] = running
    if not inc:
        return 0
    result = await db[MC_COLLECTION].update_one({"_id": mc_id}, {"$inc": inc})
    return int(result.modified_count)


async def set_mc_aggregate(
    db: Any, *, mc_id: str, aggregate: dict[str, Any]
) -> int:
    result = await db[MC_COLLECTION].update_one(
        {"_id": mc_id}, {"$set": {"aggregate": aggregate}}
    )
    return int(result.modified_count)


async def find_mc_by_strategy(
    db: Any, *, strategy_id: str
) -> list[dict[str, Any]]:
    cursor = db[MC_COLLECTION].find({"strategy_id": strategy_id})
    return [doc async for doc in cursor]


async def find_mc_by_dataset(
    db: Any, *, round_num: int, day: int
) -> list[dict[str, Any]]:
    cursor = db[MC_COLLECTION].find({"round": round_num, "day": day})
    return [doc async for doc in cursor]


async def update_study_best(
    db: Any,
    *,
    study_id: str,
    direction: str,
    trial: dict[str, Any],
) -> bool:
    """Replace best_trial iff the new trial beats the existing best.

    Returns True if updated. `direction` is 'maximize' or 'minimize'.
    """
    study = await get_study(db, study_id)
    if study is None:
        return False
    existing = study.get("best_trial")
    new_value = float(trial["value"])
    if existing is not None:
        existing_value = float(existing["value"])
        if direction == "maximize" and new_value <= existing_value:
            return False
        if direction == "minimize" and new_value >= existing_value:
            return False
    await db[STUDIES_COLLECTION].update_one(
        {"_id": study_id}, {"$set": {"best_trial": trial}}
    )
    return True
