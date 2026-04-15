"""GBM generator tests — statistical recovery and book well-formedness."""

from __future__ import annotations

import math

import numpy as np

from engine.datamodel.types import OrderDepth, Trade
from engine.market.loader import MarketData, ProductSnap
from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.calibration import calibrate
from engine.montecarlo.generators.gbm import GbmGenerator
from engine.montecarlo.rng import rng_for_path

from tests.engine._mc_fixtures import make_synthetic_market_data


def _drifting_md(
    *, n: int = 4000, mu: float = 0.0001, sigma: float = 0.002, seed: int = 1
) -> MarketData:
    rng = np.random.default_rng(seed)
    log_price = math.log(1000.0)
    mids: list[int] = []
    for _ in range(n):
        log_price += mu + sigma * float(rng.standard_normal())
        mids.append(int(round(math.exp(log_price))))
    timestamps = tuple(i * 100 for i in range(n))
    frames: dict[int, dict[str, ProductSnap]] = {}
    for i, ts in enumerate(timestamps):
        mid = mids[i]
        depth = OrderDepth(
            buy_orders={mid - 1: 10, mid - 2: 6, mid - 3: 3},
            sell_orders={mid + 1: -10, mid + 2: -6, mid + 3: -3},
        )
        trades = (Trade(symbol="X", price=mid, quantity=2, timestamp=ts),)
        frames[ts] = {
            "X": ProductSnap(order_depth=depth, market_trades=trades, mid_price=float(mid))
        }
    return MarketData(round=0, day=0, timestamps=timestamps, products=("X",), frames=frames)


def test_gbm_generates_valid_books() -> None:
    md = make_synthetic_market_data(num_timestamps=60)
    cal = calibrate(md)
    out = build_synthetic_market_data(
        historical=md,
        generator=GbmGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=1, path_index=0),
    )
    for ts in out.timestamps:
        for product, snap in out.frames[ts].items():
            bid = snap.order_depth.best_bid()
            ask = snap.order_depth.best_ask()
            assert bid is not None and ask is not None
            assert bid[0] < ask[0], f"{product} ts={ts} bid>=ask"


def test_gbm_preserves_spine() -> None:
    md = make_synthetic_market_data(num_timestamps=40)
    cal = calibrate(md)
    out = build_synthetic_market_data(
        historical=md,
        generator=GbmGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=2, path_index=0),
    )
    assert out.timestamps == md.timestamps
    assert out.products == md.products


def test_gbm_determinism_same_seed() -> None:
    md = make_synthetic_market_data(num_timestamps=40)
    cal = calibrate(md)
    a = build_synthetic_market_data(
        historical=md,
        generator=GbmGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    b = build_synthetic_market_data(
        historical=md,
        generator=GbmGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    for ts in md.timestamps:
        assert a.frames[ts]["KELP"].order_depth.best_bid() == b.frames[ts]["KELP"].order_depth.best_bid()
        assert a.frames[ts]["KELP"].order_depth.best_ask() == b.frames[ts]["KELP"].order_depth.best_ask()


def test_gbm_recovers_volatility_on_long_path() -> None:
    md = _drifting_md(n=4000, mu=0.0001, sigma=0.002, seed=123)
    cal = calibrate(md)
    out = build_synthetic_market_data(
        historical=md,
        generator=GbmGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    mids = np.asarray(
        [float(out.frames[ts]["X"].mid_price or 0) for ts in out.timestamps]
    )
    log_rets = np.log(mids[1:] / mids[:-1])
    # Recovered sigma should be close to the calibrated sigma.
    recovered_sigma = float(log_rets.std(ddof=1))
    calibrated_sigma = float(cal.get("X").log_return_std)
    assert abs(recovered_sigma - calibrated_sigma) / max(calibrated_sigma, 1e-9) < 0.3


def test_gbm_zero_volatility_is_constant() -> None:
    md = make_synthetic_market_data(num_timestamps=40)
    cal = calibrate(md)
    # Force zero log-return std by overriding via a new Calibration built from
    # a constant-mid series. Simpler: use a flat synthetic MD.
    timestamps = tuple(i * 100 for i in range(30))
    frames: dict[int, dict[str, ProductSnap]] = {}
    for ts in timestamps:
        depth = OrderDepth(buy_orders={99: 5}, sell_orders={101: -5})
        frames[ts] = {
            "FLAT": ProductSnap(order_depth=depth, market_trades=(), mid_price=100.0)
        }
    flat_md = MarketData(
        round=0, day=0, timestamps=timestamps, products=("FLAT",), frames=frames
    )
    flat_cal = calibrate(flat_md)
    out = build_synthetic_market_data(
        historical=flat_md,
        generator=GbmGenerator(),
        calibration=flat_cal,
        params={},
        rng=rng_for_path(run_seed=1, path_index=0),
    )
    mids = [out.frames[ts]["FLAT"].mid_price for ts in out.timestamps]
    # All equal to the starting price.
    assert len(set(mids)) == 1
