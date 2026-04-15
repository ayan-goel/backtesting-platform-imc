"""Strategy router tests: upload, list, get, delete (+ cascade)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""


def _upload_noop(client: TestClient, auth_headers: dict):
    return client.post(
        "/strategies",
        headers=auth_headers,
        files={"file": ("noop.py", MINIMAL_TRADER, "text/x-python")},
    )


def test_list_strategies_empty(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/strategies", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_upload_and_list(client: TestClient, auth_headers: dict) -> None:
    r = _upload_noop(client, auth_headers)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "noop.py"
    assert doc["stem"] == "noop"
    assert doc["sha256"].startswith("sha256:")
    assert doc["size_bytes"] > 0
    assert "noop-" in doc["_id"]

    r2 = client.get("/strategies", headers=auth_headers)
    assert len(r2.json()) == 1


def test_upload_same_content_is_idempotent(
    client: TestClient, auth_headers: dict
) -> None:
    r1 = _upload_noop(client, auth_headers)
    r2 = _upload_noop(client, auth_headers)
    assert r1.json()["_id"] == r2.json()["_id"]
    listing = client.get("/strategies", headers=auth_headers).json()
    assert len(listing) == 1


def test_get_one(client: TestClient, auth_headers: dict) -> None:
    r = _upload_noop(client, auth_headers)
    strategy_id = r.json()["_id"]
    r2 = client.get(f"/strategies/{strategy_id}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["_id"] == strategy_id


def test_get_one_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/strategies/nonexistent", headers=auth_headers)
    assert r.status_code == 404


def test_delete(client: TestClient, auth_headers: dict) -> None:
    r = _upload_noop(client, auth_headers)
    strategy_id = r.json()["_id"]
    r2 = client.delete(f"/strategies/{strategy_id}", headers=auth_headers)
    assert r2.status_code == 204
    assert client.get("/strategies", headers=auth_headers).json() == []


def test_delete_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.delete("/strategies/nonexistent", headers=auth_headers)
    assert r.status_code == 404


def test_upload_rejects_non_python(client: TestClient, auth_headers: dict) -> None:
    r = client.post(
        "/strategies",
        headers=auth_headers,
        files={"file": ("hello.txt", b"not python", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_rejects_no_trader_class(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.post(
        "/strategies",
        headers=auth_headers,
        files={
            "file": (
                "empty.py",
                b"# just a comment, no Trader class\nprint('hi')\n",
                "text/x-python",
            )
        },
    )
    assert r.status_code == 400
    assert "trader" in r.json()["detail"].lower()


def test_upload_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/strategies",
        files={"file": ("x.py", b"class Trader: pass", "text/x-python")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_strategy_cascades_everything(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_dataset: dict,
    seeded_strategy: dict,
    tmp_path: Path,
) -> None:
    """Deleting a strategy must also delete its runs, batches, and studies
    (and their artifact dirs / optuna SQLite files)."""
    db = test_app.state.mongo_db
    strategy_id = seeded_strategy["_id"]

    # Seed a child run + its artifact dir.
    run_id = "child-run-1"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("{}")
    await db["runs"].insert_one(
        {
            "_id": run_id,
            "strategy_id": strategy_id,
            "strategy_hash": seeded_strategy["sha256"],
            "round": 0,
            "day": -2,
            "status": "succeeded",
        }
    )

    # Seed a terminal child batch.
    batch_id = "child-batch-1"
    await db["batches"].insert_one(
        {
            "_id": batch_id,
            "strategy_id": strategy_id,
            "status": "succeeded",
            "tasks": [{"round": 0, "day": -2, "status": "succeeded"}],
        }
    )

    # Seed a terminal child study + fake SQLite file.
    study_id = "child-study-1"
    optuna_dir = tmp_path / "optuna"
    optuna_dir.mkdir(parents=True)
    sqlite_file = optuna_dir / f"{study_id}.db"
    sqlite_file.write_bytes(b"fake sqlite")
    await db["studies"].insert_one(
        {
            "_id": study_id,
            "strategy_id": strategy_id,
            "round": 0,
            "day": -2,
            "status": "succeeded",
            "storage_path": f"optuna/{study_id}.db",
        }
    )

    # Sanity: everything is there.
    assert (await db["runs"].find_one({"_id": run_id})) is not None
    assert (await db["batches"].find_one({"_id": batch_id})) is not None
    assert (await db["studies"].find_one({"_id": study_id})) is not None
    assert run_dir.exists()
    assert sqlite_file.exists()

    # Delete the strategy.
    resp = client.delete(f"/strategies/{strategy_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Everything downstream is gone.
    assert (await db["runs"].find_one({"_id": run_id})) is None
    assert (await db["batches"].find_one({"_id": batch_id})) is None
    assert (await db["studies"].find_one({"_id": study_id})) is None
    assert not run_dir.exists()
    assert not sqlite_file.exists()

    # Strategy itself is gone.
    assert (await db["strategies"].find_one({"_id": strategy_id})) is None


@pytest.mark.asyncio
async def test_delete_strategy_rejects_running_batch(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    strategy_id = seeded_strategy["_id"]
    await db["batches"].insert_one(
        {
            "_id": "busy-batch",
            "strategy_id": strategy_id,
            "status": "running",
            "tasks": [],
        }
    )
    r = client.delete(f"/strategies/{strategy_id}", headers=auth_headers)
    assert r.status_code == 409
    assert "busy-batch" in r.json()["detail"]


@pytest.mark.asyncio
async def test_delete_strategy_rejects_running_study(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    strategy_id = seeded_strategy["_id"]
    await db["studies"].insert_one(
        {
            "_id": "busy-study",
            "strategy_id": strategy_id,
            "round": 0,
            "day": -2,
            "status": "running",
            "storage_path": "optuna/busy-study.db",
        }
    )
    r = client.delete(f"/strategies/{strategy_id}", headers=auth_headers)
    assert r.status_code == 409
    assert "busy-study" in r.json()["detail"]


def test_delete_strategy_unknown_returns_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.delete("/strategies/does-not-exist", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_preview_returns_counts(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_strategy: dict,
) -> None:
    db = test_app.state.mongo_db
    strategy_id = seeded_strategy["_id"]
    await db["runs"].insert_many(
        [
            {"_id": "r1", "strategy_id": strategy_id, "round": 0, "day": -2},
            {"_id": "r2", "strategy_id": strategy_id, "round": 0, "day": -1},
        ]
    )
    await db["batches"].insert_one(
        {"_id": "b1", "strategy_id": strategy_id, "status": "succeeded", "tasks": []}
    )
    await db["studies"].insert_one(
        {
            "_id": "s1",
            "strategy_id": strategy_id,
            "round": 0,
            "day": -2,
            "status": "succeeded",
            "storage_path": "optuna/s1.db",
        }
    )
    r = client.get(
        f"/strategies/{strategy_id}/delete-preview", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == {"runs": 2, "batches": 1, "studies": 1}


def test_delete_preview_unknown_strategy_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/strategies/nope/delete-preview", headers=auth_headers)
    assert r.status_code == 404


TUNABLE_TRADER = b"""
class OsmiumTrader:
    MR_WEIGHT = 0.5
    SKEW_PER_UNIT = 0.05
    SOFT_LIMIT = 40

