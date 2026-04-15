"""B2 tests: /batches router (queued state only — executor arrives in B3)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_body(strategy_id: str, datasets: list[tuple[int, int]]) -> dict:
    return {
        "strategy_id": strategy_id,
        "datasets": [{"round": r, "day": d} for r, d in datasets],
        "matcher": "depth_only",
        "position_limit": 50,
        "params": {},
    }


def test_list_batches_empty(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/batches", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_requires_auth(client: TestClient) -> None:
    assert client.get("/batches").status_code == 401


def test_create_requires_auth(client: TestClient) -> None:
    assert client.post("/batches", json={}).status_code == 401


def test_create_batch_happy_path(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_dataset_day_neg1: dict,
    seeded_strategy: dict,
) -> None:
    r = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(0, -2), (0, -1)]),
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["strategy_id"] == seeded_strategy["_id"]
    assert doc["strategy_hash"] == seeded_strategy["sha256"]
    assert doc["strategy_filename"] == seeded_strategy["filename"]
    assert doc["matcher"] == "depth_only"
    assert doc["position_limit"] == 50
    assert doc["status"] == "queued"
    assert doc["started_at"] is None
    assert doc["finished_at"] is None
    assert doc["progress"] == {"total": 2, "completed": 0, "failed": 0}
    assert len(doc["tasks"]) == 2
    for task in doc["tasks"]:
        assert task["status"] == "queued"
        assert task["run_id"] is None


def test_create_batch_missing_strategy_404(
    client: TestClient, auth_headers: dict, seeded_dataset: dict
) -> None:
    r = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body("does-not-exist", [(0, -2)]),
    )
    assert r.status_code == 404
    assert "strategy" in r.json()["detail"].lower()


def test_create_batch_missing_dataset_404(
    client: TestClient, auth_headers: dict, seeded_strategy: dict
) -> None:
    r = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(9, 9)]),
    )
    assert r.status_code == 404
    assert "dataset" in r.json()["detail"].lower()


def test_create_batch_empty_datasets_422(
    client: TestClient, auth_headers: dict, seeded_strategy: dict
) -> None:
    r = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], []),
    )
    assert r.status_code == 422  # pydantic min_length=1


def test_list_after_create(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    create = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(0, -2)]),
    )
    assert create.status_code == 201
    batch_id = create.json()["_id"]

    listing = client.get("/batches", headers=auth_headers)
    assert listing.status_code == 200
    ids = [b["_id"] for b in listing.json()]
    assert batch_id in ids


def test_get_batch_by_id(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    create = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(0, -2)]),
    )
    batch_id = create.json()["_id"]

    got = client.get(f"/batches/{batch_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["_id"] == batch_id


def test_get_batch_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/batches/nope", headers=auth_headers)
    assert r.status_code == 404


def test_delete_batch_unknown_returns_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.delete("/batches/nope", headers=auth_headers)
    assert r.status_code == 404


def test_delete_batch_queued_returns_409(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    created = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(0, -2)]),
    ).json()
    # Batch is queued right after POST (no worker running in this test).
    r = client.delete(f"/batches/{created['_id']}", headers=auth_headers)
    assert r.status_code == 409


def test_delete_batch_terminal_happy_path(
    client: TestClient,
    auth_headers: dict,
    test_app,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    created = client.post(
        "/batches",
        headers=auth_headers,
        json=_create_body(seeded_strategy["_id"], [(0, -2)]),
    ).json()
    batch_id = created["_id"]

    # Flip the batch to succeeded directly in Mongo so delete is allowed.
    import asyncio

    async def _mark_done():
        await test_app.state.mongo_db["batches"].update_one(
            {"_id": batch_id}, {"$set": {"status": "succeeded"}}
        )

    asyncio.get_event_loop().run_until_complete(_mark_done())

    r = client.delete(f"/batches/{batch_id}", headers=auth_headers)
    assert r.status_code == 204

    # Gone.
    r2 = client.get(f"/batches/{batch_id}", headers=auth_headers)
    assert r2.status_code == 404
