"""T8 tests: simulate_day glue end-to-end on real tutorial data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.market.loader import MarketData, load_round_day
from engine.matching.depth_only import DepthOnlyMatcher
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_ROOT = REPO_ROOT / "tutorial-round-data"

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""


@pytest.fixture(scope="module")
def tutorial_md() -> MarketData:
    return load_round_day(0, -2, DATA_ROOT)


def test_simulate_day_runs_minimal_trader_on_tutorial(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    strategy = tmp_path / "noop.py"
    strategy.write_bytes(MINIMAL_TRADER)
    trader = load_trader(strategy)
    config = RunConfig(
        run_id="test-run-1",
        strategy_path=str(strategy),
        strategy_hash=hash_strategy_file(strategy),
        round=0,
        day=-2,
        matcher_name="depth_only",
        position_limits={"EMERALDS": 50, "TOMATOES": 50},
        output_dir=tmp_path / "run1",
    )

    result = simulate_day(
        trader=trader,
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )

    # Artifacts
    assert result.events_path.is_file()
    lines = result.events_path.read_text().splitlines()
    assert len(lines) == len(tutorial_md.timestamps) * len(tutorial_md.products)

    first = json.loads(lines[0])
    assert first["run_id"] == "test-run-1"
    assert "state" in first
    assert "fills" in first
    assert "pnl" in first

    # Summary invariants
    s = result.summary
    assert s.num_events == len(lines)
    assert s.duration_ms >= 0
    assert isinstance(s.pnl_total, float)
    # No NaN / inf
    assert s.pnl_total == s.pnl_total


def test_simulate_day_respects_position_limits(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    # A pathological trader that always wants to buy max size — should never breach limit
    class GreedyTrader:
        def run(self, state: Any) -> tuple[dict[str, list[Any]], int, str]:
            from datamodel import Order

            orders: dict[str, list[Any]] = {}
            for product in state.order_depths:
                orders[product] = [Order(product, 99999, 1000)]
            return orders, 0, ""

    config = RunConfig(
        run_id="test-greedy",
        strategy_path="<synthetic>",
        strategy_hash="sha256:synthetic",
        round=0,
        day=-2,
        matcher_name="depth_only",
        position_limits={"EMERALDS": 50, "TOMATOES": 50},
        output_dir=tmp_path / "greedy",
    )
    result = simulate_day(
        trader=GreedyTrader(),
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )
    # Max inventory must not exceed limit
    assert result.summary.max_inventory_by_product["EMERALDS"] <= 50
    assert result.summary.max_inventory_by_product["TOMATOES"] <= 50
