"""Matcher protocol. Implementations consume orders and produce fills."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar, Protocol

from engine.datamodel.types import Fill, Order, OrderDepth, Trade


class Matcher(Protocol):
    """A matcher produces fills from a set of our orders against the current book.

    Implementations are pure — no hidden state between calls. They receive the current
    book and our intended orders, and return the resulting fills.

    `market_trades` is the list of market prints at this timestamp keyed by symbol.
    Implementations that only walk the book (e.g. DepthOnlyMatcher) ignore it.
    """

    name: ClassVar[str]

    def match(
        self,
        *,
        ts: int,
        order_depths: dict[str, OrderDepth],
        orders_by_symbol: dict[str, tuple[Order, ...]],
        market_trades: Mapping[str, Sequence[Trade]] | None = None,
    ) -> list[Fill]: ...
