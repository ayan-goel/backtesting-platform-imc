"""Depth-only matcher: match our orders against the L2 book, price-priority, no market-trade matching."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from engine.datamodel.types import Fill, Order, OrderDepth, Trade
from engine.errors import MatcherError


@dataclass(frozen=True, slots=True)
class DepthOnlyMatcher:
    """Walks the opposing side of the book in price priority, emits fills until no cross."""

    name: ClassVar[str] = "depth_only"

    def match(
        self,
        *,
        ts: int,
        order_depths: dict[str, OrderDepth],
        orders_by_symbol: dict[str, tuple[Order, ...]],
        market_trades: Mapping[str, Sequence[Trade]] | None = None,
    ) -> list[Fill]:
        _ = market_trades  # depth_only ignores market trades intentionally
        fills: list[Fill] = []
        for symbol, orders in orders_by_symbol.items():
            if symbol not in order_depths:
                raise MatcherError(f"no order depth for symbol {symbol!r} at ts={ts}")
            # Mutable copies of the book for this matching pass — we consume liquidity
            # in order, not in parallel.
            book = _BookState(order_depths[symbol])
            for order in orders:
                if order.quantity == 0:
                    continue
                fills.extend(_match_one(book, order, ts, symbol))
        return fills


class _BookState:
    """Mutable per-pass copy of an OrderDepth. Only used inside one matcher call."""

    __slots__ = ("buys", "sells")

    def __init__(self, depth: OrderDepth) -> None:
        self.buys: dict[int, int] = dict(depth.buy_orders)
        self.sells: dict[int, int] = dict(depth.sell_orders)


def _match_one(book: _BookState, order: Order, ts: int, symbol: str) -> list[Fill]:
    fills: list[Fill] = []
    remaining = order.quantity
    if remaining > 0:
        # Buy order — consume sells from lowest ask upward while ask <= our price.
        while remaining > 0 and book.sells:
            best_ask = min(book.sells)
            if best_ask > order.price:
                break
            available = -book.sells[best_ask]  # sells are stored negative
            take = min(remaining, available)
            fills.append(Fill(symbol=symbol, price=best_ask, quantity=take, source="book", timestamp=ts))
            remaining -= take
            leftover = available - take
            if leftover == 0:
                del book.sells[best_ask]
            else:
                book.sells[best_ask] = -leftover
    else:
        # Sell order — consume buys from highest bid downward while bid >= our price.
        need = -remaining
        while need > 0 and book.buys:
            best_bid = max(book.buys)
            if best_bid < order.price:
                break
            available = book.buys[best_bid]
            take = min(need, available)
            fills.append(
                Fill(symbol=symbol, price=best_bid, quantity=-take, source="book", timestamp=ts)
            )
            need -= take
            leftover = available - take
            if leftover == 0:
                del book.buys[best_bid]
            else:
                book.buys[best_bid] = leftover
    return fills
