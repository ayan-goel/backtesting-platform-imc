"""IMC-parity matcher — direct port of `prosperity4btx/runner.py` match_order.

Targets binary parity with `prosperity4btx` (xeeshan85/imc-prosperity-4-backtester,
PyPI v1.0.2), which is itself a port of jmerle's prosperity3bt with P4 updates.

Algorithm per order:
    1. Walk the opposing side of the book in price priority, fill at book price.
    2. If residual > 0 and mode != NONE, iterate market_trades at this ts and
       fill residual at ORDER price (not trade price — see README example:
       "if you place a sell order for 9 and there is a market trade for 10,
        the sell order is matched at 9").
    3. `WORSE` mode skips market trades whose price equals the order's price.

MarketTrade pool semantics (from prosperity4btx/models.py):
    Each print has independent buy_remaining / sell_remaining counters. Our
    buy orders consume sell_remaining (we take the counterparty's sell side);
    our sell orders consume buy_remaining. Pool is rebuilt fresh per ts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from engine.datamodel.types import Fill, Order, OrderDepth, Trade
from engine.errors import MatcherError


class TradeMatchingMode(str, Enum):
    ALL = "all"
    WORSE = "worse"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ImcMatcher:
    mode: TradeMatchingMode = TradeMatchingMode.ALL
    name: str = "imc"

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
            pool = _build_pool(market_trades, symbol) if market_trades else []
            for order in orders:
                if order.quantity == 0:
                    continue
                if order.quantity > 0:
                    _match_buy(book, pool, order, ts, symbol, self.mode, fills)
                else:
                    _match_sell(book, pool, order, ts, symbol, self.mode, fills)
        return fills


class _BookState:
    """Mutable per-ts copy of an OrderDepth. Ask volumes are normalized to positive."""

    __slots__ = ("buys", "sells")

    def __init__(self, depth: OrderDepth) -> None:
        self.buys: dict[int, int] = dict(depth.buy_orders)
        self.sells: dict[int, int] = {p: abs(v) for p, v in depth.sell_orders.items()}


class _PoolEntry:
    """Mutable MarketTrade analogue — independent buy/sell remaining counters."""

    __slots__ = ("price", "buy_remaining", "sell_remaining")

    def __init__(self, price: int, quantity: int) -> None:
        self.price = price
        q = abs(quantity)
        self.buy_remaining = q
        self.sell_remaining = q


def _build_pool(
    market_trades: Mapping[str, Sequence[Trade]], symbol: str
) -> list[_PoolEntry]:
    trades = market_trades.get(symbol, ())
    return [_PoolEntry(t.price, t.quantity) for t in trades if t.quantity != 0]


def _match_buy(
    book: _BookState,
    pool: list[_PoolEntry],
    order: Order,
    ts: int,
    symbol: str,
    mode: TradeMatchingMode,
    fills: list[Fill],
) -> None:
    remaining = order.quantity
    # Snapshot sorted marketable asks, then walk them. We mutate book.sells
    # during the walk; .get() protects against prices already consumed.
    price_matches = sorted(p for p in book.sells if p <= order.price)
    for ask_price in price_matches:
        if remaining == 0:
            return
        available = book.sells.get(ask_price, 0)
        if available == 0:
            continue
        take = min(remaining, available)
        fills.append(
            Fill(symbol=symbol, price=ask_price, quantity=take, source="book", timestamp=ts)
        )
        remaining -= take
        leftover = available - take
        if leftover == 0:
            del book.sells[ask_price]
        else:
            book.sells[ask_price] = leftover

    if remaining == 0 or mode == TradeMatchingMode.NONE:
        return

    # Residual against market trades, at ORDER price.
    for entry in pool:
        if remaining == 0:
            return
        if entry.sell_remaining == 0:
            continue
        if entry.price > order.price:
            continue
        if entry.price == order.price and mode == TradeMatchingMode.WORSE:
            continue
        take = min(remaining, entry.sell_remaining)
        fills.append(
            Fill(symbol=symbol, price=order.price, quantity=take, source="trade", timestamp=ts)
        )
        remaining -= take
        entry.sell_remaining -= take


def _match_sell(
    book: _BookState,
    pool: list[_PoolEntry],
    order: Order,
    ts: int,
    symbol: str,
    mode: TradeMatchingMode,
    fills: list[Fill],
) -> None:
    need = -order.quantity  # positive working quantity
    price_matches = sorted((p for p in book.buys if p >= order.price), reverse=True)
    for bid_price in price_matches:
        if need == 0:
            return
        available = book.buys.get(bid_price, 0)
        if available == 0:
            continue
        take = min(need, available)
        fills.append(
            Fill(symbol=symbol, price=bid_price, quantity=-take, source="book", timestamp=ts)
        )
        need -= take
        leftover = available - take
        if leftover == 0:
            del book.buys[bid_price]
        else:
            book.buys[bid_price] = leftover

    if need == 0 or mode == TradeMatchingMode.NONE:
        return

    for entry in pool:
        if need == 0:
            return
        if entry.buy_remaining == 0:
            continue
        if entry.price < order.price:
            continue
        if entry.price == order.price and mode == TradeMatchingMode.WORSE:
            continue
        take = min(need, entry.buy_remaining)
        fills.append(
            Fill(symbol=symbol, price=order.price, quantity=-take, source="trade", timestamp=ts)
        )
        need -= take
        entry.buy_remaining -= take
