"""Dataset router tests: multi-file upload, list, get, delete (+ cascade)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

TUTORIAL = Path(__file__).resolve().parents[4] / "tutorial-round-data"


def _tutorial_files(round_num: int, day: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    prices = (TUTORIAL / f"prices_round_{round_num}_day_{day}.csv").read_bytes()
    trades = (TUTORIAL / f"trades_round_{round_num}_day_{day}.csv").read_bytes()
    return [
        (
            "files",
            (f"prices_round_{round_num}_day_{day}.csv", prices, "text/csv"),
        ),
        (
            "files",
            (f"trades_round_{round_num}_day_{day}.csv", trades, "text/csv"),
        ),
    ]


def _upload_tutorial(client: TestClient, auth_headers: dict, round_num: int, day: int):
    return client.post(
        "/datasets",
        headers=auth_headers,
        files=_tutorial_files(round_num, day),
    )


def test_list_datasets_empty(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/datasets", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_upload_and_list(client: TestClient, auth_headers: dict) -> None:
    r = _upload_tutorial(client, auth_headers, 0, -2)
    assert r.status_code == 201, r.text
    result = r.json()
    assert len(result["uploaded"]) == 1
    assert result["skipped"] == []
    doc = result["uploaded"][0]
    assert doc["_id"] == "r0d-2"
    assert doc["round"] == 0
    assert doc["day"] == -2
    assert "EMERALDS" in doc["products"]
    assert "TOMATOES" in doc["products"]
    assert doc["num_timestamps"] == 10000

    r2 = client.get("/datasets", headers=auth_headers)
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_upload_overwrites_existing(client: TestClient, auth_headers: dict) -> None:
    r1 = _upload_tutorial(client, auth_headers, 0, -2)
    r2 = _upload_tutorial(client, auth_headers, 0, -2)
    assert r1.status_code == 201
    assert r2.status_code == 201
    listing = client.get("/datasets", headers=auth_headers).json()
    assert len(listing) == 1


def test_upload_multiple_days_in_one_request(
    client: TestClient, auth_headers: dict
) -> None:
    files = _tutorial_files(0, -2) + _tutorial_files(0, -1)
    r = client.post("/datasets", headers=auth_headers, files=files)
    assert r.status_code == 201, r.text
    result = r.json()
    uploaded_ids = sorted(d["_id"] for d in result["uploaded"])
    assert uploaded_ids == ["r0d-1", "r0d-2"]

    listing = client.get("/datasets", headers=auth_headers).json()
    assert len(listing) == 2


def test_upload_skips_unrecognized_filenames(
    client: TestClient, auth_headers: dict
) -> None:
    files = [
        *_tutorial_files(0, -2),
        ("files", ("README.txt", b"not a dataset", "text/plain")),
    ]
    r = client.post("/datasets", headers=auth_headers, files=files)
    assert r.status_code == 201, r.text
    result = r.json()
    assert len(result["uploaded"]) == 1
    assert any(s["filename"] == "README.txt" for s in result["skipped"])


def test_upload_unpaired_file_skipped(client: TestClient, auth_headers: dict) -> None:
    prices = (TUTORIAL / "prices_round_0_day_-2.csv").read_bytes()
    files = [
        ("files", ("prices_round_0_day_-2.csv", prices, "text/csv")),
    ]
    r = client.post("/datasets", headers=auth_headers, files=files)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert any("missing matching trades" in s["reason"] for s in detail["skipped"])


def test_get_one(client: TestClient, auth_headers: dict) -> None:
    _upload_tutorial(client, auth_headers, 0, -2)
    r = client.get("/datasets/0/-2", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["_id"] == "r0d-2"


def test_get_one_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.get("/datasets/9/9", headers=auth_headers)
    assert r.status_code == 404


def test_delete(client: TestClient, auth_headers: dict) -> None:
    _upload_tutorial(client, auth_headers, 0, -2)
    r = client.delete("/datasets/0/-2", headers=auth_headers)
    assert r.status_code == 204
    listing = client.get("/datasets", headers=auth_headers).json()
    assert listing == []


def test_delete_not_found(client: TestClient, auth_headers: dict) -> None:
    r = client.delete("/datasets/9/9", headers=auth_headers)
    assert r.status_code == 404


def test_upload_invalid_csv_rejected(client: TestClient, auth_headers: dict) -> None:
    files = [
        (
            "files",
            (
                "prices_round_99_day_99.csv",
                b"wrong,header,layout\n",
                "text/csv",
            ),
        ),
        (
            "files",
            (
                "trades_round_99_day_99.csv",
                b"timestamp;buyer;seller;symbol;currency;price;quantity\n",
                "text/csv",
            ),
        ),
    ]
    r = client.post("/datasets", headers=auth_headers, files=files)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert any("invalid dataset" in s["reason"] for s in detail["skipped"])


def test_upload_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/datasets",
        files=[("files", ("prices_round_0_day_-2.csv", b"", "text/csv"))],
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_dataset_cascades_everything(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_dataset: dict,
    tmp_path: Path,
) -> None:
    """Deleting a dataset must also delete its runs, batches that
    referenced it, and studies targeting that (round, day)."""
    db = test_app.state.mongo_db

    # Seed a child run + its artifact dir.
    run_id = "child-run-ds"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("{}")
    await db["runs"].insert_one(
        {
            "_id": run_id,
            "strategy_id": "strat-x",
            "round": 0,
            "day": -2,
            "status": "succeeded",
        }
    )

    # Seed a terminal batch with a task at (0, -2).
    batch_id = "child-batch-ds"
    await db["batches"].insert_one(
        {
            "_id": batch_id,
            "strategy_id": "strat-x",
            "status": "succeeded",
            "tasks": [{"round": 0, "day": -2, "status": "succeeded"}],
        }
    )

    # Seed a terminal study at (0, -2) + fake SQLite file.
    study_id = "child-study-ds"
    optuna_dir = tmp_path / "optuna"
    optuna_dir.mkdir(parents=True)
    sqlite_file = optuna_dir / f"{study_id}.db"
    sqlite_file.write_bytes(b"fake")
    await db["studies"].insert_one(
        {
            "_id": study_id,
            "strategy_id": "strat-x",
            "round": 0,
            "day": -2,
            "status": "succeeded",
            "storage_path": f"optuna/{study_id}.db",
        }
    )

    # Delete the dataset.
    resp = client.delete("/datasets/0/-2", headers=auth_headers)
    assert resp.status_code == 204

    # Everything downstream is gone.
    assert (await db["runs"].find_one({"_id": run_id})) is None
    assert (await db["batches"].find_one({"_id": batch_id})) is None
    assert (await db["studies"].find_one({"_id": study_id})) is None
    assert not run_dir.exists()
    assert not sqlite_file.exists()
    assert (await db["datasets"].find_one({"round": 0, "day": -2})) is None


@pytest.mark.asyncio
async def test_delete_dataset_rejects_running_batch(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_dataset: dict,
) -> None:
    db = test_app.state.mongo_db
    await db["batches"].insert_one(
        {
            "_id": "busy-batch-ds",
            "strategy_id": "strat-x",
            "status": "running",
            "tasks": [{"round": 0, "day": -2, "status": "running"}],
        }
    )
    r = client.delete("/datasets/0/-2", headers=auth_headers)
    assert r.status_code == 409
    assert "busy-batch-ds" in r.json()["detail"]


@pytest.mark.asyncio
async def test_dataset_delete_preview_returns_counts(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_dataset: dict,
) -> None:
    db = test_app.state.mongo_db
    await db["runs"].insert_many(
        [
            {"_id": "r1", "strategy_id": "x", "round": 0, "day": -2},
            {"_id": "r2", "strategy_id": "y", "round": 0, "day": -2},
        ]
    )
    await db["batches"].insert_one(
        {
            "_id": "b1",
            "strategy_id": "x",
            "status": "succeeded",
            "tasks": [{"round": 0, "day": -2, "status": "succeeded"}],
        }
    )
    await db["studies"].insert_one(
        {
            "_id": "s1",
            "strategy_id": "x",
            "round": 0,
            "day": -2,
            "status": "succeeded",
            "storage_path": "optuna/s1.db",
        }
    )
    r = client.get("/datasets/0/-2/delete-preview", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"runs": 2, "batches": 1, "studies": 1}


def test_dataset_delete_preview_unknown_404(
    client: TestClient, auth_headers: dict
) -> None:
    r = client.get("/datasets/99/99/delete-preview", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_dataset_leaves_other_datasets_alone(
    client: TestClient,
    auth_headers: dict,
    test_app: FastAPI,
    seeded_dataset: dict,
    seeded_dataset_day_neg1: dict,
) -> None:
    db = test_app.state.mongo_db

    # A run at (0, -1), unrelated to the dataset we're deleting.
    await db["runs"].insert_one(
        {
            "_id": "other-run",
            "strategy_id": "strat-x",
            "round": 0,
            "day": -1,
            "status": "succeeded",
        }
    )

    assert client.delete("/datasets/0/-2", headers=auth_headers).status_code == 204

    # (0, -1) dataset still present, unrelated run still present.
    assert (await db["datasets"].find_one({"round": 0, "day": -1})) is not None
    assert (await db["runs"].find_one({"_id": "other-run"})) is not None
