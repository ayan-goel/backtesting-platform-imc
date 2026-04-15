"""T7 tests: strategy loader with synthetic Trader files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine.errors import StrategyLoadError
from engine.simulator.strategy_loader import hash_strategy_file, load_trader

MINIMAL_TRADER = b"""
class Trader:
    def run(self, state):
        return {}, 0, ""
"""


def _write_strategy(tmp_path: Path, name: str = "noop.py") -> Path:
    path = tmp_path / name
    path.write_bytes(MINIMAL_TRADER)
    return path


def test_load_minimal_strategy(tmp_path: Path) -> None:
    trader = load_trader(_write_strategy(tmp_path))
    assert trader is not None
    assert hasattr(trader, "run")
    assert callable(trader.run)


def test_loader_restores_sys_path(tmp_path: Path) -> None:
    path_before = list(sys.path)
    load_trader(_write_strategy(tmp_path))
    path_after = list(sys.path)
    assert path_after == path_before


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(StrategyLoadError, match="not found"):
        load_trader(tmp_path / "nope.py")


def test_no_trader_class_raises(tmp_path: Path) -> None:
    strategy = tmp_path / "empty.py"
    strategy.write_text("# nothing here\n")
    with pytest.raises(StrategyLoadError, match="no Trader class"):
        load_trader(strategy)


def test_load_strategy_using_strategies_datamodel_alias(tmp_path: Path) -> None:
    """Users whose strategies live in a `strategies/` folder often import via
    `from strategies.datamodel import ...`. The loader must route that to the
    bundled shim without needing any on-disk `strategies/` package.
    """
    strategy = tmp_path / "round0.py"
    strategy.write_text(
        "from strategies.datamodel import Order, TradingState\n"
        "\n"
        "class Trader:\n"
        "    def run(self, state: TradingState):\n"
        "        return {'KELP': [Order('KELP', 9999, 1)]}, 0, ''\n"
    )
    trader = load_trader(strategy)
    assert trader is not None

    # Aliases should be cleaned up after load — no lingering `strategies` module.
    assert "strategies" not in sys.modules
    assert "strategies.datamodel" not in sys.modules


def test_load_strategy_using_plain_datamodel_still_works(tmp_path: Path) -> None:
    strategy = tmp_path / "round0.py"
    strategy.write_text(
        "from datamodel import Order\n"
        "\n"
        "class Trader:\n"
        "    def run(self, state):\n"
        "        return {'KELP': [Order('KELP', 9999, 1)]}, 0, ''\n"
    )
    trader = load_trader(strategy)
    assert trader is not None


def test_hash_strategy_file_is_stable(tmp_path: Path) -> None:
    path = _write_strategy(tmp_path)
    h1 = hash_strategy_file(path)
    h2 = hash_strategy_file(path)
    assert h1 == h2
    assert h1.startswith("sha256:")
