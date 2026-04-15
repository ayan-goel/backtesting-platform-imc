"""D1 tests: shared delete helpers for run artifacts."""

from __future__ import annotations

from pathlib import Path

from server.storage.artifacts import delete_run_dir, run_dir


def test_delete_run_dir_removes_tree(tmp_path: Path) -> None:
    rd = run_dir(tmp_path, "my-run")
    rd.mkdir(parents=True)
    (rd / "events.jsonl").write_text("{}")
    (rd / "summary.json").write_text("{}")
    (rd / "nested").mkdir()
    (rd / "nested" / "thing.txt").write_text("x")

    delete_run_dir(tmp_path, "my-run")

    assert not rd.exists()


def test_delete_run_dir_missing_is_noop(tmp_path: Path) -> None:
    # Never created — should not raise.
    delete_run_dir(tmp_path, "never-existed")
    assert not (tmp_path / "runs" / "never-existed").exists()


def test_delete_run_dir_leaves_siblings(tmp_path: Path) -> None:
    rd1 = run_dir(tmp_path, "run-1")
    rd2 = run_dir(tmp_path, "run-2")
    rd1.mkdir(parents=True)
    rd2.mkdir(parents=True)
    (rd1 / "a.txt").write_text("1")
    (rd2 / "b.txt").write_text("2")

    delete_run_dir(tmp_path, "run-1")

    assert not rd1.exists()
    assert rd2.exists()
    assert (rd2 / "b.txt").read_text() == "2"
