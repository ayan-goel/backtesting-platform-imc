"""Load a `Trader` class from an arbitrary strategy file path.

Uploaded strategies import from the IMC `datamodel` module. Two styles are common:

    from datamodel import Order, TradingState
    from strategies.datamodel import Order, TradingState     # if the author keeps
                                                             # datamodel.py next to
                                                             # their strategies inside
                                                             # a `strategies/` folder

Both resolve to our bundled copy at `engine/compat/datamodel.py`. We satisfy the first
by prepending `COMPAT_DIR` to sys.path and the second by registering a synthetic
`strategies` package in sys.modules that re-exports the same module as `.datamodel`.
The platform never touches any folder outside `platform/api/`.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import importlib.util
import inspect
import sys
import types
from pathlib import Path
from typing import Any

from engine.compat import COMPAT_DIR
from engine.errors import StrategyLoadError


def load_trader(strategy_path: Path) -> Any:
    """Import a strategy file, return an instance of its `Trader` class.

    Raises StrategyLoadError if the file is missing, has no Trader class, or Trader.run
    has a wrong signature.
    """
    strategy_path = strategy_path.resolve()
    if not strategy_path.is_file():
        raise StrategyLoadError(f"strategy file not found: {strategy_path}")

    compat_str = str(COMPAT_DIR)
    added_to_path = False
    if compat_str not in sys.path:
        sys.path.insert(0, compat_str)
        added_to_path = True

    # If a stale `datamodel` module got cached (e.g. the repo's broken version was
    # imported earlier in this process), drop it so our bundled copy wins.
    if "datamodel" in sys.modules:
        existing_path = getattr(sys.modules["datamodel"], "__file__", None)
        if existing_path and Path(existing_path).resolve() != (COMPAT_DIR / "datamodel.py").resolve():
            del sys.modules["datamodel"]

    datamodel_mod = importlib.import_module("datamodel")
    injected_aliases: list[str] = []
    if "strategies" not in sys.modules:
        pkg = types.ModuleType("strategies")
        pkg.__path__ = []  # marker that makes it a package for `from strategies.X import …`
        sys.modules["strategies"] = pkg
        injected_aliases.append("strategies")
    if "strategies.datamodel" not in sys.modules:
        sys.modules["strategies.datamodel"] = datamodel_mod
        injected_aliases.append("strategies.datamodel")

    def _cleanup() -> None:
        if added_to_path:
            with contextlib.suppress(ValueError):
                sys.path.remove(compat_str)
        for name in injected_aliases:
            sys.modules.pop(name, None)

    module_name = f"_strategy_{strategy_path.stem}_{id(strategy_path):x}"
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        _cleanup()
        raise StrategyLoadError(f"could not build import spec for {strategy_path}")

    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        sys.modules.pop(module_name, None)
        raise StrategyLoadError(f"error importing {strategy_path}: {e}") from e
    finally:
        _cleanup()

    trader_cls = getattr(module, "Trader", None)
    if trader_cls is None or not inspect.isclass(trader_cls):
        raise StrategyLoadError(f"no Trader class found in {strategy_path}")

    run_method = getattr(trader_cls, "run", None)
    if run_method is None or not callable(run_method):
        raise StrategyLoadError(f"Trader in {strategy_path} has no callable `run`")

    sig = inspect.signature(run_method)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    if len(params) < 1:
        raise StrategyLoadError(
            f"Trader.run in {strategy_path} must accept a TradingState argument"
        )

    return trader_cls()


def hash_strategy_file(strategy_path: Path) -> str:
    """Return `sha256:{hex}` for the strategy file — used as part of run_id."""
    h = hashlib.sha256()
    h.update(strategy_path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def hash_strategy_bytes(content: bytes) -> str:
    """Return `sha256:{hex}` for a byte buffer (used by the upload path)."""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
