"""Engine-local defaults. No environment I/O — env config lives in prosperity.api.settings."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_POSITION_LIMIT: int = 50
"""Default per-product position limit. Overridden per-product via RunConfig in T8."""

DEFAULT_MATCHER: str = "depth_only"


@dataclass(frozen=True, slots=True)
class EngineDefaults:
    position_limit: int = DEFAULT_POSITION_LIMIT
    matcher_name: str = DEFAULT_MATCHER
