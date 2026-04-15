import { Card, CardHeader } from "@/components/ui/card";
import type { McAggregateStats } from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";

interface Props {
  aggregate: McAggregateStats;
  referenceRunId?: string | null;
}

export function McMetricsPanel({ aggregate }: Props) {
  const q = aggregate.pnl_quantiles;
  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Metric
        label="mean pnl"
        value={formatCurrency(aggregate.pnl_mean)}
        tone={aggregate.pnl_mean >= 0 ? "buy" : "sell"}
      />
      <Metric
        label="median pnl"
        value={formatCurrency(aggregate.pnl_median)}
        tone={aggregate.pnl_median >= 0 ? "buy" : "sell"}
      />
      <Metric label="std" value={formatCurrency(aggregate.pnl_std)} />
      <Metric
        label="winrate"
        value={`${(aggregate.winrate * 100).toFixed(1)}%`}
        tone={aggregate.winrate >= 0.5 ? "buy" : "sell"}
      />
      <Metric
        label="p05"
        value={formatCurrency(q.p05)}
        tone={q.p05 >= 0 ? "buy" : "sell"}
      />
      <Metric label="p95" value={formatCurrency(q.p95)} />
      <Metric
        label="sharpe"
        value={aggregate.sharpe_across_paths.toFixed(2)}
      />
      <Metric
        label="mean max dd"
        value={formatCurrency(aggregate.max_drawdown_mean)}
        tone="sell"
      />
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "buy" | "sell";
}) {
  return (
    <Card tone="subtle">
      <CardHeader>{label}</CardHeader>
      <div
        className={cn(
          "font-mono text-xl font-semibold tabular-nums",
          tone === "buy" && "text-buy",
          tone === "sell" && "text-sell"
        )}
      >
        {value}
      </div>
    </Card>
  );
}
