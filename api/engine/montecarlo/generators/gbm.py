"""Geometric Brownian Motion generator.

Simulates mid prices as `S_{t+1} = S_t * exp((mu - 0.5 sigma^2) dt + sigma sqrt(dt) Z)`
with `dt = 1` per tick, calibrated from historical log returns. Integer-rounded.
The book is reconstructed from empirical spread/depth samples by
`_book_synth.synthesize_snap`.

Products with near-zero calibrated volatility are held constant at the
starting price (a safe degeneracy — log returns were flat historically).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from engine.market.loader import MarketData, ProductSnap
from engine.montecarlo.calibration import Calibration, ProductCalibration
from engine.montecarlo.generators._book_synth import synthesize_snap


@dataclass(frozen=True, slots=True)
class GbmGenerator:
    name: ClassVar[str] = "gbm"

    def generate(
        self,
        *,
        historical: MarketData,
        calibration: Calibration,
        params: Mapping[str, Any] | None = None,
        rng: np.random.Generator,
    ) -> MarketData:
        if calibration is None:
            raise ValueError("gbm generator requires calibration")
        p = params or {}
        mu_scale = float(p.get("mu_scale", 1.0))
        sigma_scale = float(p.get("sigma_scale", 1.0))
        starting_price_from = p.get("starting_price_from", "historical_first")

        timestamps = historical.timestamps
        n_ts = len(timestamps)
        frames: dict[int, dict[str, ProductSnap]] = {ts: {} for ts in timestamps}

        for product in historical.products:
            cal = calibration.get(product)
            mu = cal.log_return_mean * mu_scale
            sigma = cal.log_return_std * sigma_scale

            start_price = _pick_start_price(cal, starting_price_from)
            if start_price <= 0:
                start_price = 1.0

            if sigma <= 0:
                mids = np.full(n_ts, start_price, dtype=np.float64)
            else:
                z = rng.standard_normal(n_ts - 1)
                log_returns = (mu - 0.5 * sigma * sigma) + sigma * z
                logs = np.concatenate([[np.log(start_price)], np.log(start_price) + np.cumsum(log_returns)])
                mids = np.exp(logs)

            for i, ts in enumerate(timestamps):
                frames[ts][product] = synthesize_snap(
                    product=product,
                    mid=float(mids[i]),
                    ts=ts,
                    calibration=cal,
                    rng=rng,
                )

        return MarketData(
            round=historical.round,
            day=historical.day,
            timestamps=timestamps,
            products=historical.products,
            frames=frames,
        )


def _pick_start_price(cal: ProductCalibration, source: str) -> float:
    if source == "historical_last" and cal.mid_level_last > 0:
        return cal.mid_level_last
    if cal.mid_level_first > 0:
        return cal.mid_level_first
    if cal.mid_level_mean > 0:
        return cal.mid_level_mean
    return 100.0
