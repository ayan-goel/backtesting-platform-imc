"""T6 tests: EventLogger JSONL schema + NoOpLogger."""

from __future__ import annotations

import json
from pathlib import Path

from engine.datamodel.types import Fill, Order, OrderDepth, Trade
from engine.logging.event_log import EventLogger, NoOpLogger


def _sample_depth() -> OrderDepth:
    return OrderDepth(buy_orders={9999: 10}, sell_orders={10001: -12})


def test_event_logger_writes_valid_json_lines(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    logger = EventLogger("run-1", out)
    logger.write(
        ts=0,
        product="KELP",
        order_depth=_sample_depth(),
        position=0,
        market_trades=(Trade("KELP", 10000, 1),),
        orders=(Order("KELP", 10000, -5),),
        fills=[Fill("KELP", 10000, -5, "book", 0)],
        pnl={"cash": 50000.0, "mark": 0.0, "total": 50000.0},
    )
    logger.close()

    lines = out.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["run_id"] == "run-1"
    assert record["ts"] == 0
    assert record["product"] == "KELP"
    # Schema shape per SPEC §6
    assert set(record) >= {"run_id", "ts", "product", "state", "actions", "fills", "pnl", "debug"}
    assert record["state"]["order_depth"]["sell"] == {"10001": -12}
    assert record["state"]["position"] == 0
    assert record["fills"][0]["qty"] == -5


def test_event_logger_sells_are_negative(tmp_path: Path) -> None:
    out = tmp_path / "events.jsonl"
    with EventLogger("run-2", out) as logger:
        logger.write(
            ts=1,
            product="KELP",
            order_depth=OrderDepth(buy_orders={}, sell_orders={10001: -5, 10002: -3}),
            position=0,
            market_trades=(),
            orders=(),
            fills=[],
            pnl={"cash": 0.0, "mark": 0.0, "total": 0.0},
        )

    record = json.loads(out.read_text().strip())
    for volume in record["state"]["order_depth"]["sell"].values():
        assert volume < 0


def test_event_logger_close_is_idempotent(tmp_path: Path) -> None:
    logger = EventLogger("run-3", tmp_path / "e.jsonl")
    logger.close()
    logger.close()  # should not raise


def test_no_op_logger_discards(tmp_path: Path) -> None:
    logger = NoOpLogger()
    logger.write(ts=0, product="KELP")  # arbitrary kwargs ignored
    logger.close()
