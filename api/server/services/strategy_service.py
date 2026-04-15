"""Strategy upload, listing, and lookup.

Strategies are Python files containing a `Trader` class. Uploads are content-addressed
by SHA-256: the same file uploaded twice is the same document. Validation happens at
upload time by actually calling `load_trader` against the bundled `datamodel` compat
module — if it can't be loaded, we reject with a 400.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.errors import StrategyLoadError
from engine.simulator.strategy_loader import load_trader
from server.settings import Settings
from server.storage import artifacts, registry

STRATEGIES_SUBDIR = "strategies"


class StrategyBusyError(Exception):
    """Raised when a delete is attempted on a strategy that has running work."""


def _strategies_dir(settings: Settings) -> Path:
    return (settings.storage_root / STRATEGIES_SUBDIR).resolve()


def _build_id(stem: str, sha256_hex: str) -> str:
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem) or "strategy"
    return f"{safe_stem}-{sha256_hex[:8]}"


async def upload_strategy(
    *,
    filename: str,
    content: bytes,
    settings: Settings,
    db: Any,
) -> dict[str, Any]:
    """Persist a strategy file. Returns the Mongo doc.

    Raises StrategyLoadError if the file does not contain a valid `Trader` class.
    Idempotent: re-uploading the same byte content returns the existing doc.
    """
    if not filename.endswith(".py"):
        raise StrategyLoadError(f"strategy filename must end in .py, got {filename!r}")

    stem = Path(filename).stem
    sha256_hex = hashlib.sha256(content).hexdigest()
    strategy_id = _build_id(stem, sha256_hex)

    strategies_dir = _strategies_dir(settings)
    strategies_dir.mkdir(parents=True, exist_ok=True)
    storage_path = strategies_dir / f"{strategy_id}.py"

    # Write the file before validating so load_trader can read it.
    storage_path.write_bytes(content)

    try:
        load_trader(storage_path)
    except StrategyLoadError:
        storage_path.unlink(missing_ok=True)
        raise

    doc = {
        "_id": strategy_id,
        "filename": filename,
        "stem": stem,
        "sha256": f"sha256:{sha256_hex}",
        "uploaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": len(content),
        "storage_subpath": f"{STRATEGIES_SUBDIR}/{storage_path.name}",
    }
    await registry.upsert_strategy(db, doc)
    return doc


async def list_strategies(db: Any) -> list[dict[str, Any]]:
    return await registry.list_strategies(db)


async def get_strategy(db: Any, strategy_id: str) -> dict[str, Any] | None:
    return await registry.get_strategy(db, strategy_id)


async def delete_strategy(
    *, strategy_id: str, settings: Settings, db: Any
) -> bool:
    """Cascading delete: strategy + all runs + all batches + all studies.

    Refuses if any dependent batch or study is still queued/running. The
    caller is expected to cancel those first. Child runs are deleted via
    run_service.delete_run so their artifact dirs are wiped. Child studies
    have their SQLite files removed. The strategy file on disk is removed
    last.

    Returns True if the strategy existed (and therefore was deleted); False
    if it was not found.
    """
    doc = await registry.get_strategy(db, strategy_id)
    if doc is None:
        return False

    # Pre-check: refuse if any dependent batch/study is active.
    batches = await registry.find_batches_by_strategy(db, strategy_id=strategy_id)
    for b in batches:
        if b.get("status") in {"queued", "running"}:
            raise StrategyBusyError(
                f"strategy {strategy_id!r} has an active batch {b['_id']!r}; "
                "cancel it first"
            )
    studies = await registry.find_studies_by_strategy(db, strategy_id=strategy_id)
    for s in studies:
        if s.get("status") in {"queued", "running"}:
            raise StrategyBusyError(
                f"strategy {strategy_id!r} has an active study {s['_id']!r}; "
                "cancel it first"
            )

    # Cascade: runs first (so artifact dirs get wiped before the Mongo
    # doc disappears), then batches, then studies, then the strategy itself.
    runs = await registry.find_runs_by_strategy(db, strategy_id=strategy_id)
    for run in runs:
        await registry.delete_run(db, run["_id"])
        artifacts.delete_run_dir(settings.storage_root, run["_id"])

    for b in batches:
        await registry.delete_batch(db, b["_id"])

    for s in studies:
        storage_subpath = s.get("storage_path")
        if storage_subpath:
            (settings.storage_root / storage_subpath).unlink(missing_ok=True)
        await registry.delete_study(db, s["_id"])

    deleted = await registry.delete_strategy(db, strategy_id)
    storage_path = resolve_strategy_path(settings, doc)
    storage_path.unlink(missing_ok=True)
    return deleted > 0


def resolve_strategy_path(settings: Settings, doc: dict[str, Any]) -> Path:
    """Return the absolute filesystem path to the uploaded strategy file."""
    subpath: str = doc["storage_subpath"]
    return (settings.storage_root / subpath).resolve()
