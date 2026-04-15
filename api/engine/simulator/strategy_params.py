"""Autodetect tunable hyperparameters from a strategy source file.

Walks the AST looking for class-level `UPPER_CASE = <numeric literal>` assignments.
These are the conventional way strategies in this codebase declare their tunable
constants (e.g. `MR_WEIGHT = 0.5` on `OsmiumTrader`). For each match we return a
`TunableParam` with a default value, inferred type, and a suggested search range.

The accompanying `apply_params_to_module` function patches the matching class
attributes at runtime so that trials actually affect the simulation. That keeps
the contract symmetric: whatever the extractor can find, the runner can tune.

Conventions
-----------
- Target must be a bare `ast.Name` (not tuple unpack, not subscript).
- Name must match `UPPER_CASE_WITH_UNDERSCORES` (first char a letter).
- Value must be a `Constant` (or simple `UnaryOp(-, Constant)`) with an int or float.
- Negative number literals are accepted as `UnaryOp`.
- Multi-assign (`A = B = 1`) and annotated assigns (`A: int = 1`) are both supported.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_UPPER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

ParamType = Literal["int", "float"]


@dataclass(frozen=True, slots=True)
class TunableParam:
    name: str
    class_name: str
    default: float
    type: ParamType
    suggested_low: float
    suggested_high: float


def extract_tunable_params(source: str | Path) -> list[TunableParam]:
    """Parse a strategy file and return its detectable tunable constants.

    Accepts either a file path or raw source text. Returns an empty list if the
    file cannot be parsed or has no matching constants — this function never
    raises on a malformed strategy, it just returns nothing.
    """
    text = source.read_text() if isinstance(source, Path) else source
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    found: list[TunableParam] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            for name, value in _iter_class_assignments(stmt):
                if not _UPPER_RE.match(name):
                    continue
                numeric = _constant_number(value)
                if numeric is None:
                    continue
                if name in seen:
                    # First-seen wins. This avoids duplicate rows when the same
                    # constant is declared in a base and an override in a subclass.
                    continue
                seen.add(name)
                param_type: ParamType = "int" if isinstance(numeric, int) else "float"
                low, high = _suggest_range(numeric, param_type)
                found.append(
                    TunableParam(
                        name=name,
                        class_name=node.name,
                        default=float(numeric),
                        type=param_type,
                        suggested_low=low,
                        suggested_high=high,
                    )
                )
    return found


def apply_params_to_module(module: object, params: dict[str, object]) -> None:
    """Override matching class attributes in `module` with values from `params`.

    For every top-level class in the module whose name does not start with `_`,
    any class attribute whose UPPER_CASE name appears in `params` is replaced.
    Values are coerced to the existing attribute's type when possible so that an
    `int` tunable stays `int`. Unknown keys (those that don't match any class
    attribute) are ignored; that is expected because `params` may also include
    keys consumed via `self.params.get(...)` inside the trader's `run` method.
    """
    if not params:
        return
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        cls = getattr(module, attr_name, None)
        if not isinstance(cls, type):
            continue
        for key, value in params.items():
            if not _UPPER_RE.match(key):
                continue
            if key not in cls.__dict__:
                continue
            current = cls.__dict__[key]
            setattr(cls, key, _coerce_like(value, current))


def _iter_class_assignments(
    stmt: ast.stmt,
) -> Iterator[tuple[str, ast.expr]]:
    """Yield (name, value) pairs for every simple class-body assignment."""
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                yield target.id, stmt.value
    elif (
        isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name)
        and stmt.value is not None
    ):
        yield stmt.target.id, stmt.value


def _constant_number(value: ast.expr) -> int | float | None:
    """Return the literal numeric value of `value`, or None.

    Accepts `Constant` and single `UnaryOp(-/+, Constant)` wrappers so that
    `-10` and `+0.5` parse correctly. `bool` constants are rejected because
    they are `int` subclasses in Python but are rarely search-space-tunable.
    """
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.USub, ast.UAdd)):
        inner = _constant_number(value.operand)
        if inner is None:
            return None
        return -inner if isinstance(value.op, ast.USub) else inner
    if isinstance(value, ast.Constant):
        if isinstance(value.value, bool):
            return None
        if isinstance(value.value, (int, float)):
            return value.value
    return None


def _suggest_range(default: int | float, kind: ParamType) -> tuple[float, float]:
    """Heuristic suggested search range for a given default.

    Aim: give the user a starting range they can accept or tweak. No magic
    formula produces perfect bounds, so we prefer ranges that clearly bracket
    the default rather than hugging it.
    """
    if kind == "int":
        if default == 0:
            return (0.0, 10.0)
        if default > 0:
            return (0.0, float(max(int(default) * 2, int(default) + 1)))
        return (float(int(default) * 2), 0.0)
    # float
    if default == 0.0:
        return (0.0, 1.0)
    if 0.0 < default <= 1.0:
        return (0.0, 1.0)
    if -1.0 <= default < 0.0:
        return (-1.0, 0.0)
    span = abs(default) * 0.5
    return (default - span, default + span)


def _coerce_like(value: object, reference: object) -> object:
    """Coerce `value` so it matches `reference`'s numeric type when sensible.

    Optuna hands us `int` for int-typed params and `float` for float-typed
    params, but we want the class attribute's original type to stick when the
    two disagree (e.g. a user tunes an int constant as a float by mistake).
    """
    if isinstance(reference, bool):
        return bool(value)
    if isinstance(reference, int) and not isinstance(value, bool):
        try:
            return int(value)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return value
    if isinstance(reference, float):
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value
    return value


__all__ = ["TunableParam", "apply_params_to_module", "extract_tunable_params"]
