"""simulate_day — main backtest loop.

Per timestamp:
  1. Build engine TradingState snapshot
  2. Convert to strategy-facing datamodel.TradingState via adapters
  3. Call trader.run(state) → (orders_by_symbol, conversions, trader_data)
  4. Coerce orders back to engine types
  5. Clamp orders against position limits
  6. Match clamped orders → fills
  7. Apply fills to SimState, update positions + cash
  8. Write event log row per product
  9. Stash trader_data for next iteration
Finally: build RunSummary and return a RunResult.
"""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from engine.datamodel import adapters
from engine.datamodel.types import Fill, Order, Trade
from engine.errors import SimulationError
from engine.logging.event_log import EventLogger, NoOpLogger
from engine.market.loader import MarketData
from engine.market.snapshot import build_trading_state
from engine.matching.base import Matcher
from engine.metrics.inventory import inventory_stats
from engine.metrics.summary import RunSummary, build_summary
from engine.simulator.limits import apply_position_limits
from engine.simulator.state import SimState
from engine.simulator.strategy_params import apply_params_to_module

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RunConfig:
    run_id: str
    strategy_path: str
    strategy_hash: str
    round: int
    day: int
    matcher_name: str
    position_limits: dict[str, int]
    output_dir: Path
    params: dict[str, Any] = field(default_factory=dict)
    engine_version: str = "0.1.0"
    default_limit: int = 50


@dataclass(slots=True)
class RunResult:
    summary: RunSummary
    events_path: Path


