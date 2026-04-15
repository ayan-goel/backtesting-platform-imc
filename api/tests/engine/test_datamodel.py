"""T2 tests: frozen engine types + round-trip adapters against the bundled shim."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from engine.datamodel import (
    ConversionObservation,
    Listing,
    Observation,
    Order,
    OrderDepth,
    Trade,
    TradingState,
    adapters,
)


def test_order_is_frozen() -> None:
    o = Order(symbol="KELP", price=100, quantity=5)
    with pytest.raises((AttributeError, TypeError)):
        o.price = 101  # type: ignore[misc]


def test_order_depth_best_bid_ask_and_mid() -> None:
    depth = OrderDepth(
        buy_orders=MappingProxyType({9999: 10, 9998: 5}),
        sell_orders=MappingProxyType({10001: -12, 10002: -8}),
    )
    assert depth.best_bid() == (9999, 10)
    assert depth.best_ask() == (10001, -12)
    assert depth.mid_price() == 10000.0


def test_order_depth_empty_sides() -> None:
    depth = OrderDepth()
    assert depth.best_bid() is None
    assert depth.best_ask() is None
    assert depth.mid_price() is None


def test_trading_state_round_trip_to_strategy_facing() -> None:
    depth = OrderDepth(
        buy_orders=MappingProxyType({9999: 10}),
        sell_orders=MappingProxyType({10001: -12}),
    )
    state = TradingState(
        trader_data="",
        timestamp=0,
        listings={"KELP": Listing("KELP", "KELP", "SEASHELLS")},
        order_depths={"KELP": depth},
        own_trades={"KELP": ()},
        market_trades={"KELP": (Trade(symbol="KELP", price=10000, quantity=1, timestamp=0),)},
        position={"KELP": 0},
        observations=Observation(),
    )

    dm_state = adapters.to_strategy_state(state)

    assert dm_state.traderData == ""
    assert dm_state.timestamp == 0
    assert dm_state.listings["KELP"].symbol == "KELP"
    assert dm_state.order_depths["KELP"].buy_orders == {9999: 10}
    assert dm_state.order_depths["KELP"].sell_orders == {10001: -12}
    assert len(dm_state.market_trades["KELP"]) == 1
    assert dm_state.market_trades["KELP"][0].price == 10000
    assert dm_state.position == {"KELP": 0}


def test_from_strategy_orders_coerces_types() -> None:
    # strategy_loader injects engine/compat onto sys.path so user strategies
    # import from the bundled shim. Emulate that here.
    import sys as _sys

    from engine.compat import COMPAT_DIR

    if str(COMPAT_DIR) not in _sys.path:
        _sys.path.insert(0, str(COMPAT_DIR))
    import datamodel as dm

    raw = {
        "KELP": [
            dm.Order("KELP", 10000, -5),
            dm.Order("KELP", 9998, 5),
        ]
    }
    engine_orders = adapters.from_strategy_orders(raw)
    assert set(engine_orders) == {"KELP"}
    assert len(engine_orders["KELP"]) == 2
    assert engine_orders["KELP"][0] == Order(symbol="KELP", price=10000, quantity=-5)
    assert engine_orders["KELP"][1] == Order(symbol="KELP", price=9998, quantity=5)


def test_conversion_observation_roundtrips_despite_buggy_init() -> None:
    """Root datamodel.ConversionObservation.__init__ is broken; adapter bypasses it."""
    state = TradingState(
        trader_data="",
        timestamp=0,
        listings={},
        order_depths={},
        own_trades={},
        market_trades={},
        position={},
        observations=Observation(
            conversion=MappingProxyType(
                {
                    "ORCHIDS": ConversionObservation(
                        bid_price=100.0,
                        ask_price=101.0,
                        transport_fees=0.5,
                        export_tariff=1.0,
                        import_tariff=0.25,
                        sugar_price=50.0,
                        sunlight_index=7.5,
                    )
                }
            ),
        ),
    )
    dm_state = adapters.to_strategy_state(state)
    co = dm_state.observations.conversionObservations["ORCHIDS"]
    assert co.bidPrice == 100.0
    assert co.askPrice == 101.0
    assert co.sugarPrice == 50.0
    assert co.sunlightIndex == 7.5
