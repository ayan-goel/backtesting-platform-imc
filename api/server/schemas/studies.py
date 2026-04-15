"""Pydantic models for the `studies` collection and /studies router."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StudyStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
Direction = Literal["maximize", "minimize"]


class IntSpec(BaseModel):
    type: Literal["int"] = "int"
    low: int
    high: int
    step: int = 1
    log: bool = False


class FloatSpec(BaseModel):
    type: Literal["float"] = "float"
    low: float
    high: float
    step: float | None = None
    log: bool = False


class CategoricalSpec(BaseModel):
    type: Literal["categorical"] = "categorical"
    choices: list[str | int | float] = Field(min_length=1)


ParamSpec = Annotated[
    IntSpec | FloatSpec | CategoricalSpec,
    Field(discriminator="type"),
]

SearchSpace = dict[str, ParamSpec]


class StudyCreateRequest(BaseModel):
    strategy_id: str = Field(description="ID of an uploaded strategy. See POST /strategies.")
    round: int
    day: int
    matcher: str = "imc"
    trade_matching_mode: str = "all"
    position_limit: int = 50
    space: dict[str, Any] = Field(
        description="Search-space map. Each value is a ParamSpec (int/float/categorical)."
    )
    objective: str = "pnl_total"
    direction: Direction = "maximize"
    n_trials: int = Field(default=30, ge=1, le=500)


class StudyProgress(BaseModel):
    total: int
    completed: int = 0
    failed: int = 0
    running: int = 0


class BestTrial(BaseModel):
    number: int
    value: float
    params: dict[str, Any]
    run_id: str | None = None


class StudyDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    study_id: str = Field(alias="_id")
    created_at: str
    strategy_id: str
    strategy_hash: str
    strategy_filename: str
    round: int
    day: int
    matcher: str
    trade_matching_mode: str = "all"
    position_limit: int
    space: dict[str, Any]
    objective: str
    direction: Direction
    n_trials: int
    status: StudyStatus
    started_at: str | None = None
    finished_at: str | None = None
    storage_path: str
    progress: StudyProgress
    best_trial: BestTrial | None = None


class StudyTrialSummary(BaseModel):
    trial_number: int
    status: Literal["queued", "running", "succeeded", "failed"]
    value: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    duration_ms: int | None = None
