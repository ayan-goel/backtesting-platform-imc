import { NuqsAdapter } from "nuqs/adapters/next/app";
import Link from "next/link";
import { RunDetailActions } from "@/components/run-detail-actions";
import { StatusBadge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorCard } from "@/components/ui/error-card";
import { ReplayView } from "@/components/replay/replay-view";
import { getRunSummary } from "@/lib/api";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: runIdRaw } = await params;
  const runId = decodeURIComponent(runIdRaw);

  let summary;
  try {
    summary = await getRunSummary(runId);
  } catch {
    return (
      <div className="space-y-4">
        <Link
          href="/"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to runs
        </Link>
        <ErrorCard title="could not load run">
          <code className="font-mono">{runId}</code>
        </ErrorCard>
      </div>
    );
  }

  const products = Object.keys(summary.pnl_by_product);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to runs
        </Link>
        <RunDetailActions runId={runId} />
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card tone="subtle">
          <CardHeader>strategy</CardHeader>
          <div className="font-mono text-sm text-fg">{summary.strategy_path}</div>
          <div className="mt-1 text-xs text-muted-fg">
            r{summary.round} / d{summary.day} · {summary.matcher}
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>created</CardHeader>
          <div className="font-mono text-sm text-fg">
            {formatTimestamp(summary.created_at)}
          </div>
          <div className="mt-1 text-xs text-muted-fg">
            {formatInt(summary.duration_ms)} ms · {formatInt(summary.num_events)} events
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>pnl total</CardHeader>
          <div
            className={cn(
              "font-mono text-xl font-semibold tabular-nums",
              summary.pnl_total >= 0 ? "text-buy" : "text-sell"
            )}
          >
            {formatCurrency(summary.pnl_total)}
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>status</CardHeader>
          <StatusBadge status={summary.status} />
          {summary.error && (
            <div className="mt-2 text-xs text-sell">{summary.error}</div>
          )}
        </Card>
      </div>

      <NuqsAdapter>
        <ReplayView
          runId={runId}
          products={products}
          expectedNumEvents={summary.num_events}
          finalPnlByProduct={summary.pnl_by_product}
        />
      </NuqsAdapter>
    </div>
  );
}
