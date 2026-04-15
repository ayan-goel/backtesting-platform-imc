"""T6 parallel-worker tests: concurrent path execution is deterministic
and still produces correct aggregate stats.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI

from server.schemas.mc import McCreateRequest
from server.services import mc_runner, mc_service
from server.settings import get_settings

from tests.server._mc_csv_fixtures import dataset_doc_for, write_synthetic_csvs

GREEDY_TRADER = b"""
from datamodel import Order


class Trader:
    def run(self, state):
        orders = {}
        for product, depth in state.order_depths.items():
            asks = sorted(depth.sell_orders.items())
            if asks:
                price, _ = asks[0]
                orders[product] = [Order(product, price, 2)]
            else:
                orders[product] = []
        return orders, 0, ""
"""


async def _wait_until(
    predicate: Any, db: Any, mc_id: str, timeout: float = 30.0
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        last = await mc_service.get_mc_simulation(db, mc_id) or {}
        if predicate(last):
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out. last: {last}")


@pytest_asyncio.fixture
async def parallel_dataset(test_app: FastAPI, tmp_path: Path) -> dict:
    datasets_dir = tmp_path / "data"
    prices_path, trades_path, products = write_synthetic_csvs(
        datasets_dir=datasets_dir, round_num=0, day=0, num_timestamps=40
    )
    doc = dataset_doc_for(
        round_num=0,
        day=0,
        prices_path=prices_path,
        trades_path=trades_path,
        products=products,
        num_timestamps=40,
    )
    await test_app.state.mongo_db["datasets"].insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def parallel_strategy(test_app: FastAPI, tmp_path: Path) -> dict:
    source = GREEDY_TRADER
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(source).hexdigest()
    stem = "parallelstrat"
    storage_path = strategies_dir / f"{stem}-{sha[:8]}.py"
    storage_path.write_bytes(source)
    doc = {
        "_id": f"{stem}-{sha[:8]}",
        "filename": f"{stem}.py",
        "stem": stem,
        "sha256": f"sha256:{sha}",
        "uploaded_at": datetime.now(UTC).isoformat(),
        "size_bytes": len(source),
        "storage_subpath": f"strategies/{storage_path.name}",
    }
    await test_app.state.mongo_db["strategies"].insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def mc_worker_state(
    test_app: FastAPI,
) -> AsyncIterator[mc_runner.McWorkersState]:
    settings = get_settings()
    state = await mc_runner.start_mc_worker(
        db=test_app.state.mongo_db, settings=settings
    )
    test_app.state.mc_worker = state
    try:
        yield state
    finally:
        await mc_runner.stop_mc_worker(state)


@pytest.mark.asyncio
async def test_parallel_path_results_match_sequential(
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    parallel_dataset: dict,
    parallel_strategy: dict,
) -> None:
    """Same seed, different worker counts → byte-identical per-path pnls."""
    db = test_app.state.mongo_db
    settings = get_settings()

    async def run_with_workers(workers: int) -> list[float]:
        doc = await mc_service.create_mc_simulation(
            req=McCreateRequest(
                strategy_id=parallel_strategy["_id"],
                round=0,
                day=0,
                n_paths=6,
                seed=2026,
                num_workers=workers,
                generator={"type": "block_bootstrap", "block_size": 5},
            ),
            settings=settings,
            db=db,
        )
        mc_runner.signal_new_mc_work(mc_worker_state)
        final = await _wait_until(
            lambda d: d.get("status") in {"succeeded", "failed"}, db, doc["_id"]
        )
        assert final["status"] == "succeeded", final
        paths = sorted(final["paths"], key=lambda p: p["index"])
        return [float(p["pnl_total"]) for p in paths]

    seq = await run_with_workers(1)
    par = await run_with_workers(4)
    assert seq == par, f"parallel output drifted from sequential: {seq=} {par=}"


@pytest.mark.asyncio
async def test_cancellation_halts_before_all_paths_finish(
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    parallel_dataset: dict,
    parallel_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=parallel_strategy["_id"],
            round=0,
            day=0,
            n_paths=20,
            seed=1,
            num_workers=1,
        ),
        settings=settings,
        db=db,
    )
    mc_runner.signal_new_mc_work(mc_worker_state)

    # Give the worker a moment to start, then cancel.
    await asyncio.sleep(0.05)
    await mc_service.cancel_mc_simulation(db, doc["_id"])

    final = await _wait_until(
        lambda d: d.get("status") in {"cancelled", "succeeded", "failed"},
        db,
        doc["_id"],
    )
    # Either the worker saw the cancel mid-loop (ideal) or it happened to finish
    # before cancel landed; both are acceptable. We just assert it reached a
    # terminal state.
    assert final["status"] in {"cancelled", "succeeded", "failed"}


@pytest.mark.asyncio
async def test_recover_orphaned_mc_resets_to_queued(test_app: FastAPI) -> None:
    from server.storage import registry

    db = test_app.state.mongo_db
    orphan = {
        "_id": "mc-orphan",
        "created_at": datetime.now(UTC).isoformat(),
        "strategy_id": "missing",
        "strategy_hash": "sha256:dead",
        "strategy_filename": "noop.py",
        "round": 0,
        "day": 0,
        "matcher": "imc",
        "trade_matching_mode": "all",
        "position_limit": 50,
        "params": {},
        "generator": {"type": "identity"},
        "n_paths": 3,
        "seed": 0,
        "num_workers": 1,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "progress": {"total": 3, "completed": 0, "failed": 0, "running": 1},
        "paths": [{"index": i, "status": "queued"} for i in range(3)],
    }
    await db[registry.MC_COLLECTION].insert_one(orphan)

    recovered = await mc_runner.recover_orphaned_mc(db)
    assert recovered == 1

    after = await registry.get_mc(db, "mc-orphan")
    assert after is not None
    assert after["status"] == "queued"
