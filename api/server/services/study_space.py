"""Search-space helpers for optuna studies.

Pure functions: validation + optuna.Trial → concrete params dict. No DB, no
storage concerns. `parse_space` accepts the raw dict from a StudyCreateRequest
and returns the discriminated-union models for downstream use.
"""

from __future__ import annotations

from typing import Any

import optuna
from pydantic import TypeAdapter, ValidationError

from server.schemas.studies import (
    CategoricalSpec,
    FloatSpec,
    IntSpec,
    ParamSpec,
)

_ParamSpecAdapter: TypeAdapter[ParamSpec] = TypeAdapter(ParamSpec)


class SpaceValidationError(ValueError):
    """Raised when a search space is malformed."""


def parse_space(raw: dict[str, Any]) -> dict[str, ParamSpec]:
    """Turn a raw `{name: {type, ...}}` dict into validated ParamSpec models."""
    if not raw:
        raise SpaceValidationError("search space must not be empty")
    parsed: dict[str, ParamSpec] = {}
    for name, spec_raw in raw.items():
        if not isinstance(spec_raw, dict):
            raise SpaceValidationError(f"spec for {name!r} must be an object, got {type(spec_raw).__name__}")
        try:
            parsed[name] = _ParamSpecAdapter.validate_python(spec_raw)
        except ValidationError as e:
            raise SpaceValidationError(f"invalid spec for {name!r}: {e}") from e
    validate_space(parsed)
    return parsed


def validate_space(space: dict[str, ParamSpec]) -> None:
    """Reject empty/inverted/zero-choice specs."""
    if not space:
        raise SpaceValidationError("search space must not be empty")
    for name, spec in space.items():
        if isinstance(spec, IntSpec):
            if spec.low > spec.high:
                raise SpaceValidationError(f"{name}: int low ({spec.low}) > high ({spec.high})")
            if spec.step <= 0:
                raise SpaceValidationError(f"{name}: int step must be > 0")
        elif isinstance(spec, FloatSpec):
            if spec.low > spec.high:
                raise SpaceValidationError(f"{name}: float low ({spec.low}) > high ({spec.high})")
            if spec.step is not None and spec.step <= 0:
                raise SpaceValidationError(f"{name}: float step must be > 0 if set")
        elif isinstance(spec, CategoricalSpec):
            if not spec.choices:
                raise SpaceValidationError(f"{name}: categorical choices must not be empty")


def apply_space(
    trial: optuna.Trial, space: dict[str, ParamSpec]
) -> dict[str, Any]:
    """Ask the trial for a concrete value per param. Dispatches on spec type."""
    out: dict[str, Any] = {}
    for name, spec in space.items():
        if isinstance(spec, IntSpec):
            out[name] = trial.suggest_int(
                name, spec.low, spec.high, step=spec.step, log=spec.log
            )
        elif isinstance(spec, FloatSpec):
            out[name] = trial.suggest_float(
                name, spec.low, spec.high, step=spec.step, log=spec.log
            )
        elif isinstance(spec, CategoricalSpec):
            out[name] = trial.suggest_categorical(name, spec.choices)
    return out
