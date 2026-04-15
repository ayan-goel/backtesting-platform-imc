"""L3 tests: prosperity study command via Typer CliRunner."""

from __future__ import annotations

import json
from pathlib import Path
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
    def __init__(
        self, *, post_response: _FakeResponse, get_responses: list[_FakeResponse]
    ) -> None:
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
            raise AssertionError("ran out of scripted GETs")
        return self._gets.pop(0)

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_API_URL", "http://stub")
    monkeypatch.setenv("PLATFORM_API_KEY", "test-key")


def _install_fake(
    monkeypatch: pytest.MonkeyPatch,
    post: _FakeResponse,
    gets: list[_FakeResponse],
) -> _FakeClient:
    fake = _FakeClient(post_response=post, get_responses=gets)
    monkeypatch.setattr(api_client, "build_client", lambda timeout=60.0: fake)
    return fake


def _study_doc(status: str, best: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "_id": "study-1",
        "status": status,
        "progress": {"total": 3, "completed": 3 if status == "succeeded" else 0, "failed": 0, "running": 0},
        "best_trial": best,
    }


def _space_file(tmp_path: Path) -> Path:
    path = tmp_path / "space.json"
    path.write_text(json.dumps({"edge": {"type": "int", "low": 0, "high": 5}}))
    return path


def test_study_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    queued = _study_doc("queued")
    running = _study_doc("running")
    best = {"number": 2, "value": 200.0, "params": {"edge": 4}, "run_id": "run-xyz"}
    succeeded = _study_doc("succeeded", best=best)

    fake = _install_fake(
        monkeypatch,
        post=_FakeResponse(201, queued),
        gets=[_FakeResponse(200, running), _FakeResponse(200, succeeded)],
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "study",
            "--strategy",
            "noop-abc",
            "--round",
            "0",
            "--day",
            "-2",
            "--space",
            str(_space_file(tmp_path)),
            "--n-trials",
            "3",
            "--poll",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "submitted" in result.output
    assert "study-1" in result.output
    assert "run-xyz" in result.output
    assert "200.0000" in result.output

    # Confirm POST body is shaped correctly.
    assert len(fake.post_calls) == 1
    path, body = fake.post_calls[0]
    assert path == "/studies"
    assert body["strategy_id"] == "noop-abc"
    assert body["round"] == 0
    assert body["day"] == -2
    assert body["n_trials"] == 3
    assert body["space"] == {"edge": {"type": "int", "low": 0, "high": 5}}


def test_study_cancelled_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    queued = _study_doc("queued")
    cancelled = _study_doc("cancelled")
    _install_fake(
        monkeypatch,
        post=_FakeResponse(201, queued),
        gets=[_FakeResponse(200, cancelled)],
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "study",
            "--strategy",
            "noop-abc",
            "--round",
            "0",
            "--day",
            "-2",
            "--space",
            str(_space_file(tmp_path)),
            "--poll",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "cancelled" in result.output
    assert "no best trial" in result.output


def test_study_invalid_direction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "study",
            "--strategy",
            "noop-abc",
            "--round",
            "0",
            "--day",
            "-2",
            "--space",
            str(_space_file(tmp_path)),
            "--direction",
            "sideways",
        ],
    )
    assert result.exit_code != 0
    assert "direction" in result.output.lower()
