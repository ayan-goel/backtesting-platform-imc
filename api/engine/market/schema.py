"""Pydantic models for raw IMC Prosperity CSV rows.

Prices CSV columns (17, `;`-delimited):
    day, timestamp, product,
    bid_price_1, bid_volume_1, bid_price_2, bid_volume_2, bid_price_3, bid_volume_3,
    ask_price_1, ask_volume_1, ask_price_2, ask_volume_2, ask_price_3, ask_volume_3,
    mid_price, profit_and_loss

Trades CSV columns (7):
    timestamp, buyer, seller, symbol, currency, price, quantity
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

EXPECTED_PRICE_COLUMNS: tuple[str, ...] = (
    "day",
    "timestamp",
    "product",
    "bid_price_1",
    "bid_volume_1",
    "bid_price_2",
    "bid_volume_2",
    "bid_price_3",
    "bid_volume_3",
    "ask_price_1",
    "ask_volume_1",
    "ask_price_2",
    "ask_volume_2",
    "ask_price_3",
    "ask_volume_3",
    "mid_price",
    "profit_and_loss",
)

EXPECTED_TRADE_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "buyer",
    "seller",
    "symbol",
    "currency",
    "price",
    "quantity",
)


class PriceRow(BaseModel):
    """Single row from prices_round_N_day_M.csv."""

    model_config = ConfigDict(frozen=True)

    day: int
    timestamp: int
    product: str
    bid_price_1: int | None = None
    bid_volume_1: int | None = None
    bid_price_2: int | None = None
    bid_volume_2: int | None = None
    bid_price_3: int | None = None
    bid_volume_3: int | None = None
    ask_price_1: int | None = None
    ask_volume_1: int | None = None
    ask_price_2: int | None = None
    ask_volume_2: int | None = None
    ask_price_3: int | None = None
    ask_volume_3: int | None = None
    mid_price: float | None = None
    profit_and_loss: float | None = None

    def bid_levels(self) -> list[tuple[int, int]]:
        """Return present (price, volume) pairs for bids, ordered as in the file."""
        levels: list[tuple[int, int]] = []
        for price, volume in (
            (self.bid_price_1, self.bid_volume_1),
            (self.bid_price_2, self.bid_volume_2),
            (self.bid_price_3, self.bid_volume_3),
        ):
            if price is not None and volume is not None:
                levels.append((price, volume))
        return levels

    def ask_levels(self) -> list[tuple[int, int]]:
        """Return present (price, volume) pairs for asks. Volumes are normalized negative."""
        levels: list[tuple[int, int]] = []
        for price, volume in (
            (self.ask_price_1, self.ask_volume_1),
            (self.ask_price_2, self.ask_volume_2),
            (self.ask_price_3, self.ask_volume_3),
        ):
            if price is not None and volume is not None:
                signed = -abs(volume)
                levels.append((price, signed))
        return levels


class TradeRow(BaseModel):
    """Single row from trades_round_N_day_M.csv."""

    model_config = ConfigDict(frozen=True)

    timestamp: int
    buyer: str | None = Field(default=None)
    seller: str | None = Field(default=None)
    symbol: str
    currency: str
    price: float  # fractional in raw data; loader coerces to int with warning
    quantity: int
