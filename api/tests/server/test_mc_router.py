"""Tests for the /mc router and mc_runner worker."""

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
from fastapi.testclient import TestClient

from server.schemas.mc import McCreateRequest
from server.services import mc_runner, mc_service
from server.settings import get_settings
from tests.server._mc_csv_fixtures import dataset_doc_for, write_synthetic_csvs

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""

GREEDY_TRADER = b"""
from datamodel import Order


class Trader:
    def run(self, state):
        orders = {}
        for product, depth in state.order_depths.items():
            asks = sorted(depth.sell_orders.items())
            if asks:
                price, _ = asks[0]
                orders[product] = [Order(product, price, 3)]
            else:
                orders[product] = []
        return orders, 0, ""
"""


# ---- fixtures ---------------------------------------------------------------


@pytest_asyncio.fixture
async def mc_dataset(test_app: FastAPI, tmp_path: Path) -> dict:
    datasets_dir = tmp_path / "data"
    prices_path, trades_path, products = write_synthetic_csvs(
        datasets_dir=datasets_dir, round_num=0, day=0
    )
    doc = dataset_doc_for(
        round_num=0,
        day=0,
        prices_path=prices_path,
        trades_path=trades_path,
        products=products,
        num_timestamps=80,
    )
    await test_app.state.mongo_db["datasets"].insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def mc_strategy(
    test_app: FastAPI, tmp_path: Path, request: pytest.FixtureRequest
) -> dict:
    source: bytes = getattr(request, "param", MINIMAL_TRADER)
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(source).hexdigest()
    stem = "mcstrat"
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


