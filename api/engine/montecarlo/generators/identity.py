"""Identity generator — returns the historical MarketData unchanged.

The correctness anchor for the entire MC feature. Running an MC simulation
with `identity` MUST produce a PnL equal to a normal `/runs` backtest on
the same strategy/round/day. If this property ever regresses, the MC
plumbing is wrong.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from engine.market.loader import MarketData


@dataclass(frozen=True, slots=True)
class IdentityGenerator:
    name: str = "identity"

    def generate(
        self,
        *,
        historical: MarketData,
        calibration: Any | None = None,
        params: Mapping[str, Any] | None = None,
        rng: np.random.Generator | None = None,
    ) -> MarketData:
        return historical
