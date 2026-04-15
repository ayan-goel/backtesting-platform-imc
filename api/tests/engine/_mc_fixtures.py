"""Synthetic MarketData fixtures for Monte Carlo engine tests.

Tutorial CSVs are not available in this checkout, so tests synthesize a
deterministic in-memory `MarketData` that is small but realistic enough to
exercise matcher/runner/MC plumbing end-to-end.
"""

from __future__ import annotations

import math

from engine.datamodel.types import OrderDepth, Trade
from engine.market.loader import MarketData, ProductSnap


def make_synthetic_market_data(
    *,
    round_num: int = 0,
    day: int = 0,
    num_timestamps: int = 120,
    products: tuple[str, ...] = ("KELP", "RESIN"),
    seed: int = 0,
) -> MarketData:
    """Build a small but realistic MarketData with mean-reverting mid prices.

    Each ts carries a 3-level book and one market trade per product. Prices
    are deterministic functions of (seed, ts, product_index) so fixtures
    are byte-stable across runs and platforms.
    """
    base_prices = {"KELP": 10_000, "RESIN": 5_000}
    frames: dict[int, dict[str, ProductSnap]] = {}
    timestamps = tuple(i * 100 for i in range(num_timestamps))

    for i, ts in enumerate(timestamps):
        for p_idx, product in enumerate(products):
            base = base_prices.get(product, 1_000 + p_idx * 500)
            # Smooth oscillation + small "noise" from (seed, i, p_idx).
            osc = round(10 * math.sin(0.05 * i + p_idx))
            noise = ((seed * 131 + i * 17 + p_idx * 7) % 5) - 2
            mid = base + osc + noise

            spread = 2
            bid1 = mid - spread
            ask1 = mid + spread
            buy_orders = {
                bid1: 20,
                bid1 - 1: 15,
                bid1 - 2: 10,
            }
            sell_orders = {
                ask1: -20,
                ask1 + 1: -15,
                ask1 + 2: -10,
            }
            depth = OrderDepth(buy_orders=buy_orders, sell_orders=sell_orders)
            trades = (
                Trade(
                    symbol=product,
                    price=mid,
                    quantity=3,
                    buyer=None,
                    seller=None,
                    timestamp=ts,
                ),
            )
            snap = ProductSnap(
                order_depth=depth,
                market_trades=trades,
                mid_price=float(mid),
            )
            frames.setdefault(ts, {})[product] = snap

    return MarketData(
        round=round_num,
        day=day,
        timestamps=timestamps,
        products=products,
        frames=frames,
    )


GREEDY_TRADER_SRC = b"""
from datamodel import Order


class Trader:
    def run(self, state):
        orders = {}
        for product, depth in state.order_depths.items():
            asks = sorted(depth.sell_orders.items())
            if asks:
                price, _ = asks[0]
                orders[product] = [Order(product, price, 3)]
            else:
                orders[product] = []
        return orders, 0, ""
"""


NOOP_TRADER_SRC = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""
