"""Load per-round position limits from `rounds.json`.

Each round maps product symbol → max absolute position. Unknown rounds return
an empty dict; unknown products inside a known round fall back to whatever
default the caller supplies. Mirrors the `LIMITS[product]` table at
`prosperity4bt/data.py` in `prosperity4btx`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "rounds.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, dict[str, int]]:
    if not _CONFIG_PATH.is_file():
        return {}
    data: dict[str, dict[str, int]] = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return data


def load_round_limits(round_num: int) -> dict[str, int]:
    """Return {symbol: limit} for `round_num`, or {} if unconfigured."""
    return dict(_load_raw().get(f"round_{round_num}", {}))


def resolve_limits(
    round_num: int,
    products: tuple[str, ...] | list[str],
    default_limit: int,
) -> dict[str, int]:
    """Resolve per-product limits: config table first, then `default_limit` fallback."""
    configured = load_round_limits(round_num)
    return {p: configured.get(p, default_limit) for p in products}


def reload_config() -> None:
    """Force a re-read of `rounds.json` on next access. For tests / hot-reload."""
    _load_raw.cache_clear()
