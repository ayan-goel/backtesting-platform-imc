"""T1 smoke tests: package imports, CLI entry point, engine defaults."""

from __future__ import annotations

import subprocess
import sys


def test_subpackages_importable() -> None:
    import cli
    import engine
    import server

    assert cli is not None
    assert engine is not None
    assert server is not None


def test_engine_defaults_are_frozen() -> None:
    from engine.settings import EngineDefaults

    defaults = EngineDefaults()
    assert defaults.position_limit == 50
    assert defaults.matcher_name == "depth_only"


def test_engine_error_hierarchy() -> None:
    from engine.errors import (
        InvalidMarketDataError,
        MatcherError,
        ProsperityError,
        SimulationError,
        StrategyLoadError,
    )

    for err_cls in (
        InvalidMarketDataError,
        MatcherError,
        SimulationError,
        StrategyLoadError,
    ):
        assert issubclass(err_cls, ProsperityError)


def test_cli_version_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "0.1.0" in result.stdout
