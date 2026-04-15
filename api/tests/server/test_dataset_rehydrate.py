"""Tests for `ensure_dataset_on_disk` rehydration.

Mirrors test_strategy_rehydrate.py. Heroku/Railway-style deploys wipe
`/app/storage/data` on every restart; without caching the raw CSV
bytes in Mongo, any run/batch/MC that tries to load the dataset after a
restart fails with "prices file not found".
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from engine.errors import InvalidMarketDataError
from server.services import dataset_service
from server.settings import get_settings


@pytest.mark.asyncio
async def test_upload_persists_csv_bytes_in_doc(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    prices_bytes = _minimal_prices(day=0)
    trades_bytes = _minimal_trades()

    result = await dataset_service.upload_datasets(
        files=[
            ("prices_round_9_day_0.csv", prices_bytes),
            ("trades_round_9_day_0.csv", trades_bytes),
        ],
        settings=settings,
        db=db,
    )
    assert len(result["uploaded"]) == 1
    stored = await db["datasets"].find_one({"_id": "r9d0"})
    assert stored is not None
    assert stored["prices_content"] == prices_bytes
    assert stored["trades_content"] == trades_bytes


@pytest.mark.asyncio
async def test_rehydrate_restores_csvs_when_wiped(test_app: FastAPI) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    prices_bytes = _minimal_prices(day=0)
    trades_bytes = _minimal_trades()

    await dataset_service.upload_datasets(
        files=[
            ("prices_round_9_day_0.csv", prices_bytes),
            ("trades_round_9_day_0.csv", trades_bytes),
        ],
        settings=settings,
        db=db,
    )
    datasets_dir = settings.datasets_dir.resolve()
    prices_path = datasets_dir / "prices_round_9_day_0.csv"
    trades_path = datasets_dir / "trades_round_9_day_0.csv"
    assert prices_path.is_file() and trades_path.is_file()

    # Simulate ephemeral-fs wipe.
    prices_path.unlink()
    trades_path.unlink()

    doc = await db["datasets"].find_one({"_id": "r9d0"})
    assert doc is not None
    returned_dir = dataset_service.ensure_dataset_on_disk(settings, doc)
    assert returned_dir == datasets_dir
    assert prices_path.is_file()
    assert trades_path.is_file()
    assert prices_path.read_bytes() == prices_bytes
    assert trades_path.read_bytes() == trades_bytes


def test_rehydrate_raises_for_doc_without_cached_content(test_app: FastAPI) -> None:
    settings = get_settings()
    ghost: dict[str, Any] = {
        "_id": "r9d0",
        "round": 9,
        "day": 0,
        "uploaded_at": "2026-01-01T00:00:00Z",
        "products": ["EMERALDS"],
        "num_timestamps": 100,
        "prices_filename": "prices_round_9_day_0.csv",
        "trades_filename": "trades_round_9_day_0.csv",
        "prices_bytes": 10,
        "trades_bytes": 10,
    }
    with pytest.raises(InvalidMarketDataError, match="Re-upload"):
        dataset_service.ensure_dataset_on_disk(settings, ghost)


@pytest.mark.asyncio
async def test_run_succeeds_after_filesystem_wipe(test_app: FastAPI) -> None:
    """End-to-end: upload dataset + strategy, wipe everything, submit a run
    via execute_run — it should rehydrate both and succeed.
    """
    import hashlib
    from datetime import UTC, datetime

    from server.schemas.runs import RunCreateRequest
    from server.services import run_service

    db = test_app.state.mongo_db
    settings = get_settings()

    prices_bytes = _minimal_prices(day=0)
    trades_bytes = _minimal_trades()
    await dataset_service.upload_datasets(
        files=[
            ("prices_round_9_day_0.csv", prices_bytes),
            ("trades_round_9_day_0.csv", trades_bytes),
        ],
        settings=settings,
        db=db,
    )

    strategy_content = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""
    sha = hashlib.sha256(strategy_content).hexdigest()
    stem = "noop"
    strategies_dir = settings.storage_root / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    storage_path = strategies_dir / f"{stem}-{sha[:8]}.py"
    storage_path.write_bytes(strategy_content)
    await db["strategies"].insert_one({
        "_id": f"{stem}-{sha[:8]}",
        "filename": "noop.py",
        "stem": stem,
        "sha256": f"sha256:{sha}",
        "uploaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": len(strategy_content),
        "storage_subpath": f"strategies/{storage_path.name}",
        "source_bytes": strategy_content,
    })

    # Wipe BOTH strategy file and dataset files.
    datasets_dir = settings.datasets_dir.resolve()
    (datasets_dir / "prices_round_9_day_0.csv").unlink()
    (datasets_dir / "trades_round_9_day_0.csv").unlink()
    storage_path.unlink()

    # execute_run should rehydrate everything.
    run_doc = await run_service.execute_run(
        req=RunCreateRequest(
            strategy_id=f"{stem}-{sha[:8]}", round=9, day=0, matcher="depth_only"
        ),
        settings=settings,
        db=db,
    )
    assert run_doc.get("status") == "succeeded"


# ---- helpers ---------------------------------------------------------------


_PRICE_HEADER = (
    "day;timestamp;product;"
    "bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;"
    "ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;"
    "mid_price;profit_and_loss"
)
_TRADE_HEADER = "timestamp;buyer;seller;symbol;currency;price;quantity"


def _minimal_prices(day: int) -> bytes:
    lines = [_PRICE_HEADER]
    for i in range(50):
        ts = i * 100
        mid = 10000 + i
        lines.append(
            f"{day};{ts};EMERALDS;"
            f"{mid - 2};20;{mid - 3};15;{mid - 4};10;"
            f"{mid + 2};20;{mid + 3};15;{mid + 4};10;"
            f"{mid}.0;0.0"
        )
    return ("\n".join(lines) + "\n").encode()


def _minimal_trades() -> bytes:
    lines = [_TRADE_HEADER]
    for i in range(50):
        ts = i * 100
        mid = 10000 + i
        lines.append(f"{ts};;;EMERALDS;SEASHELLS;{mid};3")
    return ("\n".join(lines) + "\n").encode()
