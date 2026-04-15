"""Pydantic models for the `mc_simulations` collection and /mc router."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

McStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
PathStatus = Literal["queued", "running", "succeeded", "failed"]


# ---- Generator specs --------------------------------------------------------


class IdentitySpec(BaseModel):
    type: Literal["identity"] = "identity"


class BlockBootstrapSpec(BaseModel):
    type: Literal["block_bootstrap"] = "block_bootstrap"
    block_size: int = Field(default=50, ge=1, le=10_000)


class GbmSpec(BaseModel):
    type: Literal["gbm"] = "gbm"
    mu_scale: float = Field(default=1.0, description="Multiplier on calibrated drift.")
    sigma_scale: float = Field(default=1.0, description="Multiplier on calibrated vol.")
    starting_price_from: Literal["historical_first", "historical_last"] = "historical_first"


class OuSpec(BaseModel):
    type: Literal["ou"] = "ou"
    phi_scale: float = Field(default=1.0, description="Multiplier on calibrated reversion speed.")
    sigma_scale: float = Field(default=1.0, description="Multiplier on calibrated residual std.")


GeneratorSpec = Annotated[
    IdentitySpec | BlockBootstrapSpec | GbmSpec | OuSpec,
    Field(discriminator="type"),
]


# ---- Request / doc ----------------------------------------------------------


class McCreateRequest(BaseModel):
    strategy_id: str = Field(description="ID of an uploaded strategy. See POST /strategies.")
    round: int
    day: int
    matcher: str = "imc"
    trade_matching_mode: str = "all"
    position_limit: int = 50
    params: dict[str, Any] = Field(default_factory=dict)
    generator: GeneratorSpec = Field(
        default_factory=IdentitySpec,
        description="Synthetic market generator. Default is identity (regression anchor).",
    )
    n_paths: int = Field(default=100, ge=1, le=1000)
    seed: int = Field(default=42)
    num_workers: int = Field(default=2, ge=1, le=16)


class McPathSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    status: PathStatus = "queued"
    pnl_total: float | None = None
    pnl_by_product: dict[str, float] | None = None
    max_drawdown: float | None = None
    max_inventory_by_product: dict[str, int] | None = None
    turnover_by_product: dict[str, int] | None = None
    num_fills: int | None = None
    sharpe_intraday: float | None = None
    duration_ms: int | None = None
    error: str | None = None


class McProgress(BaseModel):
    total: int
    completed: int = 0
    failed: int = 0
    running: int = 0


class PnlQuantiles(BaseModel):
    p01: float
    p05: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float


class PnlHistogram(BaseModel):
    bin_edges: list[float]
    counts: list[int]


class PnlCurveQuantiles(BaseModel):
    ts_grid: list[int]
    p05: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]


class AggregateStats(BaseModel):
    pnl_mean: float
    pnl_std: float
    pnl_median: float
    pnl_min: float
    pnl_max: float
    pnl_quantiles: PnlQuantiles
    winrate: float
    sharpe_across_paths: float
    max_drawdown_mean: float
    max_drawdown_p05: float
    num_fills_mean: float
    pnl_histogram: PnlHistogram
    pnl_curve_quantiles: PnlCurveQuantiles | None = None


class McSimulationDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mc_id: str = Field(alias="_id")
    created_at: str
    strategy_id: str
    strategy_hash: str
    strategy_filename: str
    round: int
    day: int
    matcher: str
    trade_matching_mode: str = "all"
    position_limit: int
    params: dict[str, Any]
    generator: dict[str, Any]
    n_paths: int
    seed: int
    num_workers: int
    status: McStatus
    started_at: str | None = None
    finished_at: str | None = None
    progress: McProgress
    paths: list[McPathSummary] = Field(default_factory=list)
    aggregate: AggregateStats | None = None
    reference_run_id: str | None = None
    error: str | None = None
