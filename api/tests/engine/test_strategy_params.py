"""Unit tests for engine.simulator.strategy_params.

Covers the AST extractor (what counts as tunable) and the runtime patcher (class
attributes get overridden when matching keys are in `params`).
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from engine.simulator.strategy_params import (
    TunableParam,
    apply_params_to_module,
    extract_tunable_params,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _names(params: list[TunableParam]) -> set[str]:
    return {p.name for p in params}


def test_extracts_upper_case_numeric_class_constants() -> None:
    src = """
class Foo:
    A_INT = 5
    A_FLOAT = 0.5
    NEG = -3
    mixed_case = 1
    _underscored = 2
    CamelCase = 3
    STRING_CONST = "hi"
    BOOL_CONST = True
"""
    params = extract_tunable_params(src)
    assert _names(params) == {"A_INT", "A_FLOAT", "NEG"}
    by_name = {p.name: p for p in params}
    assert by_name["A_INT"].type == "int"
    assert by_name["A_INT"].default == 5
    assert by_name["A_FLOAT"].type == "float"
    assert by_name["A_FLOAT"].default == 0.5
    assert by_name["NEG"].default == -3


def test_supports_annotated_class_assignments() -> None:
    src = """
class Foo:
    MR_WEIGHT: float = 0.5
    SOFT_LIMIT: int = 40
"""
    params = extract_tunable_params(src)
    assert _names(params) == {"MR_WEIGHT", "SOFT_LIMIT"}


def test_ignores_module_level_constants() -> None:
    src = """
MODULE_CONST = 42

class Foo:
    INNER = 1
"""
    params = extract_tunable_params(src)
    assert _names(params) == {"INNER"}


def test_first_declaration_wins_across_classes() -> None:
    """A constant defined in a base class and overridden on a subclass should
    appear once — not once per class."""
    src = """
class Base:
    SOFT_LIMIT = 40

class Sub(Base):
    SOFT_LIMIT = 20
"""
    params = extract_tunable_params(src)
    assert _names(params) == {"SOFT_LIMIT"}
    assert params[0].default == 40  # Base wins (first-seen)
    assert params[0].class_name == "Base"


def test_suggested_range_int_positive() -> None:
    src = "class Foo:\n    N = 10\n"
    params = extract_tunable_params(src)
    assert params[0].suggested_low == 0.0
    assert params[0].suggested_high == 20.0


def test_suggested_range_int_zero() -> None:
    src = "class Foo:\n    N = 0\n"
    params = extract_tunable_params(src)
    assert params[0].suggested_low == 0.0
    assert params[0].suggested_high == 10.0


def test_suggested_range_int_small_positive_has_non_degenerate_high() -> None:
    """For N=1, 2*N is still 2 — check we don't end up with [0, 1] which loses the default."""
    src = "class Foo:\n    N = 1\n"
    params = extract_tunable_params(src)
    assert params[0].suggested_low == 0.0
    assert params[0].suggested_high >= 2.0


def test_suggested_range_float_unit_interval() -> None:
    src = "class Foo:\n    W = 0.5\n"
    params = extract_tunable_params(src)
    assert params[0].suggested_low == 0.0
    assert params[0].suggested_high == 1.0


def test_suggested_range_float_large() -> None:
    src = "class Foo:\n    W = 10.0\n"
    params = extract_tunable_params(src)
    assert params[0].suggested_low == 5.0
    assert params[0].suggested_high == 15.0


def test_syntax_error_returns_empty_list() -> None:
    src = "class Foo:\n    A = \n"
    assert extract_tunable_params(src) == []


def test_extracts_from_real_strategy_file() -> None:
    """Integration: runs against the actual round1.py in the repo."""
    target = REPO_ROOT / "strategies" / "ayan" / "round1.py"
    if not target.is_file():
        pytest.skip("round1.py not present in repo")
    params = extract_tunable_params(target)
    names = _names(params)
    # OsmiumTrader: MR_WEIGHT, SKEW_PER_UNIT  |  PepperTrader: MR_WEIGHT, SKEW_PER_UNIT, SOFT_LIMIT
    # MR_WEIGHT and SKEW_PER_UNIT dedupe via first-seen, so final set:
    assert "MR_WEIGHT" in names
    assert "SKEW_PER_UNIT" in names
    assert "SOFT_LIMIT" in names
    by_name = {p.name: p for p in params}
    assert by_name["MR_WEIGHT"].default == 0.5
    assert by_name["MR_WEIGHT"].type == "float"
    assert by_name["SOFT_LIMIT"].default == 40
    assert by_name["SOFT_LIMIT"].type == "int"


# ── apply_params_to_module ────────────────────────────────────────────────────


def _module_with_classes() -> types.ModuleType:
    mod = types.ModuleType("fake_strategy")
    code = """
class Foo:
    MR_WEIGHT = 0.5
    SOFT_LIMIT = 40
    OTHER = 1

class Bar:
    MR_WEIGHT = 0.9
"""
    exec(code, mod.__dict__)
    return mod


def test_apply_params_overrides_matching_class_attributes() -> None:
    mod = _module_with_classes()
    apply_params_to_module(mod, {"MR_WEIGHT": 0.2, "SOFT_LIMIT": 30})
    assert mod.__dict__["Foo"].MR_WEIGHT == 0.2
    assert mod.__dict__["Foo"].SOFT_LIMIT == 30
    assert mod.__dict__["Foo"].OTHER == 1
    assert mod.__dict__["Bar"].MR_WEIGHT == 0.2  # hit both classes


def test_apply_params_preserves_int_type_when_reference_is_int() -> None:
    """Optuna hands us float sometimes; class attribute original type should stick."""
    mod = _module_with_classes()
    apply_params_to_module(mod, {"SOFT_LIMIT": 37.8})
    assert mod.__dict__["Foo"].SOFT_LIMIT == 37
    assert isinstance(mod.__dict__["Foo"].SOFT_LIMIT, int)


def test_apply_params_ignores_unknown_keys() -> None:
    mod = _module_with_classes()
    apply_params_to_module(mod, {"NOT_A_CONST": 99, "lowercase_key": 1})
    # No exceptions, no mutations to class attributes.
    assert mod.__dict__["Foo"].MR_WEIGHT == 0.5
    assert mod.__dict__["Foo"].SOFT_LIMIT == 40


def test_apply_params_noop_on_empty_dict() -> None:
    mod = _module_with_classes()
    apply_params_to_module(mod, {})
    assert mod.__dict__["Foo"].MR_WEIGHT == 0.5
