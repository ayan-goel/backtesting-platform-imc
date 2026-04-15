"""O2 tests: search-space parsing, validation, and optuna sampler dispatch."""

from __future__ import annotations

from typing import Any

import optuna
import pytest

from server.schemas.studies import CategoricalSpec, FloatSpec, IntSpec
from server.services.study_space import (
    SpaceValidationError,
    apply_space,
    parse_space,
    validate_space,
)


def _one_trial_params(space: dict[str, Any]) -> dict[str, Any]:
    """Run a single trial against an in-memory optuna study and return params."""
    study = optuna.create_study(direction="maximize")
    captured: dict[str, Any] = {}

    def objective(trial: optuna.Trial) -> float:
        captured.update(apply_space(trial, space))
        return 0.0

    study.optimize(objective, n_trials=1)
    return captured


def test_parse_space_valid_int() -> None:
    parsed = parse_space({"edge": {"type": "int", "low": 0, "high": 5}})
    assert isinstance(parsed["edge"], IntSpec)
    assert parsed["edge"].low == 0 and parsed["edge"].high == 5


def test_parse_space_valid_float() -> None:
    parsed = parse_space(
        {"aggro": {"type": "float", "low": 0.0, "high": 1.0, "log": False}}
    )
    assert isinstance(parsed["aggro"], FloatSpec)


def test_parse_space_valid_categorical() -> None:
    parsed = parse_space({"mode": {"type": "categorical", "choices": ["mm", "taker"]}})
    assert isinstance(parsed["mode"], CategoricalSpec)
    assert parsed["mode"].choices == ["mm", "taker"]


def test_parse_space_empty_raises() -> None:
    with pytest.raises(SpaceValidationError, match="must not be empty"):
        parse_space({})


def test_parse_space_unknown_type_raises() -> None:
    with pytest.raises(SpaceValidationError):
        parse_space({"bad": {"type": "bool", "low": 0, "high": 1}})


def test_parse_space_non_dict_spec_raises() -> None:
    with pytest.raises(SpaceValidationError, match="must be an object"):
        parse_space({"bad": "not a dict"})


def test_validate_space_rejects_inverted_int() -> None:
    space = {"x": IntSpec(low=5, high=2)}
    with pytest.raises(SpaceValidationError, match="low"):
        validate_space(space)


def test_validate_space_rejects_inverted_float() -> None:
    space = {"x": FloatSpec(low=1.0, high=0.0)}
    with pytest.raises(SpaceValidationError, match="low"):
        validate_space(space)


def test_validate_space_rejects_zero_step() -> None:
    space = {"x": IntSpec(low=0, high=10, step=0)}
    with pytest.raises(SpaceValidationError, match="step"):
        validate_space(space)


def test_apply_space_int_within_bounds() -> None:
    space = parse_space({"edge": {"type": "int", "low": 0, "high": 5}})
    params = _one_trial_params(space)
    assert 0 <= params["edge"] <= 5


def test_apply_space_float_within_bounds() -> None:
    space = parse_space({"aggro": {"type": "float", "low": 0.0, "high": 1.0}})
    params = _one_trial_params(space)
    assert 0.0 <= params["aggro"] <= 1.0


def test_apply_space_categorical_picks_choice() -> None:
    space = parse_space({"mode": {"type": "categorical", "choices": ["mm", "taker"]}})
    params = _one_trial_params(space)
    assert params["mode"] in {"mm", "taker"}


def test_apply_space_multi_param_all_populated() -> None:
    space = parse_space(
        {
            "edge": {"type": "int", "low": 0, "high": 3},
            "aggro": {"type": "float", "low": 0.0, "high": 1.0},
            "mode": {"type": "categorical", "choices": ["mm", "taker"]},
        }
    )
    params = _one_trial_params(space)
    assert set(params.keys()) == {"edge", "aggro", "mode"}
