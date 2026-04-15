"""Pre-match position limit enforcement.

IMC rule (mirrored from `prosperity4btx/runner.py` enforce_limits): if the worst-case
buy total OR the worst-case sell total would push position outside ±limit, **every**
order for that product is rejected this tick. There is no partial clamp. This matches
the real IMC server's behavior; strategies that accidentally over-submit must manage
their own caps before returning from `run()`.
"""

from __future__ import annotations

from engine.datamodel.types import Order


def apply_position_limits(
    *,
    current_position: int,
    pending_orders: tuple[Order, ...],
    limit: int,
) -> tuple[Order, ...]:
    """Return `pending_orders` unchanged, or `()` if they would breach ±limit.

    Rule: reject the whole batch when
        current_position + sum(buys)  > limit   OR
        current_position - sum(sells) < -limit
    """
    if limit < 0:
        raise ValueError(f"position limit must be non-negative; got {limit}")

    total_long = sum(o.quantity for o in pending_orders if o.quantity > 0)
    total_short = sum(-o.quantity for o in pending_orders if o.quantity < 0)

    if current_position + total_long > limit or current_position - total_short < -limit:
        return ()
    return pending_orders
