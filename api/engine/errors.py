"""Engine exception hierarchy. All engine errors inherit from ProsperityError."""

from __future__ import annotations


class ProsperityError(Exception):
    """Base class for all engine errors."""


class InvalidMarketDataError(ProsperityError):
    """Raised when market data files are malformed or fail schema validation."""


class StrategyLoadError(ProsperityError):
    """Raised when a strategy file cannot be loaded as a Trader."""


class SimulationError(ProsperityError):
    """Raised when the simulator cannot continue (e.g. position limit breach post-match)."""


class MatcherError(ProsperityError):
    """Raised when a matcher receives invalid input."""
