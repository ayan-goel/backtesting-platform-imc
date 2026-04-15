"""Build an engine TradingState from MarketData at a given timestamp."""

from __future__ import annotations

from collections.abc import Mapping

from engine.datamodel.types import (
    Listing,
    Observation,
    OrderDepth,
    Trade,
    TradingState,
)
from engine.market.loader import MarketData

DEFAULT_DENOMINATION = "SEASHELLS"


def build_trading_state(
    market_data: MarketData,
    ts: int,
    *,
    positions: Mapping[str, int],
    own_trades_last_ts: Mapping[str, tuple[Trade, ...]],
    trader_data: str,
) -> TradingState:
    """Assemble an engine-internal TradingState for timestamp `ts`."""
    frame = market_data.snap_at(ts)

    listings: dict[str, Listing] = {}
    order_depths: dict[str, OrderDepth] = {}
    market_trades: dict[str, tuple[Trade, ...]] = {}
    position_view: dict[str, int] = {}

    for product, snap in frame.items():
        listings[product] = Listing(
            symbol=product, product=product, denomination=DEFAULT_DENOMINATION
        )
        order_depths[product] = snap.order_depth
        market_trades[product] = snap.market_trades
        position_view[product] = positions.get(product, 0)

    own_trades_view: dict[str, tuple[Trade, ...]] = {
        product: own_trades_last_ts.get(product, ()) for product in frame
    }

    return TradingState(
        trader_data=trader_data,
        timestamp=ts,
        listings=listings,
        order_depths=order_depths,
        own_trades=own_trades_view,
        market_trades=market_trades,
        position=position_view,
        observations=Observation(),
    )
