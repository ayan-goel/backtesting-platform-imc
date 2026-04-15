"""Load IMC Prosperity `;`-delimited CSVs into an in-memory MarketData object."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from engine.datamodel.types import OrderDepth, Trade
from engine.errors import InvalidMarketDataError
from engine.market.schema import (
    EXPECTED_PRICE_COLUMNS,
    EXPECTED_TRADE_COLUMNS,
    PriceRow,
    TradeRow,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProductSnap:
    """Per-product market state at a single timestamp."""

    order_depth: OrderDepth
    market_trades: tuple[Trade, ...]
    mid_price: float | None


@dataclass(frozen=True, slots=True)
class MarketData:
    """Immutable container of one day of market data.

    `frames[ts][product]` -> ProductSnap. `timestamps` is sorted ascending.
    """

    round: int
    day: int
    timestamps: tuple[int, ...]
    products: tuple[str, ...]
    frames: dict[int, dict[str, ProductSnap]] = field(default_factory=dict)

    def snap_at(self, ts: int) -> dict[str, ProductSnap]:
        if ts not in self.frames:
            raise KeyError(f"timestamp {ts} not in MarketData (round={self.round}, day={self.day})")
        return self.frames[ts]


def load_round_day(round_num: int, day: int, data_root: Path) -> MarketData:
    """Load prices + trades CSVs for a single (round, day) under `data_root`.

    Expects: `{data_root}/prices_round_{round_num}_day_{day}.csv` and `trades_*.csv`.
    """
    prices_path = data_root / f"prices_round_{round_num}_day_{day}.csv"
    trades_path = data_root / f"trades_round_{round_num}_day_{day}.csv"

    if not prices_path.is_file():
        raise InvalidMarketDataError(f"prices file not found: {prices_path}")
    if not trades_path.is_file():
        raise InvalidMarketDataError(f"trades file not found: {trades_path}")

    price_rows = _read_price_rows(prices_path)
    trade_rows = _read_trade_rows(trades_path)

    frames: dict[int, dict[str, ProductSnap]] = {}
    products_set: set[str] = set()
    timestamps_set: set[int] = set()

    trades_by_key: dict[tuple[int, str], list[Trade]] = {}
    for tr in trade_rows:
        price_int = _coerce_trade_price(tr.price, tr.timestamp, tr.symbol)
        trades_by_key.setdefault((tr.timestamp, tr.symbol), []).append(
            Trade(
                symbol=tr.symbol,
                price=price_int,
                quantity=tr.quantity,
                buyer=tr.buyer or None,
                seller=tr.seller or None,
                timestamp=tr.timestamp,
            )
        )

    for row in price_rows:
        products_set.add(row.product)
        timestamps_set.add(row.timestamp)

        buy_orders = {p: v for p, v in row.bid_levels()}
        sell_orders = {p: v for p, v in row.ask_levels()}
        depth = OrderDepth(buy_orders=buy_orders, sell_orders=sell_orders)
        market_trades = tuple(trades_by_key.get((row.timestamp, row.product), ()))
        snap = ProductSnap(order_depth=depth, market_trades=market_trades, mid_price=row.mid_price)

        frames.setdefault(row.timestamp, {})[row.product] = snap

    timestamps = tuple(sorted(timestamps_set))
    products = tuple(sorted(products_set))

    if not timestamps:
        raise InvalidMarketDataError(f"no price rows in {prices_path}")

    return MarketData(
        round=round_num, day=day, timestamps=timestamps, products=products, frames=frames
    )


def _read_price_rows(path: Path) -> list[PriceRow]:
    rows: list[PriceRow] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        _assert_columns(reader.fieldnames, EXPECTED_PRICE_COLUMNS, path)
        for raw in reader:
            rows.append(
                PriceRow(
                    day=int(raw["day"]),
                    timestamp=int(raw["timestamp"]),
                    product=raw["product"],
                    bid_price_1=_maybe_int(raw["bid_price_1"]),
                    bid_volume_1=_maybe_int(raw["bid_volume_1"]),
                    bid_price_2=_maybe_int(raw["bid_price_2"]),
                    bid_volume_2=_maybe_int(raw["bid_volume_2"]),
                    bid_price_3=_maybe_int(raw["bid_price_3"]),
                    bid_volume_3=_maybe_int(raw["bid_volume_3"]),
                    ask_price_1=_maybe_int(raw["ask_price_1"]),
                    ask_volume_1=_maybe_int(raw["ask_volume_1"]),
                    ask_price_2=_maybe_int(raw["ask_price_2"]),
                    ask_volume_2=_maybe_int(raw["ask_volume_2"]),
                    ask_price_3=_maybe_int(raw["ask_price_3"]),
                    ask_volume_3=_maybe_int(raw["ask_volume_3"]),
                    mid_price=_maybe_float(raw["mid_price"]),
                    profit_and_loss=_maybe_float(raw["profit_and_loss"]),
                )
            )
    return rows


def _read_trade_rows(path: Path) -> list[TradeRow]:
    rows: list[TradeRow] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        _assert_columns(reader.fieldnames, EXPECTED_TRADE_COLUMNS, path)
        for raw in reader:
            rows.append(
                TradeRow(
                    timestamp=int(raw["timestamp"]),
                    buyer=(raw["buyer"] or None),
                    seller=(raw["seller"] or None),
                    symbol=raw["symbol"],
                    currency=raw["currency"],
                    price=float(raw["price"]),
                    quantity=int(raw["quantity"]),
                )
            )
    return rows


def _assert_columns(actual: Sequence[str] | None, expected: tuple[str, ...], path: Path) -> None:
    if actual is None:
        raise InvalidMarketDataError(f"{path} has no header row")
    if tuple(actual) != expected:
        raise InvalidMarketDataError(
            f"{path} column mismatch.\n  expected: {expected}\n  actual:   {tuple(actual)}"
        )


def _maybe_int(value: str) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _maybe_float(value: str) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _coerce_trade_price(price: float, ts: int, symbol: str) -> int:
    """Coerce a trade price to int, warning on fractional values."""
    int_price = int(price)
    if price != int_price:
        log.warning(
            "trade price not integer — coerced",
            ts=ts,
            symbol=symbol,
            raw_price=price,
            coerced=int_price,
        )
    return int_price
