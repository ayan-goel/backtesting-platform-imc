"""Inventory statistics — max/avg absolute position, turnover."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InventoryStats:
    max_abs_position: int
    avg_abs_position: float
    turnover: int  # total absolute quantity traded


def inventory_stats(position_history: list[int], fill_quantities: list[int]) -> InventoryStats:
    """Compute stats from a time-ordered position history and the fill quantities."""
    if not position_history:
        return InventoryStats(max_abs_position=0, avg_abs_position=0.0, turnover=0)
    abs_positions = [abs(p) for p in position_history]
    return InventoryStats(
        max_abs_position=max(abs_positions),
        avg_abs_position=sum(abs_positions) / len(abs_positions),
        turnover=sum(abs(q) for q in fill_quantities),
    )
