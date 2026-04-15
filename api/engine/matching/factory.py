"""Single resolution point for matcher name → instance.

All four run paths (CLI run, CLI gridsearch, server run/batch/study) go through
this so there's no drift between them.
"""

from __future__ import annotations

from engine.errors import ProsperityError
from engine.matching.base import Matcher
from engine.matching.depth_and_trades import DepthAndTradesMatcher
from engine.matching.depth_only import DepthOnlyMatcher
from engine.matching.imc_matcher import ImcMatcher, TradeMatchingMode

DEFAULT_MATCHER = "imc"
DEFAULT_MODE = TradeMatchingMode.ALL


def resolve_matcher(name: str, mode: str | TradeMatchingMode | None = None) -> Matcher:
    """Return a matcher instance by name. `mode` only applies to ``imc``.

    Raises ProsperityError on an unknown name or mode.
    """
    if name == "imc":
        m = _coerce_mode(mode)
        return ImcMatcher(mode=m)
    if name == "depth_only":
        return DepthOnlyMatcher()
    if name == "depth_and_trades":
        return DepthAndTradesMatcher()
    raise ProsperityError(f"unknown matcher: {name}")


def _coerce_mode(mode: str | TradeMatchingMode | None) -> TradeMatchingMode:
    if mode is None:
        return DEFAULT_MODE
    if isinstance(mode, TradeMatchingMode):
        return mode
    try:
        return TradeMatchingMode(mode)
    except ValueError as e:
        valid = ", ".join(m.value for m in TradeMatchingMode)
        raise ProsperityError(
            f"unknown trade-matching mode: {mode!r}; expected one of {valid}"
        ) from e