class Trader:
    def run(self, state):
        return {}, 0, ""
"""


def test_detect_params_returns_tunable_constants(
    client: TestClient, auth_headers: dict
) -> None:
    up = client.post(
        "/strategies",
        headers=auth_headers,
        files={"file": ("tunable.py", TUNABLE_TRADER, "text/x-python")},
    )
    assert up.status_code == 201, up.text
    strategy_id = up.json()["_id"]

    r = client.get(f"/strategies/{strategy_id}/params", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    names = {p["name"] for p in data}
    assert names == {"MR_WEIGHT", "SKEW_PER_UNIT", "SOFT_LIMIT"}
    by_name = {p["name"]: p for p in data}
    assert by_name["MR_WEIGHT"]["type"] == "float"
    assert by_name["MR_WEIGHT"]["default"] == 0.5
    assert by_name["MR_WEIGHT"]["suggested_low"] == 0.0
    assert by_name["MR_WEIGHT"]["suggested_high"] == 1.0
    assert by_name["SOFT_LIMIT"]["type"] == "int"
    assert by_name["SOFT_LIMIT"]["default"] == 40
    assert by_name["SOFT_LIMIT"]["class_name"] == "OsmiumTrader"


def test_detect_params_empty_when_no_constants(
    client: TestClient, auth_headers: dict
) -> None:
    r = _upload_noop(client, auth_headers)
    strategy_id = r.json()["_id"]
    r2 = client.get(f"/strategies/{strategy_id}/params", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json() == []


def test_detect_params_unknown_strategy_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/strategies/does-not-exist/params", headers=auth_headers)
    assert r.status_code == 404


def test_detect_params_requires_auth(client: TestClient) -> None:
    r = client.get("/strategies/any/params")
    assert r.status_code == 401


def test_delete_strategy_leaves_other_strategies_alone(
    client: TestClient, auth_headers: dict
) -> None:
    # Upload two different strategies.
    r1 = _upload_noop(client, auth_headers)
    body2 = b"class Trader:\n    def run(self, s):\n        return {}, 0, 'v2'\n"
    r2 = client.post(
        "/strategies",
        headers=auth_headers,
        files={"file": ("other.py", body2, "text/x-python")},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    id1 = r1.json()["_id"]
    id2 = r2.json()["_id"]

    # Delete the first.
    assert client.delete(f"/strategies/{id1}", headers=auth_headers).status_code == 204

    # Second still exists.
    assert client.get(f"/strategies/{id2}", headers=auth_headers).status_code == 200
