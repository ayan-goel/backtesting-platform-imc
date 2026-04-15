"""Server-side MC path runner.

Thin adapter over `engine.montecarlo.runner.simulate_day_mc` that
converts the engine result into the server-facing PathMetrics shape and
downsamples the curve for storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from engine.market.loader import MarketData
from engine.matching.base import Matcher
from engine.montecarlo.runner import downsample_curve, simulate_day_mc
from engine.simulator.runner import RunConfig

DOWNSAMPLE_N = 256


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


def run_mc_path(
    *,
    index: int = 0,
    trader: Any,
    market_data: MarketData,
    matcher: Matcher,
    config: RunConfig,
) -> PathResult:
    """Execute one MC path. No disk IO, no event log."""
    engine_result = simulate_day_mc(
        trader=trader,
        market_data=market_data,
        matcher=matcher,
        config=config,
    )
    summary = engine_result.summary
    metrics = PathMetrics(
        pnl_total=float(summary.pnl_total),
        pnl_by_product={k: float(v) for k, v in summary.pnl_by_product.items()},
        max_inventory_by_product=dict(summary.max_inventory_by_product),
        turnover_by_product=dict(summary.turnover_by_product),
        num_fills=int(engine_result.num_fills),
        max_drawdown=float(engine_result.max_drawdown),
        sharpe_intraday=float(engine_result.sharpe_intraday),
        duration_ms=int(engine_result.duration_ms),
    )
    downsampled = downsample_curve(engine_result.pnl_curve, n=DOWNSAMPLE_N)
    return PathResult(index=index, metrics=metrics, pnl_curve=downsampled)


__all__ = ["DOWNSAMPLE_N", "PathMetrics", "PathResult", "run_mc_path"]
