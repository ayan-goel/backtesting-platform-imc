"""API-layer schemas for the runs router."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    strategy_id: str = Field(description="ID of an uploaded strategy. See POST /strategies.")
    round: int
    day: int
    matcher: str = "imc"
    trade_matching_mode: str = Field(
        default="all",
        description="Trade-matching mode for imc matcher: all, worse, none. Ignored by other matchers.",
    )
    position_limit: int = Field(
        default=50,
        description="Fallback per-product limit for products not listed in rounds.json.",
    )
    params: dict[str, Any] = Field(default_factory=dict)
    # Set when this run is a trial inside an optuna study. When present,
    # execute_run skips the (strategy_hash, round, day) idempotency lookup
    # so each trial produces a distinct run doc.
    study_id: str | None = None
    trial_number: int | None = None


class RunListQuery(BaseModel):
    skip: int = 0
    limit: int = 50


class RunEventsQuery(BaseModel):
    product: str | None = None
    ts_from: int | None = None
    ts_to: int | None = None
    limit: int | None = None
    offset: int = 0
