"""Ornstein-Uhlenbeck (mean-reverting) generator.

Uses the AR(1) fit captured during calibration:

    x_{t+1} = phi * x_t + (1 - phi) * mu + eps,   eps ~ N(0, sigma^2)

where `phi` is the AR coefficient on the level and `mu` is the long-run
mean. Pure random walks (phi ≈ 1) produce the same behaviour as GBM at
this tick resolution; for mean-reverting products (phi << 1) prices
revert towards `mu`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from engine.market.loader import MarketData, ProductSnap
from engine.montecarlo.calibration import Calibration
from engine.montecarlo.generators._book_synth import synthesize_snap


@dataclass(frozen=True, slots=True)
class OuGenerator:
    name: ClassVar[str] = "ou"

    def generate(
        self,
        *,
        historical: MarketData,
        calibration: Calibration,
        params: Mapping[str, Any] | None = None,
        rng: np.random.Generator,
    ) -> MarketData:
        if calibration is None:
            raise ValueError("ou generator requires calibration")
        p = params or {}
        phi_scale = float(p.get("phi_scale", 1.0))
        sigma_scale = float(p.get("sigma_scale", 1.0))

        timestamps = historical.timestamps
        n_ts = len(timestamps)
        frames: dict[int, dict[str, ProductSnap]] = {ts: {} for ts in timestamps}

        for product in historical.products:
            cal = calibration.get(product)
            phi = float(np.clip(cal.ar1_phi * phi_scale, -0.999, 0.999))
            sigma = cal.ar1_residual_std * sigma_scale
            mu = cal.ar1_long_run_mean if cal.ar1_long_run_mean > 0 else cal.mid_level_mean
            if mu <= 0:
                mu = 100.0

            start = cal.mid_level_first if cal.mid_level_first > 0 else mu

            mids = np.empty(n_ts, dtype=np.float64)
            mids[0] = start
            if sigma <= 0:
                # Zero-vol degeneracy: deterministic reversion to mu.
                for i in range(1, n_ts):
                    mids[i] = phi * mids[i - 1] + (1 - phi) * mu
            else:
                noise = rng.normal(loc=0.0, scale=sigma, size=n_ts - 1)
                for i in range(1, n_ts):
                    mids[i] = phi * mids[i - 1] + (1 - phi) * mu + noise[i - 1]

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
