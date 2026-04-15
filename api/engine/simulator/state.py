"""Mutable simulator state: cash, positions, mark-to-market.

Kept deliberately small — the runner in T8 owns the loop, this module just encapsulates
the "apply a fill, update cash and position" operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.datamodel.types import Fill


@dataclass(slots=True)
class SimState:
    cash: float = 0.0
    positions: dict[str, int] = field(default_factory=dict)
    realized_pnl_by_product: dict[str, float] = field(default_factory=dict)
    # Volume-weighted average cost (per product), used to compute realized PnL on close.
    vwap_cost: dict[str, float] = field(default_factory=dict)

    def apply_fill(self, fill: Fill) -> None:
        """Update cash and position for one fill. Realized PnL is computed on position close."""
        symbol = fill.symbol
        qty = fill.quantity  # positive=buy, negative=sell
        price = fill.price

        current_pos = self.positions.get(symbol, 0)
        new_pos = current_pos + qty
        # Cash flow: buying costs us price*qty; selling credits price*|qty|
        self.cash -= price * qty

        prev_cost = self.vwap_cost.get(symbol, 0.0)
        realized = self.realized_pnl_by_product.setdefault(symbol, 0.0)

        if current_pos == 0 or _same_sign(current_pos, qty):
            # Opening or extending position — update VWAP cost.
            total_cost = prev_cost * abs(current_pos) + price * abs(qty)
            new_abs_pos = abs(new_pos)
            self.vwap_cost[symbol] = total_cost / new_abs_pos if new_abs_pos > 0 else 0.0
        else:
            # Reducing or flipping — realize PnL on the closed portion.
            closed_qty = min(abs(current_pos), abs(qty))
            direction = 1 if current_pos > 0 else -1
            realized_delta = (price - prev_cost) * closed_qty * direction
            self.realized_pnl_by_product[symbol] = realized + realized_delta
            if abs(qty) > abs(current_pos):
                # Flipped through zero — new side has leftover at the fill price.
                self.vwap_cost[symbol] = price
            elif new_pos == 0:
                self.vwap_cost[symbol] = 0.0
            # else: partial reduce — VWAP stays.

        self.positions[symbol] = new_pos

    def mark_to_market(self, mid_prices: dict[str, float]) -> float:
        """Return unrealized PnL across all non-zero positions for a given mid-price map."""
        unreal = 0.0
        for symbol, pos in self.positions.items():
            if pos == 0:
                continue
            mid = mid_prices.get(symbol)
            if mid is None:
                continue
            cost = self.vwap_cost.get(symbol, 0.0)
            unreal += (mid - cost) * pos
        return unreal


def _same_sign(a: int, b: int) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)