def simulate_day(
    *,
    trader: Any,
    market_data: MarketData,
    matcher: Matcher,
    config: RunConfig,
) -> RunResult:
    """Run a strategy across one day of market data and write artifacts to config.output_dir."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    events_path = config.output_dir / "events.jsonl"

    state = SimState()
    for product in market_data.products:
        state.positions.setdefault(product, 0)

    # Inject hyperparameters so strategies can read self.params.get(...).
    # Copy so trial mutations don't leak back into config. Suppress AttributeError
    # for traders declaring __slots__ without params — they opt out cleanly.
    with contextlib.suppress(AttributeError):
        trader.params = dict(config.params)

    # Also patch class-level UPPER_CASE constants on the trader's module. This
    # lets autodetected hyperparameters tune strategies that hardcode their
    # constants (e.g. `MR_WEIGHT = 0.5` on OsmiumTrader) without requiring the
    # author to rewrite them to read from `self.params`.
    trader_module = sys.modules.get(type(trader).__module__)
    if trader_module is not None:
        apply_params_to_module(trader_module, config.params)

    trader_data: str = ""
    own_trades_by_product: dict[str, tuple[Trade, ...]] = {}

    position_history_by_product: dict[str, list[int]] = {p: [] for p in market_data.products}
    fill_qtys_by_product: dict[str, list[int]] = {p: [] for p in market_data.products}

    start = time.monotonic()
    num_events = 0

    logger = EventLogger(config.run_id, events_path)
    try:
        for ts in market_data.timestamps:
            engine_state = build_trading_state(
                market_data,
                ts,
                positions=state.positions,
                own_trades_last_ts=own_trades_by_product,
                trader_data=trader_data,
            )

            dm_state = adapters.to_strategy_state(engine_state)

            try:
                result = trader.run(dm_state)
            except Exception as e:
                raise SimulationError(f"trader.run raised at ts={ts}: {e}") from e

            raw_orders, _conversions, new_trader_data = _unpack_trader_result(result, ts)
            trader_data = new_trader_data or ""

            engine_orders = adapters.from_strategy_orders({k: list(v) for k, v in raw_orders.items()})

            fills_for_ts: dict[str, list[Fill]] = {p: [] for p in market_data.products}
            clamped_by_symbol: dict[str, tuple[Order, ...]] = {}

            for symbol in market_data.products:
                orders = engine_orders.get(symbol, ())
                if not orders:
                    clamped_by_symbol[symbol] = ()
                    continue
                clamped = apply_position_limits(
                    current_position=state.positions.get(symbol, 0),
                    pending_orders=orders,
                    limit=config.position_limits.get(symbol, config.default_limit),
                )
                clamped_by_symbol[symbol] = clamped

            fills = matcher.match(
                ts=ts,
                order_depths={p: engine_state.order_depths[p] for p in engine_state.order_depths},
                orders_by_symbol={k: v for k, v in clamped_by_symbol.items() if v},
                market_trades=engine_state.market_trades,
            )

            for fill in fills:
                state.apply_fill(fill)
                fills_for_ts.setdefault(fill.symbol, []).append(fill)
                fill_qtys_by_product.setdefault(fill.symbol, []).append(fill.quantity)

            _verify_limits(state.positions, config)

            new_own_trades: dict[str, list[Trade]] = {}
            for fill in fills:
                new_own_trades.setdefault(fill.symbol, []).append(
                    Trade(
                        symbol=fill.symbol,
                        price=fill.price,
                        quantity=fill.quantity,
                        timestamp=ts,
                    )
                )
            own_trades_by_product = {k: tuple(v) for k, v in new_own_trades.items()}

            mid_prices = {
                p: engine_state.order_depths[p].mid_price() or state.vwap_cost.get(p, 0.0)
                for p in engine_state.order_depths
            }

            for product in engine_state.order_depths:
                depth = engine_state.order_depths[product]
                cash = state.cash
                mark = state.mark_to_market(mid_prices)
                total = cash + sum(
                    pos * mid_prices.get(sym, 0.0) for sym, pos in state.positions.items()
                )
                logger.write(
                    ts=ts,
                    product=product,
                    order_depth=depth,
                    position=state.positions.get(product, 0),
                    market_trades=engine_state.market_trades.get(product, ()),
                    orders=clamped_by_symbol.get(product, ()),
                    fills=fills_for_ts.get(product, []),
                    pnl={"cash": cash, "mark": mark, "total": total},
                )
                num_events += 1
                position_history_by_product[product].append(state.positions.get(product, 0))
    finally:
        logger.close()

    duration_ms = int((time.monotonic() - start) * 1000)

    pnl_by_product: dict[str, float] = {}
    for product in market_data.products:
        cost = state.vwap_cost.get(product, 0.0)
        pos = state.positions.get(product, 0)
        # Realized + unrealized at final mid
        last_ts = market_data.timestamps[-1]
        last_mid = market_data.snap_at(last_ts)[product].mid_price or cost
        pnl_by_product[product] = state.realized_pnl_by_product.get(product, 0.0) + (
            last_mid - cost
        ) * pos

    max_inv_by_product: dict[str, int] = {}
    turnover_by_product: dict[str, int] = {}
    for product in market_data.products:
        stats = inventory_stats(
            position_history_by_product[product], fill_qtys_by_product[product]
        )
        max_inv_by_product[product] = stats.max_abs_position
        turnover_by_product[product] = stats.turnover

    summary = build_summary(
        run_id=config.run_id,
        strategy_path=config.strategy_path,
        strategy_hash=config.strategy_hash,
        round_num=config.round,
        day=config.day,
        matcher=config.matcher_name,
        params=config.params,
        engine_version=config.engine_version,
        duration_ms=duration_ms,
        pnl_total=sum(pnl_by_product.values()),
        pnl_by_product=pnl_by_product,
        max_inventory_by_product=max_inv_by_product,
        turnover_by_product=turnover_by_product,
        num_events=num_events,
        artifact_dir=str(config.output_dir),
    )

    return RunResult(summary=summary, events_path=events_path)


def _unpack_trader_result(
    result: Any, ts: int
) -> tuple[dict[str, list[Any]], int, str]:
    """Accept either the 3-tuple return `(orders, conversions, trader_data)` or legacy 2-tuple."""
    if isinstance(result, tuple):
        if len(result) == 3:
            orders, conversions, trader_data = result
            return orders or {}, int(conversions or 0), str(trader_data or "")
        if len(result) == 2:
            orders, trader_data = result
            return orders or {}, 0, str(trader_data or "")
    raise SimulationError(
        f"trader.run at ts={ts} returned unexpected type: {type(result).__name__}"
    )


def _verify_limits(positions: dict[str, int], config: RunConfig) -> None:
    for symbol, pos in positions.items():
        limit = config.position_limits.get(symbol, config.default_limit)
        if abs(pos) > limit:
            raise SimulationError(
                f"position limit breach: {symbol} position={pos} limit={limit}"
            )


__all__ = ["NoOpLogger", "RunConfig", "RunResult", "simulate_day"]
