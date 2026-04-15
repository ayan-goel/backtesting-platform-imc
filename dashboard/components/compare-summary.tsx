"use client";

import { memo } from "react";
import { Card, CardHeader } from "@/components/ui/card";
import type { SummaryDelta } from "@/lib/compare";
import type { RunSummary } from "@/lib/types";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

interface Props {
  a: RunSummary;
  b: RunSummary;
  delta: SummaryDelta;
}

export const CompareSummary = memo(function CompareSummary({ a, b, delta }: Props) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <RunCard run={a} label="A" tone="buy" />
      <RunCard run={b} label="B" tone="accent" />
      <DeltaCard delta={delta} />
    </div>
  );
});

function RunCard({
  run,
  label,
  tone,
}: {
  run: RunSummary;
  label: string;
  tone: "buy" | "accent";
}) {
  const pnlTone = run.pnl_total >= 0 ? "text-buy" : "text-sell";
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              tone === "buy" ? "bg-buy" : "bg-accent"
            )}
          />
          run {label}
        </div>
      </CardHeader>
      <div className="space-y-2 font-mono text-xs">
        <Row k="strategy" v={run.strategy_path} />
        <Row k="created" v={formatTimestamp(run.created_at)} />
        <Row k="round / day" v={`r${run.round} / d${run.day}`} />
        <Row k="matcher" v={run.matcher} />
        <Row k="duration" v={`${formatInt(run.duration_ms)} ms`} />
      </div>
      <div className="mt-3 border-t border-border pt-3">
        <div className={cn("font-mono text-lg", pnlTone)}>
          {formatCurrency(run.pnl_total)}
        </div>
        <div className="mt-2 space-y-0.5">
          {Object.entries(run.pnl_by_product).map(([product, pnl]) => (
            <div
              key={product}
              className="grid grid-cols-[1fr_auto] gap-3 font-mono text-[11px] tabular-nums"
            >
              <span className="text-muted-fg">{product}</span>
              <span className={pnl >= 0 ? "text-buy" : "text-sell"}>
                {formatCurrency(pnl)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function DeltaCard({ delta }: { delta: SummaryDelta }) {
  const totalTone =
    delta.pnlTotalDelta > 0
      ? "text-buy"
      : delta.pnlTotalDelta < 0
        ? "text-sell"
        : "text-muted-fg";
  const durationTone =
    delta.durationDeltaMs > 0
      ? "text-sell"
      : delta.durationDeltaMs < 0
        ? "text-buy"
        : "text-muted-fg";
  return (
    <Card>
      <CardHeader>Δ (B − A)</CardHeader>
      <div className="space-y-2 font-mono text-xs">
        <Row
          k="duration"
          v={
            <span className={durationTone}>
              {signed(delta.durationDeltaMs)} ms
            </span>
          }
        />
      </div>
      <div className="mt-3 border-t border-border pt-3">
        <div className={cn("font-mono text-lg", totalTone)}>
          {signedCurrency(delta.pnlTotalDelta)}
        </div>
        <div className="mt-2 space-y-0.5">
          {Object.entries(delta.pnlByProductDelta).map(([product, d]) => (
            <div
              key={product}
              className="grid grid-cols-[1fr_auto] gap-3 font-mono text-[11px] tabular-nums"
            >
              <span className="text-muted-fg">{product}</span>
              <span className={d >= 0 ? "text-buy" : "text-sell"}>
                {signedCurrency(d)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-3">
      <span className="text-[10px] uppercase tracking-wider text-muted-fg">{k}</span>
      <span className="truncate text-right">{v}</span>
    </div>
  );
}

function signed(n: number): string {
  return n >= 0 ? `+${formatInt(n)}` : formatInt(n);
}

function signedCurrency(n: number): string {
  return n >= 0 ? `+${formatCurrency(n)}` : formatCurrency(n);
}
