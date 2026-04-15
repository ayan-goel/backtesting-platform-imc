"""Historical calibration — extract the statistical fingerprint of a day.

Runs once per MC simulation (not once per path). Downstream generators
(block bootstrap, GBM, OU) consume the resulting `Calibration` object to
sample synthetic markets.

All fields are per-product. Data pathologies (missing mids, single-point
series) are handled defensively — calibrations on degenerate inputs
produce zero-variance estimates rather than raising.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from engine.market.loader import MarketData


@dataclass(frozen=True, slots=True)
class ProductCalibration:
    product: str
    # Per-timestamp mid price series, ordered by timestamp. NaN where the book
    # had no two-sided quote at that ts.
    mids: np.ndarray
    # Log-return statistics on non-NaN, non-zero pairs.
    log_return_mean: float
    log_return_std: float
    # AR(1) fit on mid levels: x_t = phi * x_{t-1} + (1 - phi) * mu + eps
    # `ar1_phi` here is the AR coefficient on the level itself. For a pure
    # random walk this is 1.0, for strong mean reversion it's closer to 0.
    ar1_phi: float
    ar1_residual_std: float
    ar1_long_run_mean: float
    # Empirical distributions sampled at every ts with a well-formed quote.
    spread_samples: np.ndarray  # shape (K,)
    bid_depth_samples: np.ndarray  # shape (K, 3) absolute volumes at levels 1..3
    ask_depth_samples: np.ndarray  # shape (K, 3) absolute volumes at levels 1..3
    # Market-trade statistics.
    trade_count_per_ts_mean: float
    trade_size_samples: np.ndarray  # shape (M,), positive ints
    # Level statistics used for reasonableness checks and starting-price choice.
    mid_level_first: float
    mid_level_last: float
    mid_level_mean: float
    mid_level_std: float


@dataclass(frozen=True, slots=True)
class Calibration:
    round_num: int
    day: int
    timestamps: tuple[int, ...]
    products: tuple[str, ...]
    per_product: dict[str, ProductCalibration] = field(default_factory=dict)

    def get(self, product: str) -> ProductCalibration:
        return self.per_product[product]


def calibrate(market_data: MarketData) -> Calibration:
    """Compute a `Calibration` for `market_data` in one pass."""
    per_product: dict[str, ProductCalibration] = {}
    for product in market_data.products:
        per_product[product] = _calibrate_product(market_data, product)
    return Calibration(
        round_num=market_data.round,
        day=market_data.day,
        timestamps=market_data.timestamps,
        products=market_data.products,
        per_product=per_product,
    )


def _calibrate_product(md: MarketData, product: str) -> ProductCalibration:
    n = len(md.timestamps)
    mids = np.full(n, np.nan, dtype=np.float64)
    spreads_list: list[float] = []
    bid_depths_list: list[list[int]] = []
    ask_depths_list: list[list[int]] = []
    trade_counts: list[int] = []
    trade_sizes_list: list[int] = []

    for i, ts in enumerate(md.timestamps):
        snap = md.frames[ts].get(product)
        if snap is None:
            continue
        depth = snap.order_depth
        best_bid = depth.best_bid()
        best_ask = depth.best_ask()
        if best_bid is not None and best_ask is not None:
            bid_p, _ = best_bid
            ask_p, _ = best_ask
            mids[i] = (bid_p + ask_p) / 2
            spreads_list.append(float(ask_p - bid_p))
            bid_depths_list.append(_top_levels(depth.buy_orders, descending=True))
            ask_depths_list.append(_top_levels(depth.sell_orders, descending=False))
        elif snap.mid_price is not None:
            mids[i] = float(snap.mid_price)

        mt = snap.market_trades
        trade_counts.append(len(mt))
        for trade in mt:
            trade_sizes_list.append(int(abs(trade.quantity)))

    log_return_mean, log_return_std = _log_return_stats(mids)
    ar1_phi, ar1_resid_std, ar1_mean = _ar1_fit(mids)

    spread_samples = np.asarray(spreads_list, dtype=np.float64)
    bid_depth_samples = (
        np.asarray(bid_depths_list, dtype=np.int64)
        if bid_depths_list
        else np.zeros((0, 3), dtype=np.int64)
    )
    ask_depth_samples = (
        np.asarray(ask_depths_list, dtype=np.int64)
        if ask_depths_list
        else np.zeros((0, 3), dtype=np.int64)
    )
    trade_size_samples = np.asarray(trade_sizes_list, dtype=np.int64)
    trade_count_mean = float(np.mean(trade_counts)) if trade_counts else 0.0

    observed = mids[~np.isnan(mids)]
    if observed.size == 0:
        mid_first = mid_last = mid_mean = mid_std = 0.0
    else:
        mid_first = float(observed[0])
        mid_last = float(observed[-1])
        mid_mean = float(np.mean(observed))
        mid_std = float(np.std(observed))

    return ProductCalibration(
        product=product,
        mids=mids,
        log_return_mean=log_return_mean,
        log_return_std=log_return_std,
        ar1_phi=ar1_phi,
        ar1_residual_std=ar1_resid_std,
        ar1_long_run_mean=ar1_mean,
        spread_samples=spread_samples,
        bid_depth_samples=bid_depth_samples,
        ask_depth_samples=ask_depth_samples,
        trade_count_per_ts_mean=trade_count_mean,
        trade_size_samples=trade_size_samples,
        mid_level_first=mid_first,
        mid_level_last=mid_last,
        mid_level_mean=mid_mean,
        mid_level_std=mid_std,
    )


def _top_levels(
    levels: Mapping[int, int], *, descending: bool
) -> list[int]:
    """Return absolute volumes at the top 3 levels, padded with 0."""
    items: list[tuple[int, int]] = list(levels.items())
    items.sort(key=lambda pv: pv[0], reverse=descending)
    vols = [abs(int(v)) for _, v in items[:3]]
    while len(vols) < 3:
        vols.append(0)
    return vols


def _log_return_stats(mids: np.ndarray) -> tuple[float, float]:
    """Compute (mean, std) of log returns over consecutive non-NaN pairs."""
    pairs = []
    for i in range(1, mids.size):
        a, b = mids[i - 1], mids[i]
        if math.isnan(a) or math.isnan(b) or a <= 0 or b <= 0:
            continue
        pairs.append(math.log(b / a))
    if len(pairs) < 2:
        return 0.0, 0.0
    arr = np.asarray(pairs, dtype=np.float64)
    return float(np.mean(arr)), float(np.std(arr, ddof=1))


def _ar1_fit(mids: np.ndarray) -> tuple[float, float, float]:
    """Fit AR(1) on the mid level: x_t = phi * x_{t-1} + c + eps.

    Returns `(phi, residual_std, long_run_mean)`. For a pure random walk
    phi == 1 and long_run_mean is undefined; we return the series mean as
    a safe fallback. For fewer than 3 valid points, returns (1.0, 0.0, mean).
    """
    observed_mask = ~np.isnan(mids)
    observed = mids[observed_mask]
    if observed.size < 3:
        mean = float(observed.mean()) if observed.size > 0 else 0.0
        return 1.0, 0.0, mean

    x_prev = observed[:-1]
    x_curr = observed[1:]
    mean = float(observed.mean())

    x_prev_dm = x_prev - mean
    x_curr_dm = x_curr - mean
    denom = float(np.dot(x_prev_dm, x_prev_dm))
    if denom <= 0:
        return 1.0, 0.0, mean
    phi = float(np.dot(x_prev_dm, x_curr_dm) / denom)
    # Clamp numerical noise.
    if phi > 1.0:
        phi = 1.0
    if phi < -1.0:
        phi = -1.0

    residuals = x_curr - (phi * x_prev + (1 - phi) * mean)
    resid_std = float(np.std(residuals, ddof=1)) if residuals.size > 1 else 0.0
    return phi, resid_std, mean
