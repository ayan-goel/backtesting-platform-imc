"""Thin wrapper around `simulate_day` for Monte Carlo paths.

For T1 this just delegates to `simulate_day` and returns a PathResult
holding the headline PnL + run summary. T4 refactors `runner.py` to expose
a per-step callback so we can capture a compact PnL curve without writing
event logs.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engine.market.loader import MarketData
from engine.matching.base import Matcher
from engine.metrics.summary import RunSummary
from engine.simulator.runner import RunConfig, simulate_day


@dataclass(slots=True)
class PathMetrics:
    pnl_total: float
    pnl_by_product: dict[str, float]
    max_inventory_by_product: dict[str, int]
    turnover_by_product: dict[str, int]
    num_fills: int
    max_drawdown: float
    sharpe_intraday: float
    duration_ms: int


@dataclass(slots=True)
class PathResult:
    index: int
    metrics: PathMetrics
    pnl_curve: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    summary: RunSummary | None = None


def run_mc_path(
    *,
    index: int = 0,
    trader: Any,
    market_data: MarketData,
    matcher: Matcher,
    config: RunConfig,
) -> PathResult:
    """Execute one MC path. Returns metrics, optional curve.

    The path writes its events.jsonl to `config.output_dir` via the stock
    runner. We immediately delete that file to avoid bloating storage —
    MC paths are cheap to re-run and we never need per-event replay for
    them.
    """
    result = simulate_day(
        trader=trader,
        market_data=market_data,
        matcher=matcher,
        config=config,
    )
    # Dispose of events.jsonl so we don't leak thousands of files in mc_dir.
    if result.events_path.is_file():
        with contextlib.suppress(OSError):
            result.events_path.unlink()

    summary = result.summary
    num_fills = sum(summary.turnover_by_product.values())
    metrics = PathMetrics(
        pnl_total=summary.pnl_total,
        pnl_by_product=dict(summary.pnl_by_product),
        max_inventory_by_product=dict(summary.max_inventory_by_product),
        turnover_by_product=dict(summary.turnover_by_product),
        num_fills=num_fills,
        max_drawdown=0.0,
        sharpe_intraday=0.0,
        duration_ms=summary.duration_ms,
    )
    return PathResult(index=index, metrics=metrics, summary=summary)


def cleanup_mc_events(output_dir: Any) -> None:
    """Best-effort cleanup of any stray events.jsonl left in an MC dir."""
    try:
        path = output_dir / "events.jsonl"
        if path.is_file():
            path.unlink()
    except OSError:
        pass


__all__ = ["PathMetrics", "PathResult", "cleanup_mc_events", "run_mc_path"]
