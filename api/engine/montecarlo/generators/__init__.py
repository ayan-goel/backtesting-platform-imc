"""Generator registry.

A generator is a callable of the form::

    generate(
        historical: MarketData,
        calibration: Calibration | None,
        params: Mapping[str, Any],
        rng: np.random.Generator,
    ) -> MarketData

All generators are dispatched from `resolve_generator(spec)` keyed on
`spec["type"]`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import numpy as np

from engine.market.loader import MarketData
from engine.montecarlo.generators.identity import IdentityGenerator


class Generator(Protocol):
    name: str

    def generate(
        self,
        *,
        historical: MarketData,
        calibration: Any | None,
        params: Mapping[str, Any],
        rng: np.random.Generator,
    ) -> MarketData: ...


def resolve_generator(spec: Mapping[str, Any]) -> Generator:
    """Pick a generator from a spec dict. Spec must include a `type` key."""
    gen_type = spec.get("type")
    if gen_type is None:
        raise ValueError("generator spec missing 'type'")
    if gen_type == "identity":
        return IdentityGenerator()
    if gen_type == "block_bootstrap":
        from engine.montecarlo.generators.block_bootstrap import BlockBootstrapGenerator

        return BlockBootstrapGenerator()
    if gen_type == "gbm":
        from engine.montecarlo.generators.gbm import GbmGenerator

        return GbmGenerator()
    if gen_type == "ou":
        from engine.montecarlo.generators.ou import OuGenerator

        return OuGenerator()
    raise ValueError(f"unknown generator type: {gen_type!r}")


__all__ = ["Generator", "IdentityGenerator", "resolve_generator"]
