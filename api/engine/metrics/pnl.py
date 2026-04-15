"""PnL calculators. Pure functions over a SimState."""

from __future__ import annotations

from dataclasses import dataclass

from engine.simulator.state import SimState


@dataclass(frozen=True, slots=True)
class PnlSnapshot:
    cash: float
    realized_by_product: dict[str, float]
    mark: float
    total: float

    @property
    def realized(self) -> float:
        return sum(self.realized_by_product.values())


def realized_and_mark(state: SimState, mid_prices: dict[str, float]) -> PnlSnapshot:
    """Return a snapshot of realized + mark-to-market PnL at this moment.

    Total = cash + value of open positions at mid. Realized is already absorbed into cash
    (since we subtract fill cost on every fill), so we don't add it twice.
    """
    return PnlSnapshot(
        cash=state.cash,
        realized_by_product=dict(state.realized_pnl_by_product),
        mark=state.mark_to_market(mid_prices),
        total=state.cash + _portfolio_value(state, mid_prices),
    )


def _portfolio_value(state: SimState, mid_prices: dict[str, float]) -> float:
    """Sum `position * mid_price` across open positions."""
    return sum(
        pos * mid_prices.get(symbol, state.vwap_cost.get(symbol, 0.0))
        for symbol, pos in state.positions.items()
        if pos != 0
    )
