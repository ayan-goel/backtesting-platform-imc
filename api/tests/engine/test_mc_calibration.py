"""Unit tests for `engine.montecarlo.calibration.calibrate`."""

from __future__ import annotations

import math

import numpy as np

from engine.datamodel.types import OrderDepth, Trade
from engine.market.loader import MarketData, ProductSnap
from engine.montecarlo.calibration import calibrate


def _linear_md(
    mids: list[int], spreads: list[int], product: str = "KELP"
) -> MarketData:
    assert len(mids) == len(spreads)
    timestamps = tuple(i * 100 for i in range(len(mids)))
    frames: dict[int, dict[str, ProductSnap]] = {}
    for i, ts in enumerate(timestamps):
        mid = mids[i]
        s = spreads[i]
        bid = mid - s // 2
        ask = mid + s - s // 2
        depth = OrderDepth(
            buy_orders={bid: 10, bid - 1: 6, bid - 2: 3},
            sell_orders={ask: -10, ask + 1: -6, ask + 2: -3},
        )
        trades = (
            Trade(symbol=product, price=mid, quantity=2, timestamp=ts),
            Trade(symbol=product, price=mid, quantity=5, timestamp=ts),
        )
        frames[ts] = {
            product: ProductSnap(
                order_depth=depth, market_trades=trades, mid_price=float(mid)
            )
        }
    return MarketData(
        round=0, day=0, timestamps=timestamps, products=(product,), frames=frames
    )


def test_calibrate_returns_entry_per_product() -> None:
    md = _linear_md(mids=[100, 101, 102, 103, 104], spreads=[2] * 5)
    cal = calibrate(md)
    assert cal.products == ("KELP",)
    assert "KELP" in cal.per_product


def test_spread_samples_equal_observed_spreads() -> None:
    md = _linear_md(mids=[100] * 10, spreads=[4] * 10)
    pc = calibrate(md).get("KELP")
    assert np.all(pc.spread_samples == 4)
    assert pc.spread_samples.size == 10


def test_bid_ask_depth_samples_shape() -> None:
    md = _linear_md(mids=[100] * 5, spreads=[2] * 5)
    pc = calibrate(md).get("KELP")
    assert pc.bid_depth_samples.shape == (5, 3)
    assert pc.ask_depth_samples.shape == (5, 3)
    assert (pc.bid_depth_samples[:, 0] == 10).all()
    assert (pc.ask_depth_samples[:, 0] == 10).all()


def test_log_return_mean_on_constant_series_is_zero() -> None:
    md = _linear_md(mids=[100] * 20, spreads=[2] * 20)
    pc = calibrate(md).get("KELP")
    assert pc.log_return_mean == 0.0
    assert pc.log_return_std == 0.0


def test_log_return_stats_match_numpy_reference() -> None:
    mids = [100, 101, 103, 102, 104, 105, 103]
    md = _linear_md(mids=mids, spreads=[2] * len(mids))
    pc = calibrate(md).get("KELP")
    expected = np.log(np.asarray(mids[1:]) / np.asarray(mids[:-1]))
    assert math.isclose(pc.log_return_mean, float(expected.mean()), rel_tol=1e-12)
    assert math.isclose(
        pc.log_return_std, float(expected.std(ddof=1)), rel_tol=1e-12
    )


def test_ar1_fit_recovers_random_walk() -> None:
    rng = np.random.default_rng(42)
    prices = [100.0]
    for _ in range(400):
        prices.append(prices[-1] + float(rng.standard_normal()))
    int_prices = [round(p) for p in prices]
    md = _linear_md(mids=int_prices, spreads=[2] * len(int_prices))
    pc = calibrate(md).get("KELP")
    assert pc.ar1_phi > 0.9  # near 1.0 for a random walk


def test_ar1_fit_recovers_mean_reversion() -> None:
    rng = np.random.default_rng(42)
    mu = 500.0
    phi_true = 0.8
    sigma = 1.0
    series = [mu]
    for _ in range(2000):
        nxt = phi_true * series[-1] + (1 - phi_true) * mu + rng.standard_normal() * sigma
        series.append(nxt)
    int_prices = [round(x) for x in series]
    md = _linear_md(mids=int_prices, spreads=[2] * len(int_prices))
    pc = calibrate(md).get("KELP")
    assert 0.7 < pc.ar1_phi < 0.88
    assert abs(pc.ar1_long_run_mean - mu) < 5.0


def test_trade_count_and_size_samples() -> None:
    md = _linear_md(mids=[100] * 10, spreads=[2] * 10)
    pc = calibrate(md).get("KELP")
    assert pc.trade_count_per_ts_mean == 2.0
    assert pc.trade_size_samples.tolist().count(2) == 10
    assert pc.trade_size_samples.tolist().count(5) == 10


def test_missing_mids_survive_gracefully() -> None:
    timestamps = (0, 100, 200)
    empty_depth = OrderDepth(buy_orders={}, sell_orders={})
    valid_depth = OrderDepth(buy_orders={99: 10}, sell_orders={101: -10})
    frames = {
        0: {
            "X": ProductSnap(order_depth=empty_depth, market_trades=(), mid_price=None)
        },
        100: {
            "X": ProductSnap(order_depth=valid_depth, market_trades=(), mid_price=100.0)
        },
        200: {
            "X": ProductSnap(order_depth=empty_depth, market_trades=(), mid_price=None)
        },
    }
    md = MarketData(
        round=0, day=0, timestamps=timestamps, products=("X",), frames=frames
    )
    pc = calibrate(md).get("X")
    assert pc.log_return_std == 0.0  # too few pairs
    assert pc.spread_samples.size == 1
    assert pc.mid_level_first == 100.0


def test_single_point_series_returns_safe_defaults() -> None:
    md = _linear_md(mids=[100], spreads=[2])
    pc = calibrate(md).get("KELP")
    assert pc.log_return_mean == 0.0
    assert pc.log_return_std == 0.0
    assert pc.ar1_phi == 1.0
    assert pc.ar1_residual_std == 0.0
