"""Unit tests for the pure aggregator in engine.montecarlo.aggregation."""

from __future__ import annotations

import numpy as np

from engine.montecarlo.aggregation import (
    HISTOGRAM_BINS,
    PathMetricView,
    aggregate,
)


def _view(pnl: float, *, curve: np.ndarray | None = None, dd: float = 0.0, fills: int = 0) -> PathMetricView:
    if curve is None:
        curve = np.array([0.0, pnl / 2, pnl], dtype=np.float32)
    return PathMetricView(
        pnl_total=pnl, max_drawdown=dd, num_fills=fills, curve=curve.astype(np.float32)
    )


def test_empty_paths_returns_empty_dict() -> None:
    assert aggregate([]) == {}


def test_single_path_stats() -> None:
    view = _view(100.0, dd=-20.0, fills=5)
    out = aggregate([view])
    assert out["pnl_mean"] == 100.0
    assert out["pnl_std"] == 0.0
    assert out["pnl_median"] == 100.0
    assert out["pnl_min"] == 100.0
    assert out["pnl_max"] == 100.0
    assert out["winrate"] == 1.0
    assert out["sharpe_across_paths"] == 0.0  # zero std guard
    assert out["max_drawdown_mean"] == -20.0
    assert out["num_fills_mean"] == 5.0


def test_mean_std_quantiles_match_numpy() -> None:
    pnls = np.asarray([100.0, 200.0, 300.0, 400.0, 500.0], dtype=np.float64)
    views = [_view(float(p)) for p in pnls]
    out = aggregate(views)
    assert abs(out["pnl_mean"] - float(pnls.mean())) < 1e-9
    assert abs(out["pnl_std"] - float(pnls.std(ddof=1))) < 1e-9
    assert abs(out["pnl_median"] - float(np.median(pnls))) < 1e-9
    assert out["pnl_quantiles"]["p50"] == 300.0
    assert out["pnl_quantiles"]["p05"] == 120.0
    assert out["pnl_quantiles"]["p95"] == 480.0


def test_winrate_fraction() -> None:
    pnls = [10.0, -10.0, 20.0, -5.0, 30.0]
    out = aggregate([_view(p) for p in pnls])
    assert out["winrate"] == 3 / 5


def test_histogram_has_correct_bin_count() -> None:
    rng = np.random.default_rng(0)
    pnls = rng.normal(loc=0.0, scale=100.0, size=500).tolist()
    out = aggregate([_view(p) for p in pnls])
    hist = out["pnl_histogram"]
    assert len(hist["counts"]) == HISTOGRAM_BINS
    assert len(hist["bin_edges"]) == HISTOGRAM_BINS + 1


def test_histogram_counts_sum_to_n() -> None:
    pnls = list(range(-50, 50))
    out = aggregate([_view(float(p)) for p in pnls])
    assert sum(out["pnl_histogram"]["counts"]) == len(pnls)


def test_histogram_degenerate_single_value() -> None:
    pnls = [42.0] * 10
    out = aggregate([_view(p) for p in pnls])
    hist = out["pnl_histogram"]
    assert len(hist["counts"]) == HISTOGRAM_BINS
    assert sum(hist["counts"]) == len(pnls)


def test_curve_quantiles_returned_when_curves_present() -> None:
    # Five paths of identical shape but shifted by pnl
    n = 16
    views: list[PathMetricView] = []
    for shift in [10, 20, 30, 40, 50]:
        curve = np.linspace(0.0, float(shift), n, dtype=np.float32)
        views.append(
            PathMetricView(
                pnl_total=float(shift), max_drawdown=0.0, num_fills=0, curve=curve
            )
        )
    out = aggregate(views)
    cq = out["pnl_curve_quantiles"]
    assert cq is not None
    assert len(cq["ts_grid"]) == n
    assert len(cq["p05"]) == n
    # At the last step, the median of [10,20,30,40,50] is 30.
    assert abs(cq["p50"][-1] - 30.0) < 1e-6
    assert abs(cq["p05"][-1] - 12.0) < 1e-6
    assert abs(cq["p95"][-1] - 48.0) < 1e-6


def test_curve_quantiles_none_when_lengths_differ() -> None:
    a = PathMetricView(
        pnl_total=1.0,
        max_drawdown=0.0,
        num_fills=0,
        curve=np.array([0, 1, 2], dtype=np.float32),
    )
    b = PathMetricView(
        pnl_total=1.0,
        max_drawdown=0.0,
        num_fills=0,
        curve=np.array([0, 1], dtype=np.float32),
    )
    out = aggregate([a, b])
    assert out["pnl_curve_quantiles"] is None


def test_all_negative_pnls_gives_zero_winrate() -> None:
    out = aggregate([_view(-10.0), _view(-5.0), _view(-1.0)])
    assert out["winrate"] == 0.0
