// Types mirrored from platform/api/schemas and engine.metrics.summary.

export interface RunSummary {
  _id: string;
  created_at: string;
  strategy_path: string;
  strategy_hash: string;
  round: number;
  day: number;
  matcher: string;
  params: Record<string, unknown>;
  engine_version: string;
  status: "queued" | "running" | "succeeded" | "failed";
  duration_ms: number;
  pnl_total: number;
  pnl_by_product: Record<string, number>;
  max_inventory_by_product: Record<string, number>;
  turnover_by_product: Record<string, number>;
  num_events: number;
  artifact_dir: string;
  error: string | null;
}

export interface Strategy {
  _id: string;
  filename: string;
  stem: string;
  sha256: string;
  uploaded_at: string;
  size_bytes: number;
  storage_subpath: string;
}

export interface Dataset {
  _id: string;
  round: number;
  day: number;
  uploaded_at: string;
  products: string[];
  num_timestamps: number;
  prices_filename: string;
  trades_filename: string;
  prices_bytes: number;
  trades_bytes: number;
}

export interface BatchTask {
  round: number;
  day: number;
  status: "queued" | "running" | "succeeded" | "failed";
  run_id: string | null;
  error: string | null;
  duration_ms: number | null;
  pnl_total: number | null;
}

export interface BatchProgress {
  total: number;
  completed: number;
  failed: number;
}

export interface Batch {
  _id: string;
  created_at: string;
  strategy_id: string;
  strategy_hash: string;
  strategy_filename: string;
  matcher: string;
  position_limit: number;
  params: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed";
  started_at: string | null;
  finished_at: string | null;
  tasks: BatchTask[];
  progress: BatchProgress;
}

export type ParamSpec =
  | { type: "int"; low: number; high: number; step?: number; log?: boolean }
  | { type: "float"; low: number; high: number; step?: number | null; log?: boolean }
  | { type: "categorical"; choices: (string | number)[] };

export type SearchSpace = Record<string, ParamSpec>;

export interface StudyProgress {
  total: number;
  completed: number;
  failed: number;
  running: number;
}

export interface BestTrial {
  number: number;
  value: number;
  params: Record<string, unknown>;
  run_id: string | null;
}

export interface Study {
  _id: string;
  created_at: string;
  strategy_id: string;
  strategy_hash: string;
  strategy_filename: string;
  round: number;
  day: number;
  matcher: string;
  position_limit: number;
  space: SearchSpace;
  objective: string;
  direction: "maximize" | "minimize";
  n_trials: number;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  started_at: string | null;
  finished_at: string | null;
  storage_path: string;
  progress: StudyProgress;
  best_trial: BestTrial | null;
}

export interface StudyTrialSummary {
  trial_number: number;
  status: "queued" | "running" | "succeeded" | "failed";
  value: number | null;
  params: Record<string, unknown>;
  run_id: string | null;
  duration_ms: number | null;
}

// ---- Monte Carlo ------------------------------------------------------------

export type McGeneratorSpec =
  | { type: "identity" }
  | { type: "block_bootstrap"; block_size: number }
  | {
      type: "gbm";
      mu_scale: number;
      sigma_scale: number;
      starting_price_from: "historical_first" | "historical_last";
    }
  | { type: "ou"; phi_scale: number; sigma_scale: number };

export interface McPathSummary {
  index: number;
  status: "queued" | "running" | "succeeded" | "failed";
  pnl_total: number | null;
  pnl_by_product: Record<string, number> | null;
  max_drawdown: number | null;
  max_inventory_by_product: Record<string, number> | null;
  turnover_by_product: Record<string, number> | null;
  num_fills: number | null;
  sharpe_intraday: number | null;
  duration_ms: number | null;
  error: string | null;
}

export interface McProgress {
  total: number;
  completed: number;
  failed: number;
  running: number;
}

export interface PnlQuantiles {
  p01: number;
  p05: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
  p99: number;
}

export interface PnlHistogram {
  bin_edges: number[];
  counts: number[];
}

export interface PnlCurveQuantiles {
  ts_grid: number[];
  p05: number[];
  p25: number[];
  p50: number[];
  p75: number[];
  p95: number[];
}

export interface McAggregateStats {
  pnl_mean: number;
  pnl_std: number;
  pnl_median: number;
  pnl_min: number;
  pnl_max: number;
  pnl_quantiles: PnlQuantiles;
  winrate: number;
  sharpe_across_paths: number;
  max_drawdown_mean: number;
  max_drawdown_p05: number;
  num_fills_mean: number;
  pnl_histogram: PnlHistogram;
  pnl_curve_quantiles: PnlCurveQuantiles | null;
}

export interface McSimulation {
  _id: string;
  created_at: string;
  strategy_id: string;
  strategy_hash: string;
  strategy_filename: string;
  round: number;
  day: number;
  matcher: string;
  trade_matching_mode: string;
  position_limit: number;
  params: Record<string, unknown>;
  generator: McGeneratorSpec;
  n_paths: number;
  seed: number;
  num_workers: number;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  started_at: string | null;
  finished_at: string | null;
  progress: McProgress;
  paths: McPathSummary[];
  aggregate: McAggregateStats | null;
  reference_run_id: string | null;
  error: string | null;
}

export interface EventRecord {
  run_id: string;
  ts: number;
  product: string;
  state: {
    order_depth: {
      buy: Record<string, number>;
      sell: Record<string, number>;
    };
    position: number;
    market_trades: Array<{
      price: number;
      qty: number;
      buyer: string | null;
      seller: string | null;
    }>;
  };
  actions: {
    orders: Array<{ price: number; qty: number }>;
  };
  fills: Array<{ price: number; qty: number; source: string }>;
  pnl: { cash: number; mark: number; total: number };
  debug: Record<string, unknown>;
}
