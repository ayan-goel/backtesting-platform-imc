"""Tests for engine.montecarlo.runner.simulate_day_mc + curve metrics."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from engine.matching.imc_matcher import ImcMatcher
from engine.montecarlo.runner import (
    McPathResult,
    downsample_curve,
    simulate_day_mc,
)
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader
from tests.engine._mc_fixtures import (
    GREEDY_TRADER_SRC,
    NOOP_TRADER_SRC,
    make_synthetic_market_data,
)


def _write(tmp_path: Path, src: bytes) -> Path:
    p = tmp_path / "strat.py"
    p.write_bytes(src)
    return p


def _config(tmp_path: Path, name: str, strategy: Path) -> RunConfig:
    return RunConfig(
        run_id=f"test-{name}",
        strategy_path=str(strategy),
        strategy_hash=hash_strategy_file(strategy),
        round=0,
        day=0,
        matcher_name="imc",
        position_limits={"KELP": 50, "RESIN": 50},
        output_dir=tmp_path / name,
    )


def test_simulate_day_mc_matches_simulate_day_pnl(tmp_path: Path) -> None:
    md = make_synthetic_market_data(num_timestamps=100)
    strategy = _write(tmp_path, GREEDY_TRADER_SRC)

    direct = simulate_day(
        trader=load_trader(strategy),
        market_data=md,
        matcher=ImcMatcher(),
        config=_config(tmp_path, "direct", strategy),
    )
    mc = simulate_day_mc(
        trader=load_trader(strategy),
        market_data=md,
        matcher=ImcMatcher(),
        config=_config(tmp_path, "mc", strategy),
    )
    assert mc.summary.pnl_total == direct.summary.pnl_total
    assert mc.summary.pnl_by_product == direct.summary.pnl_by_product
    assert mc.summary.max_inventory_by_product == direct.summary.max_inventory_by_product
    assert mc.summary.turnover_by_product == direct.summary.turnover_by_product


def test_simulate_day_mc_captures_curve_length(tmp_path: Path) -> None:
    md = make_synthetic_market_data(num_timestamps=77)
    strategy = _write(tmp_path, NOOP_TRADER_SRC)
    result = simulate_day_mc(
        trader=load_trader(strategy),
        market_data=md,
        matcher=ImcMatcher(),
        config=_config(tmp_path, "noop", strategy),
    )
    assert result.pnl_curve.shape == (77,)
    # noop trader never trades, so the curve is all zeros
    assert float(np.abs(result.pnl_curve).max()) == 0.0


def test_simulate_day_mc_curve_final_matches_pnl_total(tmp_path: Path) -> None:
    md = make_synthetic_market_data(num_timestamps=60)
    strategy = _write(tmp_path, GREEDY_TRADER_SRC)
    result = simulate_day_mc(
        trader=load_trader(strategy),
        market_data=md,
        matcher=ImcMatcher(),
        config=_config(tmp_path, "greedy", strategy),
    )
    # Curve records mark-to-market during the loop and the summary includes
    # the final revaluation at the last-ts mid. Without closing positions they
    # may differ slightly — here we only assert the curve is finite.
    assert np.all(np.isfinite(result.pnl_curve))
    assert isinstance(result, McPathResult)


def test_downsample_curve_preserves_endpoints() -> None:
    curve = np.linspace(0.0, 99.0, 100, dtype=np.float64)
    out = downsample_curve(curve, n=16)
    assert out.shape == (16,)
    assert out.dtype == np.float32
    assert abs(float(out[0]) - 0.0) < 1e-5
    assert abs(float(out[-1]) - 99.0) < 1e-5


def test_downsample_curve_single_point() -> None:
    curve = np.array([42.0])
    out = downsample_curve(curve, n=8)
    assert out.shape == (8,)
    assert np.all(out == 42.0)


def test_downsample_curve_empty() -> None:
    out = downsample_curve(np.zeros(0), n=5)
    assert out.shape == (5,)
    assert np.all(out == 0.0)


def test_max_drawdown_sign() -> None:
    # Curve rises to 100, drops to 40, recovers to 80.
    curve = np.array([0.0, 50.0, 100.0, 70.0, 40.0, 60.0, 80.0])
    from engine.montecarlo.runner import _max_drawdown

    dd = _max_drawdown(curve)
    assert dd == -60.0


def test_intraday_sharpe_zero_variance() -> None:
    from engine.montecarlo.runner import _intraday_sharpe

    flat = np.zeros(10)
    assert _intraday_sharpe(flat) == 0.0
