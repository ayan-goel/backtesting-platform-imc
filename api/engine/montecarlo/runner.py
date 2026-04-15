"""MC-specific simulation loop.

Mirrors `engine.simulator.runner.simulate_day` but:

1. Uses `NoOpLogger` — MC never persists per-event logs.
2. Records a compact total-PnL-per-timestamp curve for aggregation.
3. Does not touch `config.output_dir` for event artifacts (the MC runner
   stores only `paths/{i}.npy` curves under the mc dir).
4. Tolerates `RunConfig.run_id` as a display-only string (no file IO).

Why duplicate instead of refactoring `simulate_day`? The production path
has extensive golden parity tests against `prosperity4btx` — any seam
refactor risks accidentally regressing parity. This module is the only
consumer of the MC loop, so duplication here is cheaper than a cross-
cutting refactor.

Future: if this drifts from `simulate_day`, extract the shared inner
step helper into a private module both call. Today the two are
byte-identical except for the points listed above, and the MC path
metrics test in `test_mc_runner_metrics.py` pins them together.
"""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from engine.datamodel import adapters
from engine.datamodel.types import Order, Trade
from engine.errors import SimulationError
from engine.market.loader import MarketData
from engine.market.snapshot import build_trading_state
from engine.matching.base import Matcher
from engine.metrics.inventory import inventory_stats
from engine.metrics.summary import RunSummary, build_summary
from engine.simulator.limits import apply_position_limits
from engine.simulator.runner import RunConfig
from engine.simulator.state import SimState
from engine.simulator.strategy_params import apply_params_to_module


@dataclass(slots=True)
class McPathResult:
    summary: RunSummary
    pnl_curve: np.ndarray  # float64[num_timestamps], total pnl per ts
    max_drawdown: float
    sharpe_intraday: float
    num_fills: int
    duration_ms: int


def simulate_day_mc(
    *,
    trader: Any,
    market_data: MarketData,
    matcher: Matcher,
    config: RunConfig,
) -> McPathResult:
    """Run a strategy across a synthetic day. Returns lightweight metrics.

    Does not write to disk. The caller is responsible for persisting
    whatever compact artifacts it wants (e.g. the downsampled curve).
    """
    state = SimState()
    for product in market_data.products:
        state.positions.setdefault(product, 0)

    with contextlib.suppress(AttributeError):
        trader.params = dict(config.params)

    trader_module = sys.modules.get(type(trader).__module__)
    if trader_module is not None:
        apply_params_to_module(trader_module, config.params)

    trader_data: str = ""
    own_trades_by_product: dict[str, tuple[Trade, ...]] = {}

    position_history_by_product: dict[str, list[int]] = {
        p: [] for p in market_data.products
    }
    fill_qtys_by_product: dict[str, list[int]] = {p: [] for p in market_data.products}

    n_ts = len(market_data.timestamps)
    pnl_curve = np.zeros(n_ts, dtype=np.float64)
    num_fills = 0

    start = time.monotonic()

    for idx, ts in enumerate(market_data.timestamps):
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

        engine_orders = adapters.from_strategy_orders(
            {k: list(v) for k, v in raw_orders.items()}
        )

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
            order_depths={
                p: engine_state.order_depths[p] for p in engine_state.order_depths
            },
            orders_by_symbol={k: v for k, v in clamped_by_symbol.items() if v},
            market_trades=engine_state.market_trades,
        )

        for fill in fills:
            state.apply_fill(fill)
            fill_qtys_by_product.setdefault(fill.symbol, []).append(fill.quantity)
        num_fills += len(fills)

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

        cash = state.cash
        positions_value = sum(
            pos * mid_prices.get(sym, 0.0) for sym, pos in state.positions.items()
        )
        total = cash + positions_value
        pnl_curve[idx] = total

        for product in engine_state.order_depths:
            position_history_by_product[product].append(
                state.positions.get(product, 0)
            )

    duration_ms = int((time.monotonic() - start) * 1000)

    pnl_by_product: dict[str, float] = {}
    last_ts = market_data.timestamps[-1]
    last_snap = market_data.snap_at(last_ts)
    for product in market_data.products:
        cost = state.vwap_cost.get(product, 0.0)
        pos = state.positions.get(product, 0)
        last_mid = last_snap[product].mid_price or cost
        pnl_by_product[product] = state.realized_pnl_by_product.get(
            product, 0.0
        ) + (last_mid - cost) * pos

    max_inv_by_product: dict[str, int] = {}
    turnover_by_product: dict[str, int] = {}
    for product in market_data.products:
        stats = inventory_stats(
            position_history_by_product[product], fill_qtys_by_product[product]
        )
        max_inv_by_product[product] = stats.max_abs_position
        turnover_by_product[product] = stats.turnover

    pnl_total = sum(pnl_by_product.values())

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
        pnl_total=pnl_total,
        pnl_by_product=pnl_by_product,
        max_inventory_by_product=max_inv_by_product,
        turnover_by_product=turnover_by_product,
        num_events=n_ts * len(market_data.products),
        artifact_dir="",
    )

    max_dd = _max_drawdown(pnl_curve)
    sharpe = _intraday_sharpe(pnl_curve)

    return McPathResult(
        summary=summary,
        pnl_curve=pnl_curve,
        max_drawdown=max_dd,
        sharpe_intraday=sharpe,
        num_fills=num_fills,
        duration_ms=duration_ms,
    )


def downsample_curve(curve: np.ndarray, n: int = 256) -> np.ndarray:
    """Linearly interpolate the pnl curve onto `n` evenly spaced points.

    Output is float32 and always exactly `n` samples, even for short
    curves (the first and last values anchor the endpoints). Used for
    aggregation + fan chart rendering.
    """
    if curve.size == 0:
        return np.zeros(n, dtype=np.float32)
    if curve.size == 1:
        return np.full(n, float(curve[0]), dtype=np.float32)
    x_src = np.linspace(0.0, 1.0, curve.size)
    x_dst = np.linspace(0.0, 1.0, n)
    resampled: np.ndarray = np.interp(x_dst, x_src, curve).astype(np.float32)
    return resampled


def _max_drawdown(curve: np.ndarray) -> float:
    """Return the most negative peak-to-trough drawdown (<=0)."""
    if curve.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(curve)
    drawdowns = curve - running_max
    return float(drawdowns.min())


def _intraday_sharpe(curve: np.ndarray) -> float:
    """Per-step pnl-change Sharpe (mean / std). Guarded against zero variance."""
    if curve.size < 2:
        return 0.0
    diffs = np.diff(curve)
    std = float(diffs.std(ddof=1)) if diffs.size > 1 else 0.0
    if std <= 0:
        return 0.0
    return float(diffs.mean()) / std


def _unpack_trader_result(
    result: Any, ts: int
) -> tuple[dict[str, list[Any]], int, str]:
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


__all__ = ["McPathResult", "downsample_curve", "simulate_day_mc"]
