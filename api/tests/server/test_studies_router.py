"""O4 tests: /studies router + service (no runner wired yet)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _valid_body(strategy_id: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "round": 0,
        "day": -2,
        "matcher": "depth_only",
        "position_limit": 50,
        "space": {"edge": {"type": "int", "low": 0, "high": 5}},
        "objective": "pnl_total",
        "direction": "maximize",
        "n_trials": 3,
    }


@pytest.mark.asyncio
async def test_list_studies_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/studies", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_studies_requires_auth(client: TestClient) -> None:
    resp = client.get("/studies")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_study_happy_path(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    body = _valid_body(seeded_strategy["_id"])
    resp = client.post("/studies", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["status"] == "queued"
    assert doc["n_trials"] == 3
    assert doc["progress"] == {"total": 3, "completed": 0, "failed": 0, "running": 0}
    assert doc["direction"] == "maximize"
    assert doc["storage_path"].startswith("optuna/")
    assert doc["best_trial"] is None

    # List should now include it.
    lst = client.get("/studies", headers=auth_headers).json()
    assert len(lst) == 1
    assert lst[0]["_id"] == doc["_id"]


@pytest.mark.asyncio
async def test_create_study_missing_strategy_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_dataset: dict[str, Any],
) -> None:
    body = _valid_body("nope-nothere")
    resp = client.post("/studies", json=body, headers=auth_headers)
    assert resp.status_code == 404
    assert "strategy" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_study_missing_dataset_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
) -> None:
    body = _valid_body(seeded_strategy["_id"])
    resp = client.post("/studies", json=body, headers=auth_headers)
    assert resp.status_code == 404
    assert "dataset" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_study_invalid_space_returns_400(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    body = _valid_body(seeded_strategy["_id"])
    body["space"] = {"edge": {"type": "int", "low": 10, "high": 1}}  # inverted
    resp = client.post("/studies", json=body, headers=auth_headers)
    assert resp.status_code == 400
    assert "edge" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_study_empty_space_returns_400(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    body = _valid_body(seeded_strategy["_id"])
    body["space"] = {}
    resp = client.post("/studies", json=body, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_study_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/studies/nope", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_study_roundtrip(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    body = _valid_body(seeded_strategy["_id"])
    created = client.post("/studies", json=body, headers=auth_headers).json()
    fetched = client.get(f"/studies/{created['_id']}", headers=auth_headers).json()
    assert fetched["_id"] == created["_id"]
    assert fetched["status"] == "queued"


@pytest.mark.asyncio
async def test_cancel_study_flips_status(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    created = client.post(
        "/studies", json=_valid_body(seeded_strategy["_id"]), headers=auth_headers
    ).json()
    resp = client.post(f"/studies/{created['_id']}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["finished_at"] is not None


@pytest.mark.asyncio
async def test_cancel_study_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/studies/nope/cancel", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_trials_empty_for_fresh_study(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    created = client.post(
        "/studies", json=_valid_body(seeded_strategy["_id"]), headers=auth_headers
    ).json()
    resp = client.get(f"/studies/{created['_id']}/trials", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_trials_unknown_study_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/studies/nope/trials", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_study_unknown_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.delete("/studies/nope", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_study_queued_returns_409(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    created = client.post(
        "/studies", json=_valid_body(seeded_strategy["_id"]), headers=auth_headers
    ).json()
    resp = client.delete(f"/studies/{created['_id']}", headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_study_terminal_happy_path(
    client: TestClient,
    auth_headers: dict[str, str],
    test_app: Any,
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
    tmp_path: Any,
) -> None:
    created = client.post(
        "/studies", json=_valid_body(seeded_strategy["_id"]), headers=auth_headers
    ).json()
    study_id = created["_id"]
    storage_subpath = created["storage_path"]

    # SQLite file exists because create_study runs optuna.create_study.
    sqlite_path = tmp_path / storage_subpath
    assert sqlite_path.is_file()

    # Flip to succeeded in Mongo so delete is allowed.
    await test_app.state.mongo_db["studies"].update_one(
        {"_id": study_id}, {"$set": {"status": "succeeded"}}
    )

    # Seed a child run to verify it stays.
    await test_app.state.mongo_db["runs"].insert_one(
        {"_id": "child-run", "study_id": study_id, "trial_number": 0}
    )

    resp = client.delete(f"/studies/{study_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Doc gone.
    resp2 = client.get(f"/studies/{study_id}", headers=auth_headers)
    assert resp2.status_code == 404

    # SQLite gone.
    assert not sqlite_path.exists()

    # Child run still exists.
    found_run = await test_app.state.mongo_db["runs"].find_one({"_id": "child-run"})
    assert found_run is not None


@pytest.mark.asyncio
async def test_list_trials_sorted_by_number(
    client: TestClient,
    auth_headers: dict[str, str],
    test_app: Any,
    seeded_strategy: dict[str, Any],
    seeded_dataset: dict[str, Any],
) -> None:
    created = client.post(
        "/studies", json=_valid_body(seeded_strategy["_id"]), headers=auth_headers
    ).json()
    study_id = created["_id"]

    # Insert child runs directly to simulate completed trials.
    runs = test_app.state.mongo_db["runs"]
    for trial_number, pnl in [(1, 50.0), (0, 10.0), (2, 200.0)]:
        await runs.insert_one(
            {
                "_id": f"{study_id}__t{trial_number}",
                "study_id": study_id,
                "trial_number": trial_number,
                "params": {"edge": trial_number},
                "pnl_total": pnl,
                "duration_ms": 100,
                "status": "succeeded",
            }
        )

    resp = client.get(f"/studies/{study_id}/trials", headers=auth_headers)
    assert resp.status_code == 200
    trials = resp.json()
    assert [t["trial_number"] for t in trials] == [0, 1, 2]
    assert [t["value"] for t in trials] == [10.0, 50.0, 200.0]
