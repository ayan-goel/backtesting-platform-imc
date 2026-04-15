"""MC correctness anchor: identity generator produces a MarketData byte-equal
to the historical one, and running the simulator on it yields a PnL identical
to a vanilla `simulate_day` run.

This test must never regress — it catches any future bug in the MC plumbing
that accidentally mutates historical data.
"""

from __future__ import annotations

from pathlib import Path

from engine.market.loader import MarketData
from engine.matching.imc_matcher import ImcMatcher
from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.generators.identity import IdentityGenerator
from engine.montecarlo.rng import rng_for_path
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader
from tests.engine._mc_fixtures import GREEDY_TRADER_SRC, make_synthetic_market_data


def _write_strategy(tmp_path: Path, source: bytes) -> Path:
    path = tmp_path / "strat.py"
    path.write_bytes(source)
    return path


def _build_run_config(tmp_path: Path, name: str, strategy_path: Path) -> RunConfig:
    return RunConfig(
        run_id=f"test-{name}",
        strategy_path=str(strategy_path),
        strategy_hash=hash_strategy_file(strategy_path),
        round=0,
        day=0,
        matcher_name="imc",
        position_limits={"KELP": 50, "RESIN": 50},
        output_dir=tmp_path / name,
    )


def test_identity_returns_historical_unchanged() -> None:
    md = make_synthetic_market_data()
    rng = rng_for_path(run_seed=42, path_index=0)
    synthetic = build_synthetic_market_data(
        historical=md,
        generator=IdentityGenerator(),
        calibration=None,
        params={},
        rng=rng,
    )
    assert synthetic is md
    assert synthetic.frames == md.frames


def test_identity_pnl_equals_direct_simulate_day(tmp_path: Path) -> None:
    md = make_synthetic_market_data()
    strategy = _write_strategy(tmp_path, GREEDY_TRADER_SRC)
    trader_a = load_trader(strategy)
    trader_b = load_trader(strategy)

    config_a = _build_run_config(tmp_path, "direct", strategy)
    config_b = _build_run_config(tmp_path, "mc", strategy)

    result_direct = simulate_day(
        trader=trader_a,
        market_data=md,
        matcher=ImcMatcher(),
        config=config_a,
    )

    rng = rng_for_path(run_seed=1234, path_index=0)
    synthetic = build_synthetic_market_data(
        historical=md,
        generator=IdentityGenerator(),
        calibration=None,
        params={},
        rng=rng,
    )
    result_mc = simulate_day(
        trader=trader_b,
        market_data=synthetic,
        matcher=ImcMatcher(),
        config=config_b,
    )

    assert result_mc.summary.pnl_total == result_direct.summary.pnl_total
    assert result_mc.summary.pnl_by_product == result_direct.summary.pnl_by_product
    assert result_mc.summary.num_events == result_direct.summary.num_events


def test_rng_for_path_is_deterministic() -> None:
    a = rng_for_path(run_seed=42, path_index=5).standard_normal(10)
    b = rng_for_path(run_seed=42, path_index=5).standard_normal(10)
    c = rng_for_path(run_seed=42, path_index=6).standard_normal(10)
    assert (a == b).all()
    assert not (a == c).all()


def test_build_synthetic_rejects_changed_spine() -> None:
    md = make_synthetic_market_data(num_timestamps=50)

    class BadGenerator:
        name = "bad"

        def generate(self, *, historical: MarketData, **_: object) -> MarketData:
            return MarketData(
                round=historical.round,
                day=historical.day,
                timestamps=historical.timestamps[:-1],  # drop last ts
                products=historical.products,
                frames={
                    ts: historical.frames[ts] for ts in historical.timestamps[:-1]
                },
            )

    try:
        build_synthetic_market_data(
            historical=md,
            generator=BadGenerator(),  # type: ignore[arg-type]
            calibration=None,
            params={},
            rng=rng_for_path(run_seed=0, path_index=0),
        )
    except ValueError as e:
        assert "timestamp" in str(e)
    else:
        raise AssertionError("expected ValueError")
