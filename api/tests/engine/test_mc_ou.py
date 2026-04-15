"""OU (mean-reverting) generator tests."""

from __future__ import annotations

import numpy as np

from engine.datamodel.types import OrderDepth, Trade
from engine.market.loader import MarketData, ProductSnap
from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.calibration import calibrate
from engine.montecarlo.generators.ou import OuGenerator
from engine.montecarlo.rng import rng_for_path

from tests.engine._mc_fixtures import make_synthetic_market_data


def _mean_reverting_md(*, mu: float = 500.0, phi: float = 0.8, n: int = 4000) -> MarketData:
    rng = np.random.default_rng(77)
    price = mu
    mids: list[int] = []
    for _ in range(n):
        price = phi * price + (1 - phi) * mu + float(rng.standard_normal()) * 1.5
        mids.append(int(round(price)))
    timestamps = tuple(i * 100 for i in range(n))
    frames: dict[int, dict[str, ProductSnap]] = {}
    for i, ts in enumerate(timestamps):
        mid = mids[i]
        depth = OrderDepth(
            buy_orders={mid - 1: 10, mid - 2: 6, mid - 3: 3},
            sell_orders={mid + 1: -10, mid + 2: -6, mid + 3: -3},
        )
        trades = (Trade(symbol="Y", price=mid, quantity=2, timestamp=ts),)
        frames[ts] = {
            "Y": ProductSnap(order_depth=depth, market_trades=trades, mid_price=float(mid))
        }
    return MarketData(
        round=0, day=0, timestamps=timestamps, products=("Y",), frames=frames
    )


def test_ou_generates_valid_books() -> None:
    md = make_synthetic_market_data(num_timestamps=60)
    cal = calibrate(md)
    out = build_synthetic_market_data(
        historical=md,
        generator=OuGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=1, path_index=0),
    )
    for ts in out.timestamps:
        for snap in out.frames[ts].values():
            bid = snap.order_depth.best_bid()
            ask = snap.order_depth.best_ask()
            assert bid is not None and ask is not None
            assert bid[0] < ask[0]


def test_ou_determinism() -> None:
    md = make_synthetic_market_data(num_timestamps=40)
    cal = calibrate(md)
    a = build_synthetic_market_data(
        historical=md,
        generator=OuGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    b = build_synthetic_market_data(
        historical=md,
        generator=OuGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    for ts in md.timestamps:
        assert a.frames[ts]["KELP"].mid_price == b.frames[ts]["KELP"].mid_price


def test_ou_recovers_phi_on_mean_reverting_series() -> None:
    md = _mean_reverting_md(mu=500.0, phi=0.8, n=4000)
    cal = calibrate(md)
    # The calibration's ar1_phi should already recover phi closely.
    assert 0.7 < cal.get("Y").ar1_phi < 0.88

    out = build_synthetic_market_data(
        historical=md,
        generator=OuGenerator(),
        calibration=cal,
        params={},
        rng=rng_for_path(run_seed=1, path_index=0),
    )
    mids = np.asarray(
        [float(out.frames[ts]["Y"].mid_price or 0) for ts in out.timestamps]
    )
    # Mean of the synthetic series should be near the calibrated long-run mean.
    assert abs(float(mids.mean()) - cal.get("Y").ar1_long_run_mean) < 10.0


def test_ou_distribution_tighter_than_gbm_on_mean_reverting_product() -> None:
    from engine.montecarlo.generators.gbm import GbmGenerator

    md = _mean_reverting_md(mu=500.0, phi=0.7, n=4000)
    cal = calibrate(md)

    def std_of_paths(gen_cls) -> float:
        mids_over_paths: list[float] = []
        for path in range(20):
            rng = rng_for_path(run_seed=42, path_index=path)
            out = build_synthetic_market_data(
                historical=md,
                generator=gen_cls(),
                calibration=cal,
                params={},
                rng=rng,
            )
            mids = np.asarray(
                [float(out.frames[ts]["Y"].mid_price or 0) for ts in out.timestamps]
            )
            mids_over_paths.append(float(mids.std()))
        return float(np.mean(mids_over_paths))

    ou_std = std_of_paths(OuGenerator)
    gbm_std = std_of_paths(GbmGenerator)
    assert ou_std < gbm_std, f"OU not tighter than GBM: {ou_std=} vs {gbm_std=}"
