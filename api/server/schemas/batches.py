"""Pydantic models for the `batches` collection and /batches router."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BatchStatus = Literal["queued", "running", "succeeded", "failed"]
TaskStatus = Literal["queued", "running", "succeeded", "failed"]


class DatasetKey(BaseModel):
    round: int
    day: int


class BatchCreateRequest(BaseModel):
    strategy_id: str = Field(description="ID of an uploaded strategy. See POST /strategies.")
    datasets: list[DatasetKey] = Field(
        min_length=1, description="(round, day) pairs to run this strategy against."
    )
    matcher: str = "imc"
    trade_matching_mode: str = "all"
    position_limit: int = 50
    params: dict[str, Any] = Field(default_factory=dict)


class BatchTaskDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    round: int
    day: int
    status: TaskStatus = "queued"
    run_id: str | None = None
    error: str | None = None
    duration_ms: int | None = None
    pnl_total: float | None = None


class BatchProgress(BaseModel):
    total: int
    completed: int = 0
    failed: int = 0


class BatchDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    batch_id: str = Field(alias="_id")
    created_at: str
    strategy_id: str
    strategy_hash: str
    strategy_filename: str
    matcher: str
    trade_matching_mode: str = "all"
    position_limit: int
    params: dict[str, Any]
    status: BatchStatus
    started_at: str | None = None
    finished_at: str | None = None
    tasks: list[BatchTaskDoc]
    progress: BatchProgress
