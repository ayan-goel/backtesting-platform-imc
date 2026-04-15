"""Write a tiny synthetic dataset to storage so MC/runner tests can load it
via `load_round_day`. Unlike the default `seeded_dataset` fixture in
`conftest.py`, this one does not depend on the external `tutorial-round-data/`
directory being present in the checkout.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRICE_COLUMNS = (
    "day;timestamp;product;"
    "bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;"
    "ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;"
    "mid_price;profit_and_loss"
)
TRADE_COLUMNS = "timestamp;buyer;seller;symbol;currency;price;quantity"


def write_synthetic_csvs(
    *,
    datasets_dir: Path,
    round_num: int,
    day: int,
    products: tuple[str, ...] = ("KELP", "RESIN"),
    num_timestamps: int = 80,
) -> tuple[Path, Path, list[str]]:
    datasets_dir.mkdir(parents=True, exist_ok=True)
    prices_path = datasets_dir / f"prices_round_{round_num}_day_{day}.csv"
    trades_path = datasets_dir / f"trades_round_{round_num}_day_{day}.csv"

    base_prices = {"KELP": 10_000, "RESIN": 5_000}
    price_lines = [PRICE_COLUMNS]
    trade_lines = [TRADE_COLUMNS]

    for i in range(num_timestamps):
        ts = i * 100
        for p_idx, product in enumerate(products):
            base = base_prices.get(product, 1_000 + p_idx * 500)
            osc = round(10 * math.sin(0.05 * i + p_idx))
            mid = base + osc

            bid1, bid1v = mid - 2, 20
            bid2, bid2v = mid - 3, 15
            bid3, bid3v = mid - 4, 10
            ask1, ask1v = mid + 2, 20
            ask2, ask2v = mid + 3, 15
            ask3, ask3v = mid + 4, 10

            price_lines.append(
                f"{day};{ts};{product};"
                f"{bid1};{bid1v};{bid2};{bid2v};{bid3};{bid3v};"
                f"{ask1};{ask1v};{ask2};{ask2v};{ask3};{ask3v};"
                f"{mid}.0;0.0"
            )
            trade_lines.append(f"{ts};;;{product};SEASHELLS;{mid};3")

    prices_path.write_text("\n".join(price_lines) + "\n")
    trades_path.write_text("\n".join(trade_lines) + "\n")
    return prices_path, trades_path, list(products)


def dataset_doc_for(
    *,
    round_num: int,
    day: int,
    prices_path: Path,
    trades_path: Path,
    products: list[str],
    num_timestamps: int,
) -> dict[str, Any]:
    return {
        "_id": f"r{round_num}d{day}",
        "round": round_num,
        "day": day,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "products": products,
        "num_timestamps": num_timestamps,
        "prices_filename": prices_path.name,
        "trades_filename": trades_path.name,
        "prices_bytes": prices_path.stat().st_size,
        "trades_bytes": trades_path.stat().st_size,
    }
