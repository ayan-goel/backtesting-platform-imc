"""Convert between engine types and the strategy-facing `datamodel` types.

User strategies import `from datamodel import ...`. The adapter builds instances of
those types using the bundled shim at `engine/compat/datamodel.py`, which is what
`strategy_loader` exposes to user code at runtime.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING, Any, cast

from engine.compat import COMPAT_DIR
from engine.datamodel import types as T

if TYPE_CHECKING:
    from types import ModuleType


def _root_datamodel() -> ModuleType:
    """Import the bundled `datamodel` shim, ensuring COMPAT_DIR is on sys.path."""
    compat_str = str(COMPAT_DIR)
    if compat_str not in sys.path:
        sys.path.insert(0, compat_str)
    return importlib.import_module("datamodel")


def to_strategy_state(state: T.TradingState) -> Any:
    """Convert an engine TradingState into a root datamodel.TradingState for a strategy."""
    dm = _root_datamodel()

    listings = {
        sym: dm.Listing(symbol=lst.symbol, product=lst.product, denomination=lst.denomination)
        for sym, lst in state.listings.items()
    }

    order_depths: dict[str, Any] = {}
    for sym, depth in state.order_depths.items():
        od = dm.OrderDepth()
        od.buy_orders = dict(depth.buy_orders)
        od.sell_orders = dict(depth.sell_orders)
        order_depths[sym] = od

    own_trades = {sym: [_to_dm_trade(dm, t) for t in trades] for sym, trades in state.own_trades.items()}
    market_trades = {
        sym: [_to_dm_trade(dm, t) for t in trades] for sym, trades in state.market_trades.items()
    }

    observation = dm.Observation(
        plainValueObservations=dict(state.observations.plain),
        conversionObservations={
            k: _make_conversion_observation(dm, v)
            for k, v in state.observations.conversion.items()
        },
    )

    return dm.TradingState(
        traderData=state.trader_data,
        timestamp=state.timestamp,
        listings=listings,
        order_depths=order_depths,
        own_trades=own_trades,
        market_trades=market_trades,
        position=dict(state.position),
        observations=observation,
    )


def _to_dm_trade(dm: ModuleType, trade: T.Trade) -> Any:
    return dm.Trade(
        symbol=trade.symbol,
        price=trade.price,
        quantity=trade.quantity,
        buyer=trade.buyer,
        seller=trade.seller,
        timestamp=trade.timestamp,
    )


def _make_conversion_observation(dm: ModuleType, v: T.ConversionObservation) -> Any:
    """Construct a root-datamodel ConversionObservation, bypassing its buggy __init__.

    The root datamodel.py version references undefined names (`sugarPrice`, `sunlightIndex`)
    inside __init__. We cannot edit it (strategy-team territory), so we allocate with
    `object.__new__` and set attributes directly. Strategies read these as regular fields.
    """
    obj = object.__new__(dm.ConversionObservation)
    obj.bidPrice = v.bid_price
    obj.askPrice = v.ask_price
    obj.transportFees = v.transport_fees
    obj.exportTariff = v.export_tariff
    obj.importTariff = v.import_tariff
    obj.sugarPrice = v.sugar_price
    obj.sunlightIndex = v.sunlight_index
    return obj


def from_strategy_orders(raw_orders_by_symbol: dict[str, list[Any]]) -> dict[str, tuple[T.Order, ...]]:
    """Convert the orders returned from `Trader.run` into engine Order tuples."""
    result: dict[str, tuple[T.Order, ...]] = {}
    for symbol, orders in raw_orders_by_symbol.items():
        coerced: list[T.Order] = []
        for o in orders:
            coerced.append(
                T.Order(
                    symbol=cast(str, o.symbol),
                    price=int(o.price),
                    quantity=int(o.quantity),
                )
            )
        result[symbol] = tuple(coerced)
    return result
