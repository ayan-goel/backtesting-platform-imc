"""O1 tests: simulate_day injects config.params onto trader.params before the loop."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

from engine.market.loader import MarketData, load_round_day
from engine.matching.depth_only import DepthOnlyMatcher
from engine.simulator.runner import RunConfig, simulate_day

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "tutorial-round-data"


@pytest.fixture(scope="module")
def tutorial_md() -> MarketData:
    return load_round_day(0, -2, DATA_ROOT)


def _make_config(tmp_path: Path, params: dict[str, Any]) -> RunConfig:
    return RunConfig(
        run_id="test-params",
        strategy_path="inline",
        strategy_hash="sha256:test",
        round=0,
        day=-2,
        matcher_name="depth_only",
        position_limits={"EMERALDS": 50, "TOMATOES": 50},
        output_dir=tmp_path / "run",
        params=params,
    )


def test_simulate_day_injects_params_into_trader(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    observed: list[int] = []

    class ParamReadingTrader:
        params: ClassVar[dict[str, Any]] = {}

        def run(self, state: Any) -> tuple[dict[str, list[Any]], int, str]:
            observed.append(self.params.get("edge", -1))
            return {}, 0, ""

    trader = ParamReadingTrader()
    config = _make_config(tmp_path, {"edge": 7})

    simulate_day(
        trader=trader,
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )

    assert observed, "trader.run was never called"
    assert all(v == 7 for v in observed), f"expected all 7, got distinct values: {set(observed)}"
    assert trader.params == {"edge": 7}


def test_simulate_day_empty_params_leaves_trader_with_empty_dict(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    observed: list[int] = []

    class ParamReadingTrader:
        params: ClassVar[dict[str, Any]] = {}

        def run(self, state: Any) -> tuple[dict[str, list[Any]], int, str]:
            observed.append(self.params.get("edge", -1))
            return {}, 0, ""

    trader = ParamReadingTrader()
    config = _make_config(tmp_path, {})

    simulate_day(
        trader=trader,
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )

    assert observed
    assert all(v == -1 for v in observed)
    assert trader.params == {}


def test_simulate_day_copies_params_does_not_share_reference(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    class MutatingTrader:
        params: ClassVar[dict[str, Any]] = {}

        def run(self, state: Any) -> tuple[dict[str, list[Any]], int, str]:
            self.params["edge"] = 999
            return {}, 0, ""

    trader = MutatingTrader()
    original_params = {"edge": 1}
    config = _make_config(tmp_path, original_params)

    simulate_day(
        trader=trader,
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )

    # Mutations by the trader must not leak back into the config dict.
    assert original_params == {"edge": 1}


def test_simulate_day_patches_class_level_constants_from_params(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    """Autodetected params must actually propagate into the simulation.

    We build a synthetic module that owns a `Trader` whose behavior is driven by
    an UPPER_CASE class constant — this mirrors how round1.py works. If
    simulate_day wires config.params into class attributes, the observed constant
    during trader.run should match the injected value.
    """
    mod = types.ModuleType("_fake_strategy_for_param_patch_test")
    src = """
from typing import Any, ClassVar

class Helper:
    MR_WEIGHT = 0.5

class Trader:
    observed: ClassVar[list[float]] = []
    def run(self, state: Any):
        self.observed.append(Helper.MR_WEIGHT)
        return {}, 0, ""
"""
    exec(src, mod.__dict__)
    sys.modules[mod.__name__] = mod
    try:
        trader_cls = mod.__dict__["Trader"]
        trader = trader_cls()
        config = _make_config(tmp_path, {"MR_WEIGHT": 0.25})

        simulate_day(
            trader=trader,
            market_data=tutorial_md,
            matcher=DepthOnlyMatcher(),
            config=config,
        )

        observed = trader_cls.observed
        assert observed, "trader.run was never called"
        assert all(v == 0.25 for v in observed), (
            f"class constant was not patched, saw: {set(observed)}"
        )
    finally:
        sys.modules.pop(mod.__name__, None)


def test_simulate_day_class_patching_ignores_unknown_param_keys(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    """Passing keys that don't match any class attribute must be harmless —
    they may still be consumed via self.params.get(...)."""
    mod = types.ModuleType("_fake_strategy_for_param_patch_unknown_keys")
    src = """
