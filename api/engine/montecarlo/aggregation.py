"""Fold per-path metrics into a distribution summary.

Produces the `aggregate` subdoc stored on the parent mc doc:
- headline pnl stats (mean, median, std, min, max)
- quantiles: p01..p99
- winrate, cross-path sharpe
- pnl histogram (30 bins, edges anchored to [p01, p99] ∪ [min, max])
- curve quantile bands for the fan chart (p05/p25/p50/p75/p95)
- max-drawdown + fill-count summary stats

All computations are deterministic given the same path input, and the
module is pure — no filesystem IO. The MC runner calls `aggregate`
exactly once, after the last path finishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

HISTOGRAM_BINS = 30
CURVE_QUANTILE_LEN = 256


@dataclass(slots=True)
class PathMetricView:
    pnl_total: float
    max_drawdown: float
    num_fills: int
    curve: np.ndarray  # shape (N,), float32


def aggregate(paths: list[PathMetricView]) -> dict[str, Any]:
    """Return the `aggregate` subdoc dict, or an empty dict if no paths."""
    if not paths:
        return {}

    pnls = np.asarray([p.pnl_total for p in paths], dtype=np.float64)
    drawdowns = np.asarray([p.max_drawdown for p in paths], dtype=np.float64)
    fills = np.asarray([p.num_fills for p in paths], dtype=np.float64)

    pnl_mean = float(pnls.mean())
    pnl_std = float(pnls.std(ddof=1)) if pnls.size > 1 else 0.0
    pnl_median = float(np.median(pnls))
    pnl_min = float(pnls.min())
    pnl_max = float(pnls.max())

    quantile_labels = ("p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99")
    quantile_qs = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
    quantile_values = np.quantile(pnls, quantile_qs)
    pnl_quantiles = {
        label: float(v) for label, v in zip(quantile_labels, quantile_values)
    }

    winrate = float((pnls > 0).mean())
    sharpe_across = pnl_mean / pnl_std if pnl_std > 0 else 0.0

    hist = _histogram(pnls, quantile_values)

    curve_quantiles = _curve_quantiles(paths)

    return {
        "pnl_mean": pnl_mean,
        "pnl_std": pnl_std,
        "pnl_median": pnl_median,
        "pnl_min": pnl_min,
        "pnl_max": pnl_max,
        "pnl_quantiles": pnl_quantiles,
        "winrate": winrate,
        "sharpe_across_paths": sharpe_across,
        "max_drawdown_mean": float(drawdowns.mean()),
        "max_drawdown_p05": float(np.quantile(drawdowns, 0.05)),
        "num_fills_mean": float(fills.mean()),
        "pnl_histogram": hist,
        "pnl_curve_quantiles": curve_quantiles,
    }


def _histogram(pnls: np.ndarray, quantile_values: np.ndarray) -> dict[str, Any]:
    """Fixed 30-bin histogram anchored to [p01, p99] if that's a valid range.

    Any samples outside [p01, p99] are clamped into the edge bins. If the
    anchored range is degenerate (p01 == p99), fall back to [min, max].
    """
    p01 = float(quantile_values[0])
    p99 = float(quantile_values[-1])
    lo: float
    hi: float
    if p99 > p01:
        lo, hi = p01, p99
    else:
        mn = float(pnls.min())
        mx = float(pnls.max())
        if mx == mn:
            lo, hi = mn - 1.0, mx + 1.0
        else:
            lo, hi = mn, mx
    edges = np.linspace(lo, hi, HISTOGRAM_BINS + 1)
    clamped = np.clip(pnls, lo, hi)
    counts, _ = np.histogram(clamped, bins=edges)
    return {
        "bin_edges": [float(x) for x in edges],
        "counts": [int(c) for c in counts],
    }


def _curve_quantiles(paths: list[PathMetricView]) -> dict[str, Any] | None:
    """Stack per-path curves and compute per-step quantile bands.

    All curves are assumed to be the same length (enforced by the path
    runner's `DOWNSAMPLE_N`). Returns None if any curve is empty.
    """
    lengths = {p.curve.size for p in paths}
    if len(lengths) != 1 or 0 in lengths:
        return None
    stacked = np.stack([p.curve for p in paths], axis=0).astype(np.float64)
    n = stacked.shape[1]
    qs = np.quantile(stacked, [0.05, 0.25, 0.50, 0.75, 0.95], axis=0)
    ts_grid = list(range(n))
    return {
        "ts_grid": ts_grid,
        "p05": [float(x) for x in qs[0]],
        "p25": [float(x) for x in qs[1]],
        "p50": [float(x) for x in qs[2]],
        "p75": [float(x) for x in qs[3]],
        "p95": [float(x) for x in qs[4]],
    }


__all__ = ["HISTOGRAM_BINS", "CURVE_QUANTILE_LEN", "PathMetricView", "aggregate"]
