"""Disk artifact layout for MC simulations.

Layout:
    storage/mc/<mc_id>/
        config.json           mirrors the create request
        paths/
            0000.npy          float32[K] compact PnL curve (K from metrics.DOWNSAMPLE_N)
            0001.npy
            ...
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np


def mc_dir(storage_root: Path, mc_id: str) -> Path:
    return storage_root / "mc" / mc_id


def paths_dir(storage_root: Path, mc_id: str) -> Path:
    return mc_dir(storage_root, mc_id) / "paths"


def ensure_mc_dir(storage_root: Path, mc_id: str) -> Path:
    d = mc_dir(storage_root, mc_id)
    (d / "paths").mkdir(parents=True, exist_ok=True)
    return d


def delete_mc_dir(storage_root: Path, mc_id: str) -> None:
    path = mc_dir(storage_root, mc_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def write_config(storage_root: Path, mc_id: str, config: dict[str, Any]) -> None:
    ensure_mc_dir(storage_root, mc_id)
    (mc_dir(storage_root, mc_id) / "config.json").write_text(json.dumps(config, indent=2))


def read_config(storage_root: Path, mc_id: str) -> dict[str, Any] | None:
    path = mc_dir(storage_root, mc_id) / "config.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def _path_file(storage_root: Path, mc_id: str, index: int) -> Path:
    return paths_dir(storage_root, mc_id) / f"{index:04d}.npy"


def write_path_curve(
    storage_root: Path, mc_id: str, index: int, curve: np.ndarray
) -> None:
    ensure_mc_dir(storage_root, mc_id)
    data = np.asarray(curve, dtype=np.float32)
    np.save(_path_file(storage_root, mc_id, index), data, allow_pickle=False)


def read_path_curve(
    storage_root: Path, mc_id: str, index: int
) -> np.ndarray | None:
    f = _path_file(storage_root, mc_id, index)
    if not f.is_file():
        return None
    arr: np.ndarray = np.load(f, allow_pickle=False)
    return arr


def list_path_curves(storage_root: Path, mc_id: str) -> list[tuple[int, np.ndarray]]:
    d = paths_dir(storage_root, mc_id)
    if not d.is_dir():
        return []
    results: list[tuple[int, np.ndarray]] = []
    for f in sorted(d.iterdir()):
        if f.suffix == ".npy":
            idx = int(f.stem)
            results.append((idx, np.load(f, allow_pickle=False)))
    return results