from typing import Any

class Helper:
    MR_WEIGHT = 0.5

class Trader:
    def run(self, state: Any):
        return {}, 0, ""
"""
    exec(src, mod.__dict__)
    sys.modules[mod.__name__] = mod
    try:
        trader = mod.__dict__["Trader"]()
        config = _make_config(tmp_path, {"UNKNOWN_KEY": 7, "also_ignored": 1})

        simulate_day(
            trader=trader,
            market_data=tutorial_md,
            matcher=DepthOnlyMatcher(),
            config=config,
        )

        # Untouched.
        assert mod.__dict__["Helper"].MR_WEIGHT == 0.5
    finally:
        sys.modules.pop(mod.__name__, None)


ROUND1_STRATEGY = REPO_ROOT / "strategies" / "ayan" / "round1.py"
ROUND1_DATA = REPO_ROOT / "data-round-1"
ROUND1_AVAILABLE = ROUND1_STRATEGY.is_file() and (ROUND1_DATA / "prices_round_1_day_-2.csv").is_file()


@pytest.mark.skipif(
    not ROUND1_AVAILABLE, reason="round1.py or data-round-1/ not present"
)
def test_end_to_end_param_tuning_changes_pnl_against_round1(tmp_path: Path) -> None:
    """End-to-end: load round1.py from disk, run simulate_day twice with different
    MR_WEIGHT values, and assert the resulting PnLs differ. This is the whole
    autodetect → patch → simulate loop running against the real strategy.
    """
    from engine.market.loader import load_round_day
    from engine.simulator.strategy_loader import load_trader
    from engine.simulator.strategy_params import extract_tunable_params

    # 1. Detection step must find MR_WEIGHT on the real strategy file.
    detected = extract_tunable_params(ROUND1_STRATEGY)
    names = {p.name for p in detected}
    assert "MR_WEIGHT" in names
    assert "SKEW_PER_UNIT" in names
    assert "SOFT_LIMIT" in names

    md = load_round_day(1, -2, ROUND1_DATA)

    def _run_with(mr_weight: float, soft_limit: int) -> float:
        trader = load_trader(ROUND1_STRATEGY)
        run_dir = tmp_path / f"run_mr_{mr_weight}_soft_{soft_limit}"
        config = RunConfig(
            run_id=f"e2e-{mr_weight}-{soft_limit}",
            strategy_path=str(ROUND1_STRATEGY),
            strategy_hash="sha256:test",
            round=1,
            day=-2,
            matcher_name="depth_only",
            position_limits={"ASH_COATED_OSMIUM": 50, "INTARIAN_PEPPER_ROOT": 50},
            output_dir=run_dir,
            params={"MR_WEIGHT": mr_weight, "SOFT_LIMIT": soft_limit},
        )
        result = simulate_day(
            trader=trader,
            market_data=md,
            matcher=DepthOnlyMatcher(),
            config=config,
        )
        return result.summary.pnl_total

    # Two very different param sets should produce different PnL numbers.
    pnl_a = _run_with(mr_weight=0.0, soft_limit=40)
    pnl_b = _run_with(mr_weight=0.9, soft_limit=20)

    assert pnl_a != pnl_b, (
        f"expected different PnL across param sets, got {pnl_a} == {pnl_b} "
        "— class-level constant patching is not reaching the strategy"
    )


def test_simulate_day_slots_trader_does_not_crash(
    tmp_path: Path, tutorial_md: MarketData
) -> None:
    class SlottedTrader:
        __slots__ = ()

        def run(self, state: Any) -> tuple[dict[str, list[Any]], int, str]:
            return {}, 0, ""

    trader = SlottedTrader()
    config = _make_config(tmp_path, {"edge": 7})

    result = simulate_day(
        trader=trader,
        market_data=tutorial_md,
        matcher=DepthOnlyMatcher(),
        config=config,
    )

    assert result.events_path.is_file()
