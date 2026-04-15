"""High-level entry point to turn a (historical, generator, rng) tuple into
a synthetic `MarketData` instance.

Kept deliberately thin — this module owns no statistical logic of its own,
it's just the place where the MC runner asks "give me a synthetic market
for path N" without knowing which generator is in use.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from engine.market.loader import MarketData
from engine.montecarlo.generators import Generator


def build_synthetic_market_data(
    *,
    historical: MarketData,
    generator: Generator,
    calibration: Any | None,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> MarketData:
    """Delegate to the generator and validate the output shape.

    Enforces that the returned `MarketData` has the same (round, day,
    timestamps, products) spine as the historical data. Generators are
    free to mutate per-frame content but must not change the tick grid —
    downstream code (position-limit enforcement, summary building)
    assumes a stable product set.
    """
    synthetic = generator.generate(
        historical=historical, calibration=calibration, params=params, rng=rng
    )
    _validate_spine(historical=historical, synthetic=synthetic)
    return synthetic


def _validate_spine(*, historical: MarketData, synthetic: MarketData) -> None:
    if synthetic.round != historical.round or synthetic.day != historical.day:
        raise ValueError(
            "generator changed round/day — "
            f"historical=({historical.round}, {historical.day}) "
            f"synthetic=({synthetic.round}, {synthetic.day})"
        )
    if synthetic.timestamps != historical.timestamps:
        raise ValueError("generator changed the timestamp grid")
    if synthetic.products != historical.products:
        raise ValueError(
            f"generator changed products: {synthetic.products} vs {historical.products}"
        )
