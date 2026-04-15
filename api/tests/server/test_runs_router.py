"""API tests: foundation (auth, health) + runs router end-to-end."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_is_unauthenticated(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_runs_list_requires_api_key(client: TestClient) -> None:
    r = client.get("/runs")
    assert r.status_code == 401


def test_runs_list_with_bad_key(client: TestClient) -> None:
    r = client.get("/runs", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_runs_list_empty_with_valid_key(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/runs", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_run_and_read_back(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    # POST /runs executes the real engine against the seeded strategy + dataset.
    body = {
        "strategy_id": seeded_strategy["_id"],
        "round": 0,
        "day": -2,
    }
    r = client.post("/runs", headers=auth_headers, json=body)
    assert r.status_code == 201, r.text
    doc = r.json()
    run_id = doc["_id"]
    assert doc["strategy_path"] == seeded_strategy["filename"]
    assert doc["round"] == 0
    assert doc["day"] == -2
    assert isinstance(doc["pnl_total"], (int, float))

    r2 = client.get("/runs", headers=auth_headers)
    assert r2.status_code == 200
    assert any(d["_id"] == run_id for d in r2.json())

    r3 = client.get(f"/runs/{run_id}/summary", headers=auth_headers)
    assert r3.status_code == 200
    assert r3.json()["_id"] == run_id

    r4 = client.get(
        f"/runs/{run_id}/events",
        headers=auth_headers,
        params={"product": "EMERALDS", "limit": 10},
    )
    assert r4.status_code == 200
    lines = [line for line in r4.text.splitlines() if line]
    assert len(lines) == 10
    assert all('"product":"EMERALDS"' in line for line in lines)


def test_events_stride_subsamples_per_product(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2}
    run_doc = client.post("/runs", headers=auth_headers, json=body).json()
    run_id = run_doc["_id"]

    # Baseline: stride=1 returns all events for the chosen product.
    full = client.get(
        f"/runs/{run_id}/events",
        headers=auth_headers,
        params={"product": "EMERALDS"},
    ).text.splitlines()
    full = [line for line in full if line]
    assert len(full) > 100  # tutorial day has ~10k events per product

    strided = client.get(
        f"/runs/{run_id}/events",
        headers=auth_headers,
        params={"product": "EMERALDS", "stride": 5},
    ).text.splitlines()
    strided = [line for line in strided if line]
    # At stride 5, expect roughly len(full) / 5 rows.
    assert len(strided) < len(full)
    assert abs(len(strided) - len(full) / 5) <= 2

    # Last ts is preserved (trailing flush).
    import json as _json

    assert _json.loads(strided[-1])["ts"] == _json.loads(full[-1])["ts"]
    # First ts is preserved (idx 0 always emitted).
    assert _json.loads(strided[0])["ts"] == _json.loads(full[0])["ts"]


def test_events_stride_default_is_no_op(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2}
    run_doc = client.post("/runs", headers=auth_headers, json=body).json()
    run_id = run_doc["_id"]
    r = client.get(
        f"/runs/{run_id}/events",
        headers=auth_headers,
        params={"stride": 1, "product": "EMERALDS"},
    )
    assert r.status_code == 200
    lines = [line for line in r.text.splitlines() if line]
    assert len(lines) > 100


def test_events_large_stride_still_emits_endpoints(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2}
    run_doc = client.post("/runs", headers=auth_headers, json=body).json()
    run_id = run_doc["_id"]

    full_lines = [
        line
        for line in client.get(
            f"/runs/{run_id}/events",
            headers=auth_headers,
            params={"product": "EMERALDS"},
        ).text.splitlines()
        if line
    ]

    # Absurdly large stride — should still return at least the first + last.
    r = client.get(
        f"/runs/{run_id}/events",
        headers=auth_headers,
        params={"product": "EMERALDS", "stride": 100_000},
    )
    lines = [line for line in r.text.splitlines() if line]
    assert len(lines) >= 2

    import json as _json

    assert _json.loads(lines[0])["ts"] == _json.loads(full_lines[0])["ts"]
    assert _json.loads(lines[-1])["ts"] == _json.loads(full_lines[-1])["ts"]


def test_create_run_with_depth_and_trades_matcher(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {
        "strategy_id": seeded_strategy["_id"],
        "round": 0,
        "day": -2,
        "matcher": "depth_and_trades",
    }
    r = client.post("/runs", headers=auth_headers, json=body)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["matcher"] == "depth_and_trades"


def test_create_run_with_unknown_matcher_400(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {
        "strategy_id": seeded_strategy["_id"],
        "round": 0,
        "day": -2,
        "matcher": "bogus",
    }
    r = client.post("/runs", headers=auth_headers, json=body)
    assert r.status_code == 400


def test_create_run_is_idempotent(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
) -> None:
    body = {"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2}
    r1 = client.post("/runs", headers=auth_headers, json=body)
    r2 = client.post("/runs", headers=auth_headers, json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["_id"] == r2.json()["_id"]


def test_create_run_missing_strategy_404(
    client: TestClient, auth_headers: dict, seeded_dataset: dict
) -> None:
    r = client.post(
        "/runs",
        headers=auth_headers,
        json={"strategy_id": "does-not-exist", "round": 0, "day": -2},
    )
    assert r.status_code == 404
    assert "strategy" in r.json()["detail"].lower()


def test_create_run_missing_dataset_404(
    client: TestClient, auth_headers: dict, seeded_strategy: dict
) -> None:
    r = client.post(
        "/runs",
        headers=auth_headers,
        json={"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2},
    )
    assert r.status_code == 404
    assert "dataset" in r.json()["detail"].lower()


def test_summary_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/runs/nonexistent/summary", headers=auth_headers)
    assert r.status_code == 404


def test_delete_run_removes_doc_and_artifacts(
    client: TestClient,
    auth_headers: dict,
    seeded_dataset: dict,
    seeded_strategy: dict,
    tmp_path,
) -> None:
    body = {"strategy_id": seeded_strategy["_id"], "round": 0, "day": -2}
    created = client.post("/runs", headers=auth_headers, json=body).json()
    run_id = created["_id"]

    # Artifact dir should exist after the run.
    run_dir = tmp_path / "runs" / run_id
    assert run_dir.is_dir()

    r = client.delete(f"/runs/{run_id}", headers=auth_headers)
    assert r.status_code == 204

    # Doc gone.
    r2 = client.get(f"/runs/{run_id}/summary", headers=auth_headers)
    assert r2.status_code == 404

    # Artifact dir gone.
    assert not run_dir.exists()

    # Second delete returns 404.
    r3 = client.delete(f"/runs/{run_id}", headers=auth_headers)
    assert r3.status_code == 404


def test_delete_run_unknown_returns_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.delete("/runs/nope", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_run_rejects_running(
    test_app, auth_headers: dict
) -> None:
    """A run currently executing must not be deletable."""
    db = test_app.state.mongo_db
    await db["runs"].insert_one(
        {
            "_id": "busy-run",
            "status": "running",
            "strategy_id": "x",
            "round": 0,
            "day": 0,
        }
    )
    from fastapi.testclient import TestClient as _TC

    client = _TC(test_app)
    r = client.delete("/runs/busy-run", headers=auth_headers)
    assert r.status_code == 409
