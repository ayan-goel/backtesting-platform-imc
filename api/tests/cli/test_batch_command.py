"""L2 tests: prosperity batch command end-to-end via Typer CliRunner.

The http client is monkeypatched to return scripted responses so we can
exercise both happy and failing paths without a real server.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from cli import api_client
from cli.main import app


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    """Minimal stand-in that records calls and returns scripted responses."""

    def __init__(self, *, post_response: _FakeResponse, get_responses: list[_FakeResponse]) -> None:
        self._post = post_response
        self._gets = list(get_responses)
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_calls: list[str] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def post(self, path: str, json: dict[str, Any]) -> _FakeResponse:
        self.post_calls.append((path, json))
        return self._post

    def get(self, path: str) -> _FakeResponse:
        self.get_calls.append(path)
        if not self._gets:
            raise AssertionError("FakeClient ran out of scripted GET responses")
        return self._gets.pop(0)

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_API_URL", "http://stub")
    monkeypatch.setenv("PLATFORM_API_KEY", "test-key")


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(api_client, "build_client", lambda: fake)


def _batch_doc(status: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "_id": "batch-abc",
        "status": status,
        "progress": {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t["status"] == "succeeded"),
            "failed": sum(1 for t in tasks if t["status"] == "failed"),
        },
        "tasks": tasks,
    }


def test_batch_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    queued = _batch_doc(
        "queued",
        [
            {"round": 0, "day": -2, "status": "queued", "run_id": None, "pnl_total": None, "duration_ms": None, "error": None},
            {"round": 0, "day": -1, "status": "queued", "run_id": None, "pnl_total": None, "duration_ms": None, "error": None},
        ],
    )
    running = _batch_doc(
        "running",
        [
            {"round": 0, "day": -2, "status": "succeeded", "run_id": "run-a", "pnl_total": 123.45, "duration_ms": 500, "error": None},
            {"round": 0, "day": -1, "status": "running", "run_id": None, "pnl_total": None, "duration_ms": None, "error": None},
        ],
    )
    succeeded = _batch_doc(
        "succeeded",
        [
            {"round": 0, "day": -2, "status": "succeeded", "run_id": "run-a", "pnl_total": 123.45, "duration_ms": 500, "error": None},
            {"round": 0, "day": -1, "status": "succeeded", "run_id": "run-b", "pnl_total": 50.0, "duration_ms": 600, "error": None},
        ],
    )

    fake = _FakeClient(
        post_response=_FakeResponse(201, queued),
        get_responses=[_FakeResponse(200, running), _FakeResponse(200, succeeded)],
    )
    _install_fake_client(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "batch",
            "--strategy",
            "noop-abc",
            "--datasets",
            "0:-2,0:-1",
            "--poll",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "submitted" in result.output
    assert "batch-abc" in result.output
    assert "succeeded" in result.output
    assert "123.45" in result.output

    # Confirm POST body was what we expect.
    assert fake.post_calls == [
        (
            "/batches",
            {
                "strategy_id": "noop-abc",
                "datasets": [{"round": 0, "day": -2}, {"round": 0, "day": -1}],
                "matcher": "depth_only",
                "position_limit": 50,
                "params": {},
            },
        )
    ]


def test_batch_failed_path(monkeypatch: pytest.MonkeyPatch) -> None:
    queued = _batch_doc(
        "queued",
        [
            {"round": 0, "day": -2, "status": "queued", "run_id": None, "pnl_total": None, "duration_ms": None, "error": None},
        ],
    )
    failed = _batch_doc(
        "failed",
        [
            {"round": 0, "day": -2, "status": "failed", "run_id": None, "pnl_total": None, "duration_ms": None, "error": "strategy import failed"},
        ],
    )

    fake = _FakeClient(
        post_response=_FakeResponse(201, queued),
        get_responses=[_FakeResponse(200, failed)],
    )
    _install_fake_client(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["batch", "--strategy", "bad", "--datasets", "0:-2", "--poll", "0"],
    )
    assert result.exit_code == 2
    assert "strategy import failed" in result.output


def test_batch_rejects_missing_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    # No need to install a fake — the flag validation fires first.
    fake = _FakeClient(
        post_response=_FakeResponse(201, {}),
        get_responses=[],
    )
    _install_fake_client(monkeypatch, fake)

    runner = CliRunner()
    result = runner.invoke(app, ["batch", "--strategy", "noop-abc"])
    assert result.exit_code != 0
    assert "dataset" in result.output.lower()
