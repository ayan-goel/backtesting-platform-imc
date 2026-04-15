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
