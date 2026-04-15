"""JSONL event logger — writes one record per (ts, product) per SPEC.md §6 schema.

Contract:
- One JSON object per line
- Schema-stable: run_id, ts, product, state, actions, fills, pnl, debug
- `state.order_depth.sell` values are negative ints
- NoOpLogger is the submission-safe mode (used when strategies run in the official environment)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path
from typing import Any, Protocol

from engine.datamodel.types import Fill, Order, OrderDepth, Trade


class EventLoggerProtocol(Protocol):
    def write(
        self,
        *,
        ts: int,
        product: str,
        order_depth: OrderDepth,
        position: int,
        market_trades: tuple[Trade, ...],
        orders: tuple[Order, ...],
        fills: list[Fill],
        pnl: dict[str, float],
        debug: dict[str, Any] | None = None,
    ) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Typed view of one log line — mostly for tests."""

    run_id: str
    ts: int
    product: str
    state: dict[str, Any]
    actions: dict[str, Any]
    fills: list[dict[str, Any]]
    pnl: dict[str, float]
    debug: dict[str, Any]


class EventLogger:
    """JSONL writer. Open on __init__, call `write` per event, call `close` when done."""

    def __init__(self, run_id: str, out_path: Path) -> None:
        self.run_id = run_id
        self.out_path = out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIOBase | None = out_path.open("w", encoding="utf-8")
        self._closed = False

    def write(
        self,
        *,
        ts: int,
        product: str,
        order_depth: OrderDepth,
        position: int,
        market_trades: tuple[Trade, ...],
        orders: tuple[Order, ...],
        fills: list[Fill],
        pnl: dict[str, float],
        debug: dict[str, Any] | None = None,
    ) -> None:
        if self._closed or self._fh is None:
            raise RuntimeError("EventLogger is closed")
        record = {
            "run_id": self.run_id,
            "ts": ts,
            "product": product,
            "state": {
                "order_depth": {
                    "buy": {str(p): v for p, v in order_depth.buy_orders.items()},
                    "sell": {str(p): v for p, v in order_depth.sell_orders.items()},
                },
                "position": position,
                "market_trades": [
                    {
                        "price": t.price,
                        "qty": t.quantity,
                        "buyer": t.buyer,
                        "seller": t.seller,
                    }
                    for t in market_trades
                ],
            },
            "actions": {
                "orders": [{"price": o.price, "qty": o.quantity} for o in orders],
            },
            "fills": [
                {"price": f.price, "qty": f.quantity, "source": f.source} for f in fills
            ],
            "pnl": pnl,
            "debug": debug or {},
        }
        self._fh.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
        self._fh.write("\n")

    def close(self) -> None:
        if self._closed:
            return
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
        self._closed = True

    def __enter__(self) -> EventLogger:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class NoOpLogger:
    """Submission-safe logger — discards everything. Used when running in the IMC environment."""

    def write(self, **_kwargs: Any) -> None:
        return None

    def close(self) -> None:
        return None
