"""Server-side adapter around `engine.montecarlo.aggregation.aggregate`.

Reads per-path curves from disk (written by the mc_runner after each
path) and delegates to the pure aggregator. Returns the fully-formed
subdoc ready for Mongo, or None if there is nothing to aggregate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.montecarlo.aggregation import PathMetricView, aggregate
from server.services.mc_path_runner import PathResult
from server.storage import mc_artifacts


def compute_aggregate(
    storage_root: Path,
    mc_id: str,
    *,
    path_results: list[PathResult] | None = None,
) -> dict[str, Any] | None:
    """Assemble aggregate stats for a completed MC simulation.

    If `path_results` is provided (the in-memory results collected by
    the runner in the current process), we use them directly. Otherwise
    we fall back to reading every `.npy` artifact under `mc_dir/paths/`
    and reconstructing a PnL view with `pnl_total = curve[-1]`. The
    fallback is lossy (no max_drawdown / num_fills) and is only used on
    post-hoc recomputation.
    """
    if path_results:
        views = [
            PathMetricView(
                pnl_total=p.metrics.pnl_total,
                max_drawdown=p.metrics.max_drawdown,
                num_fills=p.metrics.num_fills,
                curve=p.pnl_curve,
            )
            for p in path_results
        ]
    else:
        curves = mc_artifacts.list_path_curves(storage_root, mc_id)
        if not curves:
            return None
        views = [
            PathMetricView(
                pnl_total=float(curve[-1]) if curve.size else 0.0,
                max_drawdown=0.0,
                num_fills=0,
                curve=curve,
            )
            for _, curve in curves
        ]
    if not views:
        return None
    return aggregate(views)