async def _wait_until(
    predicate: Any, db: Any, mc_id: str, timeout: float = 20.0
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        last = await mc_service.get_mc_simulation(db, mc_id) or {}
        if predicate(last):
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting. last doc: {last}")


# ---- router surface ---------------------------------------------------------


def test_list_mc_requires_auth(client: TestClient) -> None:
    assert client.get("/mc").status_code == 401


def test_list_mc_empty(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/mc", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_mc_missing_strategy_404(
    client: TestClient, auth_headers: dict, mc_dataset: dict
) -> None:
    r = client.post(
        "/mc",
        headers=auth_headers,
        json={
            "strategy_id": "nope",
            "round": 0,
            "day": 0,
            "n_paths": 1,
        },
    )
    assert r.status_code == 404


def test_create_mc_missing_dataset_404(
    client: TestClient, auth_headers: dict, mc_strategy: dict
) -> None:
    r = client.post(
        "/mc",
        headers=auth_headers,
        json={
            "strategy_id": mc_strategy["_id"],
            "round": 9,
            "day": 9,
            "n_paths": 1,
        },
    )
    assert r.status_code == 404


def test_create_mc_happy_path_queued(
    client: TestClient,
    auth_headers: dict,
    mc_dataset: dict,
    mc_strategy: dict,
) -> None:
    r = client.post(
        "/mc",
        headers=auth_headers,
        json={
            "strategy_id": mc_strategy["_id"],
            "round": 0,
            "day": 0,
            "n_paths": 3,
            "seed": 42,
            "generator": {"type": "identity"},
        },
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "queued"
    assert doc["n_paths"] == 3
    assert doc["generator"] == {"type": "identity"}
    assert doc["progress"]["total"] == 3
    assert len(doc["paths"]) == 3
    assert all(p["status"] == "queued" for p in doc["paths"])


def test_delete_queued_mc_returns_409(
    client: TestClient,
    auth_headers: dict,
    mc_dataset: dict,
    mc_strategy: dict,
) -> None:
    created = client.post(
        "/mc",
        headers=auth_headers,
        json={
            "strategy_id": mc_strategy["_id"],
            "round": 0,
            "day": 0,
            "n_paths": 1,
        },
    ).json()
    r = client.delete(f"/mc/{created['_id']}", headers=auth_headers)
    assert r.status_code == 409


# ---- worker end-to-end ------------------------------------------------------


@pytest.mark.parametrize("mc_strategy", [GREEDY_TRADER], indirect=True)
@pytest.mark.asyncio
async def test_mc_identity_runs_end_to_end(
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    mc_dataset: dict,
    mc_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    settings = get_settings()

    doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=mc_strategy["_id"],
            round=0,
            day=0,
            n_paths=2,
            seed=42,
        ),
        settings=settings,
        db=db,
    )
    mc_runner.signal_new_mc_work(mc_worker_state)

    final = await _wait_until(
        lambda d: d.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "succeeded", final
    assert final["progress"]["completed"] == 2
    assert final["progress"]["failed"] == 0
    assert final["finished_at"] is not None
    for path in final["paths"]:
        assert path["status"] == "succeeded"
        assert path["pnl_total"] is not None


@pytest.mark.parametrize("mc_strategy", [GREEDY_TRADER], indirect=True)
@pytest.mark.asyncio
async def test_mc_writes_path_curves_to_disk(
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    mc_dataset: dict,
    mc_strategy: dict,
    tmp_path: Path,
) -> None:
    from server.services.mc_path_runner import DOWNSAMPLE_N
    from server.storage import mc_artifacts

    db = test_app.state.mongo_db
    settings = get_settings()
    doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=mc_strategy["_id"],
            round=0,
            day=0,
            n_paths=2,
            seed=7,
            generator={"type": "block_bootstrap", "block_size": 10},
        ),
        settings=settings,
        db=db,
    )
    mc_runner.signal_new_mc_work(mc_worker_state)
    final = await _wait_until(
        lambda d: d.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "succeeded", final

    for idx in range(2):
        curve = mc_artifacts.read_path_curve(settings.storage_root, doc["_id"], idx)
        assert curve is not None
        assert curve.shape == (DOWNSAMPLE_N,)
        assert curve.dtype.name == "float32"


@pytest.mark.parametrize("mc_strategy", [GREEDY_TRADER], indirect=True)
@pytest.mark.asyncio
async def test_mc_path_curve_endpoint_returns_json(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    mc_dataset: dict,
    mc_strategy: dict,
) -> None:
    from server.services.mc_path_runner import DOWNSAMPLE_N

    db = test_app.state.mongo_db
    settings = get_settings()
    doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=mc_strategy["_id"],
            round=0,
            day=0,
            n_paths=1,
            seed=1,
        ),
        settings=settings,
        db=db,
    )
    mc_runner.signal_new_mc_work(mc_worker_state)
    await _wait_until(
        lambda d: d.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    r = client.get(f"/mc/{doc['_id']}/paths/0/curve", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["index"] == 0
    assert len(body["curve"]) == DOWNSAMPLE_N


@pytest.mark.parametrize("mc_strategy", [GREEDY_TRADER], indirect=True)
@pytest.mark.asyncio
async def test_mc_identity_path_pnl_equals_direct(
    test_app: FastAPI,
    mc_worker_state: mc_runner.McWorkersState,
    mc_dataset: dict,
    mc_strategy: dict,
    tmp_path: Path,
) -> None:
    """Correctness anchor: identity MC path_total equals a direct simulate_day run."""
    from engine.market.loader import load_round_day
    from engine.matching.imc_matcher import ImcMatcher
    from engine.simulator.runner import RunConfig, simulate_day
    from engine.simulator.strategy_loader import load_trader

    db = test_app.state.mongo_db
    settings = get_settings()

    # Direct simulate_day on the exact same data
    md = load_round_day(0, 0, tmp_path / "data")
    strategy_path = tmp_path / "strategies" / f"{mc_strategy['stem']}-{mc_strategy['sha256'][7:15]}.py"
    trader = load_trader(strategy_path)
    direct_result = simulate_day(
        trader=trader,
        market_data=md,
        matcher=ImcMatcher(),
        config=RunConfig(
            run_id="direct",
            strategy_path=mc_strategy["filename"],
            strategy_hash=mc_strategy["sha256"],
            round=0,
            day=0,
            matcher_name="imc",
            position_limits={p: 50 for p in md.products},
            output_dir=tmp_path / "direct_out",
        ),
    )

    doc = await mc_service.create_mc_simulation(
        req=McCreateRequest(
            strategy_id=mc_strategy["_id"],
            round=0,
            day=0,
            n_paths=1,
            seed=42,
            generator={"type": "identity"},
        ),
        settings=settings,
        db=db,
    )
    mc_runner.signal_new_mc_work(mc_worker_state)
    final = await _wait_until(
        lambda d: d.get("status") in {"succeeded", "failed"}, db, doc["_id"]
    )
    assert final["status"] == "succeeded", final
    mc_pnl = final["paths"][0]["pnl_total"]
    assert mc_pnl == direct_result.summary.pnl_total
