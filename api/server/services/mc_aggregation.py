"""Aggregate statistics for an MC simulation.

Populated in T5. For T1 this is a placeholder that returns None so
`mc_runner._finalize` can skip writing aggregate stats gracefully.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from server.services.mc_path_runner import PathResult


def compute_aggregate(
    storage_root: Path,
    mc_id: str,
    *,
    path_results: list[PathResult] | None = None,
) -> dict[str, Any] | None:
    """Placeholder — returns None so the runner skips persistence in T1.

    T5 replaces this with the real histogram/quantile aggregator.
    """
    return None
