"""Monte Carlo simulation subsystem.

Generates synthetic-but-statistically-plausible `MarketData` objects so an
existing strategy can be evaluated under many realizations of the market.

The critical invariant of this module: every generator returns a fully-formed
`MarketData` instance that is a drop-in replacement for one produced by
`engine.market.loader.load_round_day`. The production simulator
(`engine.simulator.runner.simulate_day`) is reused unchanged — MC never
forks the matcher, fill logic, position-limit enforcement, or PnL accounting.
"""

from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.generators import IdentityGenerator, resolve_generator
from engine.montecarlo.rng import rng_for_path

__all__ = [
    "IdentityGenerator",
    "build_synthetic_market_data",
    "resolve_generator",
    "rng_for_path",
]
