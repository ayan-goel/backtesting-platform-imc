"""M2 tests: DepthAndTradesMatcher — book-first with market-trade fallback."""

from __future__ import annotations

from engine.datamodel.types import Order, OrderDepth, Trade
from engine.matching.depth_and_trades import DepthAndTradesMatcher


def _depth(buys: dict[int, int], sells: dict[int, int]) -> OrderDepth:
    return OrderDepth(buy_orders=buys, sell_orders=sells)


def _trade(price: int, qty: int, symbol: str = "KELP") -> Trade:
    return Trade(symbol=symbol, price=price, quantity=qty, timestamp=1)


class TestDepthAndTradesMatcher:
    def setup_method(self) -> None:
        self.m = DepthAndTradesMatcher()

    def test_fallback_to_trades_when_book_empty(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {"KELP": (Order("KELP", 100, 5),)}
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert len(fills) == 1
        assert fills[0].price == 100
        assert fills[0].quantity == 5
        assert fills[0].source == "trade"

    def test_book_is_preferred_before_trades(self) -> None:
        depths = {"KELP": _depth({}, {100: -5})}
        orders = {"KELP": (Order("KELP", 100, 5),)}
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert len(fills) == 1
        assert fills[0].source == "book"

    def test_residual_hits_trades(self) -> None:
        depths = {"KELP": _depth({}, {100: -5})}
        orders = {"KELP": (Order("KELP", 100, 15),)}
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert len(fills) == 2
        assert fills[0].source == "book"
        assert fills[0].quantity == 5
        assert fills[1].source == "trade"
        assert fills[1].quantity == 10

    def test_not_marketable_no_fill(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {"KELP": (Order("KELP", 98, 5),)}
        mt = {"KELP": (_trade(99, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert fills == []

    def test_multiple_our_orders_share_pool(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {
            "KELP": (
                Order("KELP", 100, 10),
                Order("KELP", 100, 10),
            )
        }
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        # First order consumes the whole pool, second gets nothing.
        assert len(fills) == 1
        assert fills[0].quantity == 10

    def test_sell_side_fallback(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {"KELP": (Order("KELP", 100, -5),)}
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert len(fills) == 1
        assert fills[0].source == "trade"
        assert fills[0].quantity == -5
        assert fills[0].price == 100

    def test_trade_quantity_sign_ignored(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {"KELP": (Order("KELP", 100, 5),)}
        # Negative-quantity prints should still be usable — abs() pool.
        mt = {"KELP": (_trade(100, -10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert len(fills) == 1
        assert fills[0].quantity == 5

    def test_partial_fill_across_multiple_trades(self) -> None:
        depths = {"KELP": _depth({}, {})}
        orders = {"KELP": (Order("KELP", 100, 8),)}
        mt = {"KELP": (_trade(100, 5), _trade(100, 5))}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        assert [f.quantity for f in fills] == [5, 3]

    def test_zero_residual_no_trade_pass(self) -> None:
        """A fully-filled first order must not consume the trade pool; a second
        order should still be able to take the whole pool."""
        depths = {"KELP": _depth({}, {100: -5})}
        orders = {
            "KELP": (
                Order("KELP", 100, 5),  # fully filled from the book
                Order("KELP", 100, 10),  # should see full pool
            )
        }
        mt = {"KELP": (_trade(100, 10),)}
        fills = self.m.match(
            ts=1, order_depths=depths, orders_by_symbol=orders, market_trades=mt
        )
        sources = [f.source for f in fills]
        assert sources == ["book", "trade"]
        assert fills[1].quantity == 10

    def test_no_market_trades_defaults_to_depth_only_behavior(self) -> None:
        depths = {"KELP": _depth({}, {100: -5})}
        orders = {"KELP": (Order("KELP", 100, 10),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert len(fills) == 1
        assert fills[0].source == "book"
        assert fills[0].quantity == 5
