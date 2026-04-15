"""Disk artifact readers for run outputs.

Layout: storage/runs/<run_id>/{events.jsonl, config.json, stdout.txt}
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def run_dir(storage_root: Path, run_id: str) -> Path:
    return storage_root / "runs" / run_id


def delete_run_dir(storage_root: Path, run_id: str) -> None:
    """Remove a run's on-disk artifacts. Idempotent — missing paths are a no-op."""
    path = run_dir(storage_root, run_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def read_config(storage_root: Path, run_id: str) -> dict[str, Any] | None:
    path = run_dir(storage_root, run_id) / "config.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def iter_events(
    storage_root: Path,
    run_id: str,
    *,
    product: str | None = None,
    ts_from: int | None = None,
    ts_to: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    stride: int = 1,
) -> Iterator[dict[str, Any]]:
    """Stream matching event records line-by-line. `ts_to` is exclusive.

    `stride=N` emits every Nth event per product (after other filters),
    always including the first and last event per product so the caller
    can still draw an accurate chart domain. `stride=1` is a no-op.
    """
    path = run_dir(storage_root, run_id) / "events.jsonl"
    if not path.is_file():
        return
    if stride < 1:
        stride = 1

    yielded = 0
    skipped = 0
    counter_by_product: dict[str, int] = {}
    last_skipped_by_product: dict[str, tuple[int, dict[str, Any]]] = {}
    last_emitted_ts_by_product: dict[str, int] = {}

    def _hit_limit() -> bool:
        return limit is not None and yielded >= limit

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            rec_product = record.get("product")
            if product is not None and rec_product != product:
                continue
            ts = int(record["ts"])
            if ts_from is not None and ts < ts_from:
                continue
            if ts_to is not None and ts >= ts_to:
                continue
            if skipped < offset:
                skipped += 1
                continue

            if stride > 1:
                idx = counter_by_product.get(rec_product, 0)
                counter_by_product[rec_product] = idx + 1
                if idx % stride != 0:
                    last_skipped_by_product[rec_product] = (ts, record)
                    continue

            yield record
            yielded += 1
            last_emitted_ts_by_product[rec_product] = ts
            last_skipped_by_product.pop(rec_product, None)
            if _hit_limit():
                return

    # Trailing flush: make sure the last event per product is always emitted
    # so chart domains reflect the true end of the run.
    if stride > 1:
        for prod, (ts, rec) in last_skipped_by_product.items():
            if _hit_limit():
                return
            if last_emitted_ts_by_product.get(prod, -1) >= ts:
                continue
            yield rec
            yielded += 1


def count_events(storage_root: Path, run_id: str) -> int:
    path = run_dir(storage_root, run_id) / "events.jsonl"
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())
