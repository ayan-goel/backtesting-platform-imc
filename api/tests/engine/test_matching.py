"""T4 tests: DepthOnlyMatcher + position limit clamp."""

from __future__ import annotations

import pytest

from engine.datamodel.types import Order, OrderDepth
from engine.errors import MatcherError
from engine.matching.depth_only import DepthOnlyMatcher
from engine.simulator.limits import apply_position_limits


def _depth(buys: dict[int, int], sells: dict[int, int]) -> OrderDepth:
    return OrderDepth(buy_orders=buys, sell_orders=sells)


class TestDepthOnlyMatcher:
    def setup_method(self) -> None:
        self.m = DepthOnlyMatcher()

    def test_full_fill_buy_single_level(self) -> None:
        depths = {"KELP": _depth({}, {10000: -5})}
        orders = {"KELP": (Order("KELP", 10000, 5),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert len(fills) == 1
        assert fills[0].price == 10000
        assert fills[0].quantity == 5
        assert fills[0].source == "book"

    def test_partial_fill_then_no_cross(self) -> None:
        depths = {"KELP": _depth({}, {10000: -5, 10001: -3})}
        orders = {"KELP": (Order("KELP", 10000, 10),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert len(fills) == 1
        assert fills[0].quantity == 5  # only level 1 was within price

    def test_multi_level_walk_buy(self) -> None:
        depths = {"KELP": _depth({}, {10000: -5, 10001: -3})}
        orders = {"KELP": (Order("KELP", 10001, 100),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert [f.price for f in fills] == [10000, 10001]
        assert [f.quantity for f in fills] == [5, 3]

    def test_full_fill_sell_single_level(self) -> None:
        depths = {"KELP": _depth({9999: 10}, {})}
        orders = {"KELP": (Order("KELP", 9999, -5),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert len(fills) == 1
        assert fills[0].price == 9999
        assert fills[0].quantity == -5

    def test_no_cross_no_fill(self) -> None:
        depths = {"KELP": _depth({9999: 10}, {10001: -10})}
        orders = {"KELP": (Order("KELP", 9999, 5), Order("KELP", 10001, -5))}
        # Wait — buy at 9999 doesn't cross 10001, sell at 10001 doesn't cross 9999
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert fills == []

    def test_missing_symbol_raises(self) -> None:
        with pytest.raises(MatcherError):
            self.m.match(
                ts=1,
                order_depths={},
                orders_by_symbol={"KELP": (Order("KELP", 10000, 5),)},
            )

    def test_matcher_does_not_mutate_input_depth(self) -> None:
        depth = _depth({}, {10000: -5})
        depths = {"KELP": depth}
        orders = {"KELP": (Order("KELP", 10000, 5),)}
        self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert dict(depth.sell_orders) == {10000: -5}, "matcher mutated caller's book"

    def test_zero_quantity_order_is_skipped(self) -> None:
        depths = {"KELP": _depth({}, {10000: -5})}
        orders = {"KELP": (Order("KELP", 10000, 0),)}
        fills = self.m.match(ts=1, order_depths=depths, orders_by_symbol=orders)
        assert fills == []


class TestPositionLimits:
    """IMC semantics (mirrored from prosperity4btx): all-or-nothing rejection.

    If the worst-case buy or sell total would breach the limit, every order for
    the product is dropped this tick. No partial clamp.
    """

    def test_buy_over_limit_drops_all(self) -> None:
        orders = (Order("KELP", 10000, 100),)
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == ()

    def test_sell_over_limit_drops_all(self) -> None:
        orders = (Order("KELP", 9999, -100),)
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == ()

    def test_buy_within_limit_passes_through(self) -> None:
        orders = (Order("KELP", 10000, 40),)
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == orders

    def test_at_limit_blocks_further_buys(self) -> None:
        orders = (Order("KELP", 10000, 5),)
        clamped = apply_position_limits(current_position=50, pending_orders=orders, limit=50)
        assert clamped == ()

    def test_at_limit_allows_sells(self) -> None:
        orders = (Order("KELP", 9999, -10),)
        clamped = apply_position_limits(current_position=50, pending_orders=orders, limit=50)
        assert clamped == orders

    def test_mixed_orders_within_limit_pass_through(self) -> None:
        orders = (Order("KELP", 10001, 20), Order("KELP", 9999, -20))
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == orders

    def test_collective_breach_drops_all(self) -> None:
        # Three buys totaling 90 with limit 50 — breach → all dropped, including
        # the first two which individually fit.
        orders = (
            Order("KELP", 10000, 30),
            Order("KELP", 10001, 30),
            Order("KELP", 10002, 30),
        )
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == ()

    def test_sells_not_counted_against_buy_limit(self) -> None:
        # A huge sell plus a tiny buy should not trip the buy-side check.
        orders = (Order("KELP", 10000, 10), Order("KELP", 9999, -40))
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == orders

    def test_zero_quantity_order_passes_through(self) -> None:
        # Zero-qty orders contribute 0 to totals and survive the limit check.
        # The matcher skips them downstream.
        orders = (Order("KELP", 10000, 0),)
        clamped = apply_position_limits(current_position=0, pending_orders=orders, limit=50)
        assert clamped == orders

    def test_negative_limit_raises(self) -> None:
        with pytest.raises(ValueError):
            apply_position_limits(current_position=0, pending_orders=(), limit=-1)
