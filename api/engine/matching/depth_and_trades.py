"""Depth + market-trade fallback matcher.

Pass 1 walks the L2 book in price priority exactly like depth_only. For any
remaining quantity, pass 2 fills residual against market prints at the same
timestamp: each trade is treated as a consumable pool (abs(quantity)), and
our orders consume from it in submission order if our limit is marketable
against the print price.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from engine.datamodel.types import Fill, Order, OrderDepth, Trade
from engine.errors import MatcherError


@dataclass(frozen=True, slots=True)
class DepthAndTradesMatcher:
    """Book-first matcher that falls back to market-trade prints for residual size."""

    name: str = "depth_and_trades"

    def match(
        self,
        *,
        ts: int,
        order_depths: dict[str, OrderDepth],
        orders_by_symbol: dict[str, tuple[Order, ...]],
        market_trades: Mapping[str, Sequence[Trade]] | None = None,
    ) -> list[Fill]:
        fills: list[Fill] = []
        for symbol, orders in orders_by_symbol.items():
            if symbol not in order_depths:
                raise MatcherError(f"no order depth for symbol {symbol!r} at ts={ts}")
            book = _BookState(order_depths[symbol])
            # One pool per market print at this ts, consumable across all of
            # our orders at this ts.
            trade_pool = _build_trade_pool(market_trades, symbol) if market_trades else []

            for order in orders:
                if order.quantity == 0:
                    continue
                remaining = _match_against_book(book, order, ts, symbol, fills)
                if remaining == 0:
                    continue
                _match_against_trades(trade_pool, order, ts, symbol, remaining, fills)
        return fills


class _BookState:
    __slots__ = ("buys", "sells")

    def __init__(self, depth: OrderDepth) -> None:
        self.buys: dict[int, int] = dict(depth.buy_orders)
        self.sells: dict[int, int] = dict(depth.sell_orders)


class _TradePoolEntry:
    __slots__ = ("price", "remaining")

    def __init__(self, price: int, remaining: int) -> None:
        self.price = price
        self.remaining = remaining


def _build_trade_pool(
    market_trades: Mapping[str, Sequence[Trade]], symbol: str
) -> list[_TradePoolEntry]:
    trades = market_trades.get(symbol, ())
    return [_TradePoolEntry(price=t.price, remaining=abs(t.quantity)) for t in trades if t.quantity != 0]


def _match_against_book(
    book: _BookState, order: Order, ts: int, symbol: str, fills: list[Fill]
) -> int:
    """Walk the book like depth_only. Returns remaining signed quantity."""
    remaining = order.quantity
    if remaining > 0:
        while remaining > 0 and book.sells:
            best_ask = min(book.sells)
            if best_ask > order.price:
                break
            available = -book.sells[best_ask]
            take = min(remaining, available)
            fills.append(
                Fill(symbol=symbol, price=best_ask, quantity=take, source="book", timestamp=ts)
            )
            remaining -= take
            leftover = available - take
            if leftover == 0:
                del book.sells[best_ask]
            else:
                book.sells[best_ask] = -leftover
    elif remaining < 0:
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
        remaining = -need
    return remaining


def _match_against_trades(
    trade_pool: list[_TradePoolEntry],
    order: Order,
    ts: int,
    symbol: str,
    residual: int,
    fills: list[Fill],
) -> None:
    """Fill `residual` against `trade_pool`, marketability-checked, first-come-first-served."""
    if residual > 0:
        # Buy residual — consume any print at price <= order.price.
        for entry in trade_pool:
            if residual == 0:
                break
            if entry.remaining == 0:
                continue
            if entry.price > order.price:
                continue
            take = min(residual, entry.remaining)
            fills.append(
                Fill(symbol=symbol, price=entry.price, quantity=take, source="trade", timestamp=ts)
            )
            entry.remaining -= take
            residual -= take
    elif residual < 0:
        need = -residual
        for entry in trade_pool:
            if need == 0:
                break
            if entry.remaining == 0:
                continue
            if entry.price < order.price:
                continue
            take = min(need, entry.remaining)
            fills.append(
                Fill(symbol=symbol, price=entry.price, quantity=-take, source="trade", timestamp=ts)
            )
            entry.remaining -= take
            need -= take
