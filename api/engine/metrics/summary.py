"""Run summary builder — produces the MongoDB document shape from SPEC.md §6."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunSummary(BaseModel):
    """Summary document written to the `runs` MongoDB collection (and returned by the API)."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="_id")
    created_at: str
    strategy_path: str
    strategy_hash: str
    round: int
    day: int
    matcher: str
    params: dict[str, Any]
    engine_version: str
    status: str  # queued | running | succeeded | failed
    duration_ms: int
    pnl_total: float
    pnl_by_product: dict[str, float]
    max_inventory_by_product: dict[str, int]
    turnover_by_product: dict[str, int]
    num_events: int
    artifact_dir: str
    error: str | None = None


def build_summary(
    *,
    run_id: str,
    strategy_path: str,
    strategy_hash: str,
    round_num: int,
    day: int,
    matcher: str,
    params: dict[str, Any],
    engine_version: str,
    duration_ms: int,
    pnl_total: float,
    pnl_by_product: dict[str, float],
    max_inventory_by_product: dict[str, int],
    turnover_by_product: dict[str, int],
    num_events: int,
    artifact_dir: str,
    status: str = "succeeded",
    error: str | None = None,
) -> RunSummary:
    return RunSummary(
        _id=run_id,
        created_at=datetime.now(UTC).isoformat(),
        strategy_path=strategy_path,
        strategy_hash=strategy_hash,
        round=round_num,
        day=day,
        matcher=matcher,
        params=params,
        engine_version=engine_version,
        status=status,
        duration_ms=duration_ms,
        pnl_total=pnl_total,
        pnl_by_product=pnl_by_product,
        max_inventory_by_product=max_inventory_by_product,
        turnover_by_product=turnover_by_product,
        num_events=num_events,
        artifact_dir=artifact_dir,
        error=error,
    )
