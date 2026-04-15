"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { McFanChart } from "@/components/mc/mc-fan-chart";
import { McHistogram } from "@/components/mc/mc-histogram";
import { McMetricsPanel } from "@/components/mc/mc-metrics-panel";
import { StatusBadge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { McSimulation } from "@/lib/types";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

export function McDetailView({ mc }: { mc: McSimulation }) {
  const router = useRouter();
  const [polling, setPolling] = useState(
    mc.status === "queued" || mc.status === "running"
  );

  useEffect(() => {
    if (!polling) return;
    const id = setInterval(() => {
      router.refresh();
    }, 2000);
    return () => clearInterval(id);
  }, [polling, router]);

  useEffect(() => {
    if (mc.status !== "queued" && mc.status !== "running") {
      setPolling(false);
    }
  }, [mc.status]);

  const sortedPaths = [...mc.paths].sort(
    (a, b) => (b.pnl_total ?? 0) - (a.pnl_total ?? 0)
  );
  const top5 = sortedPaths.slice(0, 5);
  const bottom5 = sortedPaths.slice(-5).reverse();

  const curve = mc.aggregate?.pnl_curve_quantiles ?? null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link
          href="/mc"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to monte carlo
        </Link>
        <StatusBadge status={mc.status} />
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card tone="subtle">
          <CardHeader>strategy</CardHeader>
          <div className="font-mono text-sm text-fg">{mc.strategy_filename}</div>
          <div className="mt-1 text-xs text-muted-fg">
            r{mc.round} / d{mc.day} · {mc.matcher}
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>created</CardHeader>
          <div className="font-mono text-sm text-fg">
            {formatTimestamp(mc.created_at)}
          </div>
          <div className="mt-1 text-xs text-muted-fg">
            seed {mc.seed} · {mc.num_workers}w
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>generator</CardHeader>
          <div className="font-mono text-sm text-fg">{mc.generator.type}</div>
          <div className="mt-1 text-xs text-muted-fg">
            {JSON.stringify(
              Object.fromEntries(
                Object.entries(mc.generator).filter(([k]) => k !== "type")
              )
            )}
          </div>
        </Card>
        <Card tone="subtle">
          <CardHeader>progress</CardHeader>
          <div className="font-mono text-lg text-fg tabular-nums">
            {mc.progress.completed + mc.progress.failed} / {mc.progress.total}
          </div>
          {mc.progress.failed > 0 && (
            <div className="mt-1 text-xs text-sell">
              {mc.progress.failed} failed
            </div>
          )}
          {mc.progress.running > 0 && (
            <div className="mt-1 text-xs text-muted-fg">
              {mc.progress.running} running
            </div>
          )}
        </Card>
      </div>

      {mc.error && (
        <Card tone="subtle">
          <CardHeader>error</CardHeader>
          <div className="font-mono text-xs text-sell">{mc.error}</div>
        </Card>
      )}

      {mc.aggregate ? (
        <>
          <McMetricsPanel aggregate={mc.aggregate} referenceRunId={mc.reference_run_id} />
          <div className="grid gap-6 lg:grid-cols-2">
            <Card tone="subtle">
              <CardHeader>pnl distribution</CardHeader>
              <McHistogram histogram={mc.aggregate.pnl_histogram} />
            </Card>
            <Card tone="subtle">
              <CardHeader>equity curve fan</CardHeader>
              {curve ? (
                <McFanChart
                  curve={curve}
                  referenceRunId={mc.reference_run_id}
                />
              ) : (
                <div className="text-xs text-muted-fg">
                  curve stats not yet available
                </div>
              )}
            </Card>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card tone="subtle">
              <CardHeader>top 5 paths</CardHeader>
              <PathsTable paths={top5} />
            </Card>
            <Card tone="subtle">
              <CardHeader>bottom 5 paths</CardHeader>
              <PathsTable paths={bottom5} />
            </Card>
          </div>
        </>
      ) : (
        <Card tone="subtle">
          <CardHeader>awaiting aggregation</CardHeader>
          <div className="text-sm text-muted-fg">
            {mc.status === "succeeded"
              ? "no aggregate stats yet — refresh shortly."
              : "aggregate stats will appear once all paths complete."}
          </div>
        </Card>
      )}
    </div>
  );
}

function PathsTable({ paths }: { paths: McSimulation["paths"] }) {
  if (paths.length === 0) {
    return <div className="text-xs text-muted-fg">no completed paths</div>;
  }
  return (
    <Table>
      <Thead>
        <Tr>
          <Th className="text-right">#</Th>
          <Th className="text-right">pnl</Th>
          <Th className="text-right">max dd</Th>
          <Th className="text-right">fills</Th>
        </Tr>
      </Thead>
      <Tbody>
        {paths.map((p) => (
          <Tr key={p.index}>
            <Td className="text-right font-mono text-xs text-muted-fg">
              {p.index}
            </Td>
            <Td
              className={cn(
                "text-right font-mono tabular-nums",
                (p.pnl_total ?? 0) >= 0 ? "text-buy" : "text-sell"
              )}
            >
              {p.pnl_total === null ? "—" : formatCurrency(p.pnl_total)}
            </Td>
            <Td className="text-right font-mono text-xs text-muted-fg tabular-nums">
              {p.max_drawdown === null ? "—" : formatCurrency(p.max_drawdown)}
            </Td>
            <Td className="text-right font-mono text-xs text-muted-fg tabular-nums">
              {p.num_fills === null ? "—" : formatInt(p.num_fills)}
            </Td>
          </Tr>
        ))}
      </Tbody>
    </Table>
  );
}
