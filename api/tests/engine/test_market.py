"""T3 tests: real-data loader + snapshot builder on tutorial-round-data."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.errors import InvalidMarketDataError
from engine.market.loader import load_round_day
from engine.market.snapshot import build_trading_state

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "tutorial-round-data"


@pytest.fixture(scope="module")
def md():
    return load_round_day(0, -2, DATA_ROOT)


def test_load_round_day_returns_sorted_unique_timestamps(md) -> None:
    assert len(md.timestamps) > 0
    assert list(md.timestamps) == sorted(set(md.timestamps))
    assert "EMERALDS" in md.products
    assert "TOMATOES" in md.products


def test_load_round_day_timestamp_count_matches_row_count(md) -> None:
    # 20000 price rows / 2 products per ts = 10000 unique timestamps
    path = DATA_ROOT / "prices_round_0_day_-2.csv"
    total_rows = sum(1 for _ in path.open()) - 1  # minus header
    assert len(md.timestamps) == total_rows // len(md.products)


def test_first_frame_has_expected_book_shape(md) -> None:
    first_ts = md.timestamps[0]
    frame = md.snap_at(first_ts)
    assert set(frame) == set(md.products)
    emerald = frame["EMERALDS"]
    assert emerald.order_depth.best_bid() == (9992, 11)
    assert emerald.order_depth.best_ask() == (10008, -11)
    assert emerald.mid_price == 10000.0


def test_sell_orders_are_negative(md) -> None:
    frame = md.snap_at(md.timestamps[0])
    for snap in frame.values():
        for volume in snap.order_depth.sell_orders.values():
            assert volume < 0, "sell volumes must be stored as negative ints"


def test_market_trades_attach_to_correct_frame(md) -> None:
    # trades_round_0_day_-2.csv line 2: 900;;;TOMATOES;XIRECS;5008.0;2
    frame_900 = md.snap_at(900)
    tomatoes_trades = frame_900["TOMATOES"].market_trades
    assert len(tomatoes_trades) >= 1
    first = next(t for t in tomatoes_trades if t.price == 5008 and t.quantity == 2)
    assert first.timestamp == 900


def test_build_trading_state_at_first_timestamp(md) -> None:
    first_ts = md.timestamps[0]
    state = build_trading_state(
        md,
        first_ts,
        positions={"EMERALDS": 0, "TOMATOES": 0},
        own_trades_last_ts={},
        trader_data="",
    )
    assert state.timestamp == first_ts
    assert set(state.order_depths) == set(md.products)
    assert state.position["EMERALDS"] == 0
    assert state.listings["EMERALDS"].denomination == "SEASHELLS"


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(InvalidMarketDataError):
        load_round_day(99, 99, tmp_path)


def test_wrong_delimiter_raises(tmp_path) -> None:
    prices = tmp_path / "prices_round_9_day_9.csv"
    trades = tmp_path / "trades_round_9_day_9.csv"
    prices.write_text("day,timestamp,product\n-2,0,EMERALDS\n")  # comma not semicolon
    trades.write_text("timestamp;buyer;seller;symbol;currency;price;quantity\n")
    with pytest.raises(InvalidMarketDataError):
        load_round_day(9, 9, tmp_path)
