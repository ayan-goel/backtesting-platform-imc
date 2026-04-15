"""Shared helper for parametric generators (GBM, OU).

Reconstructs a believable 3-level order book around a synthetic mid
price by sampling spreads and depth volumes from the historical
empirical distributions captured in `Calibration`, and synthesizes a
market-trade pool from the empirical trade rate + size distribution.

Kept deliberately simple — the point of this module is that the matcher
and PnL code keep being the single source of truth. We care about
"plausible enough that the strategy's fills look right" more than
"reproduces microstructure".
"""

from __future__ import annotations

import numpy as np

from engine.datamodel.types import OrderDepth, Trade
from engine.market.loader import ProductSnap
from engine.montecarlo.calibration import ProductCalibration


def synthesize_snap(
    *,
    product: str,
    mid: float,
    ts: int,
    calibration: ProductCalibration,
    rng: np.random.Generator,
) -> ProductSnap:
    """Build one ProductSnap with a synthesized book + market trades."""
    mid_int = round(mid)
    spread = _sample_spread(calibration, rng)
    half = max(1, spread // 2)
    bid1 = mid_int - half
    ask1 = bid1 + spread
    if ask1 <= bid1:
        ask1 = bid1 + 1

    bid_vols = _sample_depth(calibration.bid_depth_samples, rng)
    ask_vols = _sample_depth(calibration.ask_depth_samples, rng)

    buy_orders = {
        bid1: int(max(1, bid_vols[0])),
        bid1 - 1: int(max(1, bid_vols[1])),
        bid1 - 2: int(max(1, bid_vols[2])),
    }
    sell_orders = {
        ask1: -int(max(1, ask_vols[0])),
        ask1 + 1: -int(max(1, ask_vols[1])),
        ask1 + 2: -int(max(1, ask_vols[2])),
    }
    depth = OrderDepth(buy_orders=buy_orders, sell_orders=sell_orders)

    trades = _sample_market_trades(
        product=product,
        mid_int=mid_int,
        ts=ts,
        calibration=calibration,
        rng=rng,
    )

    return ProductSnap(order_depth=depth, market_trades=trades, mid_price=float(mid_int))


def _sample_spread(cal: ProductCalibration, rng: np.random.Generator) -> int:
    samples = cal.spread_samples
    if samples.size == 0:
        return 2
    idx = int(rng.integers(0, samples.size))
    return max(1, round(float(samples[idx])))


def _sample_depth(
    samples: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    if samples.shape[0] == 0:
        return np.asarray([10, 6, 3], dtype=np.int64)
    idx = int(rng.integers(0, samples.shape[0]))
    return samples[idx]


def _sample_market_trades(
    *,
    product: str,
    mid_int: int,
    ts: int,
    calibration: ProductCalibration,
    rng: np.random.Generator,
) -> tuple[Trade, ...]:
    rate = float(calibration.trade_count_per_ts_mean)
    if rate <= 0 or calibration.trade_size_samples.size == 0:
        return ()
    k = int(rng.poisson(rate))
    if k == 0:
        return ()
    sizes = calibration.trade_size_samples
    trades: list[Trade] = []
    for _ in range(k):
        size_idx = int(rng.integers(0, sizes.size))
        qty = int(max(1, sizes[size_idx]))
        trades.append(
            Trade(
                symbol=product,
                price=mid_int,
                quantity=qty,
                buyer=None,
                seller=None,
                timestamp=ts,
            )
        )
    return tuple(trades)


__all__ = ["synthesize_snap"]
