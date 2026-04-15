"""Dataset upload, listing, and lookup.

Datasets are (round, day) pairs of CSVs that the dashboard uploads. The dashboard
hands us a bag of files (drag-and-dropped folder contents); we parse each filename
to extract its (kind, round, day), pair them up, write them to `{storage_root}/data/`,
then validate by invoking the loader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from engine.errors import InvalidMarketDataError
from engine.market.loader import load_round_day
from server.settings import Settings
from server.storage import artifacts, registry


class DatasetBusyError(Exception):
    """Raised when a delete is attempted on a dataset with running dependents."""

_FILENAME_RE = re.compile(r"^(?P<kind>prices|trades)_round_(?P<round>-?\d+)_day_(?P<day>-?\d+)\.csv$")


@dataclass(frozen=True, slots=True)
class _ParsedFile:
    kind: Literal["prices", "trades"]
    round_num: int
    day: int
    filename: str
    content: bytes


def _parse_filename(name: str, content: bytes) -> _ParsedFile | None:
    base = Path(name).name
    m = _FILENAME_RE.match(base)
    if m is None:
        return None
    kind = m.group("kind")
    assert kind in ("prices", "trades")
    return _ParsedFile(
        kind=kind,  # type: ignore[arg-type]
        round_num=int(m.group("round")),
        day=int(m.group("day")),
        filename=base,
        content=content,
    )


def _dataset_id(round_num: int, day: int) -> str:
    return f"r{round_num}d{day}"


async def upload_datasets(
    *,
    files: list[tuple[str, bytes]],
    settings: Settings,
    db: Any,
) -> dict[str, Any]:
    """Accept a bag of files, pair them by (round, day), and upsert each complete pair.

    Returns a summary dict with `uploaded` (list of docs), `skipped` (list of reasons).
    Unrecognized filenames and unpaired files are skipped without aborting the batch.
    Any pair that fails loader validation rolls back its own files and is reported.
    """
    pairs: dict[tuple[int, int], dict[str, _ParsedFile]] = {}
    skipped: list[dict[str, str]] = []

    for name, content in files:
        parsed = _parse_filename(name, content)
        if parsed is None:
            skipped.append({"filename": name, "reason": "unrecognized filename"})
            continue
        bucket = pairs.setdefault((parsed.round_num, parsed.day), {})
        bucket[parsed.kind] = parsed

    datasets_dir = settings.datasets_dir.resolve()
    datasets_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, Any]] = []

    for (round_num, day), bucket in sorted(pairs.items()):
        prices = bucket.get("prices")
        trades = bucket.get("trades")
        if prices is None or trades is None:
            missing = "prices" if prices is None else "trades"
            present = bucket[next(iter(bucket))].filename
            skipped.append(
                {"filename": present, "reason": f"missing matching {missing} file"}
            )
            continue

        prices_path = datasets_dir / prices.filename
        trades_path = datasets_dir / trades.filename
        prices_path.write_bytes(prices.content)
        trades_path.write_bytes(trades.content)

        try:
            md = load_round_day(round_num, day, datasets_dir)
        except InvalidMarketDataError as e:
            prices_path.unlink(missing_ok=True)
            trades_path.unlink(missing_ok=True)
            skipped.append(
                {"filename": prices.filename, "reason": f"invalid dataset: {e}"}
            )
            continue

        doc = {
            "_id": _dataset_id(round_num, day),
            "round": round_num,
            "day": day,
            "uploaded_at": datetime.now(UTC).isoformat(),
            "products": list(md.products),
            "num_timestamps": len(md.timestamps),
            "prices_filename": prices_path.name,
            "trades_filename": trades_path.name,
            "prices_bytes": len(prices.content),
            "trades_bytes": len(trades.content),
            # Persist the raw CSV bytes so datasets survive ephemeral-
            # filesystem restarts (Heroku/Railway wipe /app/storage on every
            # boot). ensure_dataset_on_disk rehydrates from this when the
            # files are missing at read time.
            "prices_content": prices.content,
            "trades_content": trades.content,
        }
        await registry.upsert_dataset(db, doc)
        uploaded.append(doc)

    return {"uploaded": uploaded, "skipped": skipped}


async def list_datasets(db: Any) -> list[dict[str, Any]]:
    return await registry.list_datasets(db)


async def get_dataset(db: Any, *, round_num: int, day: int) -> dict[str, Any] | None:
    return await registry.get_dataset(db, round_num=round_num, day=day)


async def delete_dataset(
    *,
    round_num: int,
    day: int,
    settings: Settings,
    db: Any,
) -> bool:
    """Cascading delete: dataset + runs at (round, day) + batches touching
    that (round, day) + studies at (round, day).

    Refuses if any dependent batch or study is still queued/running.
    Returns True if the dataset existed.
    """
    doc = await registry.get_dataset(db, round_num=round_num, day=day)
    if doc is None:
        return False

    # Pre-check: any active dependent blocks delete.
    batches = await registry.find_batches_by_dataset(
        db, round_num=round_num, day=day
    )
    for b in batches:
        if b.get("status") in {"queued", "running"}:
            raise DatasetBusyError(
                f"dataset r{round_num}d{day} has an active batch "
                f"{b['_id']!r}; cancel it first"
            )
    studies = await registry.find_studies_by_dataset(
        db, round_num=round_num, day=day
    )
    for s in studies:
        if s.get("status") in {"queued", "running"}:
            raise DatasetBusyError(
                f"dataset r{round_num}d{day} has an active study "
                f"{s['_id']!r}; cancel it first"
            )

    # Cascade child runs + their artifact dirs.
    runs = await registry.find_runs_by_dataset(db, round_num=round_num, day=day)
    for run in runs:
        await registry.delete_run(db, run["_id"])
        artifacts.delete_run_dir(settings.storage_root, run["_id"])

    # Cascade child batches.
    for b in batches:
        await registry.delete_batch(db, b["_id"])

    # Cascade child studies + SQLite files.
    for s in studies:
        storage_subpath = s.get("storage_path")
        if storage_subpath:
            (settings.storage_root / storage_subpath).unlink(missing_ok=True)
        await registry.delete_study(db, s["_id"])

    # Finally: delete CSV files + the dataset doc itself.
    datasets_dir = settings.datasets_dir.resolve()
    for key in ("prices_filename", "trades_filename"):
        name = doc.get(key)
        if name:
            (datasets_dir / name).unlink(missing_ok=True)
    deleted = await registry.delete_dataset(db, round_num=round_num, day=day)
    return deleted > 0


def dataset_root_for(settings: Settings) -> Path:
    """Directory passed as `data_root` to `load_round_day` at run time."""
    return settings.datasets_dir.resolve()


def ensure_dataset_on_disk(settings: Settings, doc: dict[str, Any]) -> Path:
    """Return the dataset directory, rehydrating CSVs from Mongo if wiped.

    Mirrors `strategy_service.ensure_strategy_on_disk`: on ephemeral
    filesystems the uploaded CSVs disappear on every restart, but the
    Mongo doc persists along with the raw content bytes. When the files
    are missing, write them back to disk from `prices_content` /
    `trades_content` before handing the path to `load_round_day`.

    Raises InvalidMarketDataError if the files are missing *and* the
    Mongo doc predates the backfill (no `prices_content` field).
    """
    datasets_dir = dataset_root_for(settings)
    datasets_dir.mkdir(parents=True, exist_ok=True)
    prices_name = doc.get("prices_filename")
    trades_name = doc.get("trades_filename")
    if not prices_name or not trades_name:
        raise InvalidMarketDataError(
            f"dataset doc {doc.get('_id')!r} is missing filename fields"
        )

    prices_path = datasets_dir / prices_name
    trades_path = datasets_dir / trades_name
    missing = [p for p in (prices_path, trades_path) if not p.is_file()]
    if not missing:
        return datasets_dir

    prices_content = doc.get("prices_content")
    trades_content = doc.get("trades_content")
    if prices_content is None or trades_content is None:
        raise InvalidMarketDataError(
            f"dataset {doc.get('_id')!r} files are missing on disk and the "
            "Mongo doc has no cached content. Re-upload the dataset via "
            "POST /datasets."
        )

    def _coerce(raw: object, label: str) -> bytes:
        if isinstance(raw, bytes | bytearray | memoryview):
            return bytes(raw)
        raise InvalidMarketDataError(
            f"cached {label} has unsupported type {type(raw).__name__}; "
            "re-upload the dataset"
        )

    prices_path.write_bytes(_coerce(prices_content, "prices_content"))
    trades_path.write_bytes(_coerce(trades_content, "trades_content"))
    return datasets_dir
