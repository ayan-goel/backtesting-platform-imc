"""Engine-internal trading types — frozen, slotted, hashable.

These are what the simulator operates on. Strategies import the root `datamodel.py`
types; `engine.datamodel.adapters` converts between the two at the simulator boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Listing:
    symbol: str
    product: str
    denomination: str


@dataclass(frozen=True, slots=True)
class Order:
    symbol: str
    price: int
    quantity: int  # positive=buy, negative=sell


@dataclass(frozen=True, slots=True)
class OrderDepth:
    """Read-only L2 book snapshot for a single product.

    buy_orders: price -> positive volume, highest price = best bid
    sell_orders: price -> negative volume, lowest price = best ask
    """

    buy_orders: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    sell_orders: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))

    def best_bid(self) -> tuple[int, int] | None:
        if not self.buy_orders:
            return None
        price = max(self.buy_orders)
        return price, self.buy_orders[price]

    def best_ask(self) -> tuple[int, int] | None:
        if not self.sell_orders:
            return None
        price = min(self.sell_orders)
        return price, self.sell_orders[price]

    def mid_price(self) -> float | None:
        b = self.best_bid()
        a = self.best_ask()
        if b is None or a is None:
            return None
        return (b[0] + a[0]) / 2


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    price: int
    quantity: int
    buyer: str | None = None
    seller: str | None = None
    timestamp: int = 0


@dataclass(frozen=True, slots=True)
class ConversionObservation:
    bid_price: float
    ask_price: float
    transport_fees: float
    export_tariff: float
    import_tariff: float
    sugar_price: float = 0.0
    sunlight_index: float = 0.0


@dataclass(frozen=True, slots=True)
class Observation:
    plain: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    conversion: Mapping[str, ConversionObservation] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True, slots=True)
class TradingState:
    trader_data: str
    timestamp: int
    listings: Mapping[str, Listing]
    order_depths: Mapping[str, OrderDepth]
    own_trades: Mapping[str, tuple[Trade, ...]]
    market_trades: Mapping[str, tuple[Trade, ...]]
    position: Mapping[str, int]
    observations: Observation


@dataclass(frozen=True, slots=True)
class Fill:
    """Result of matching one of our orders against the book or market trades."""

    symbol: str
    price: int
    quantity: int  # signed — positive=we bought, negative=we sold
    source: str  # "book" | "trade"
    timestamp: int
