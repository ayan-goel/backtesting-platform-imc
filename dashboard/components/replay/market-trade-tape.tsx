"use client";

import { memo } from "react";
import { Card, CardHeader } from "@/components/ui/card";
import type { MarketTapeRow } from "@/lib/replay";
import { windowRows } from "@/lib/replay";
import { cn } from "@/lib/utils";

interface MarketTradeTapeProps {
  rows: readonly MarketTapeRow[];
  currentTs: number;
  windowSize?: number;
}

export const MarketTradeTape = memo(function MarketTradeTape({
  rows,
  currentTs,
  windowSize = 20,
}: MarketTradeTapeProps) {
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>market trades</CardHeader>
        <div className="text-sm text-muted-fg">no market trades in this run</div>
      </Card>
    );
  }

  const { slice, highlightIndex } = windowRows(rows, currentTs, windowSize);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between">
          <span>market trades</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-fg">
            {rows.length} total
          </span>
        </div>
      </CardHeader>
      <div className="grid grid-cols-[auto_auto_auto_auto_1fr] gap-x-3 px-1 text-[10px] uppercase tracking-wider text-muted-fg">
        <span>ts</span>
        <span>symbol</span>
        <span className="text-right">price</span>
        <span className="text-right">qty</span>
        <span>counterparties</span>
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-xs tabular-nums">
        {slice.map((row, i) => (
          <TapeRow
            key={`${row.ts}-${row.symbol}-${row.price}-${row.qty}-${i}`}
            row={row}
            highlighted={i === highlightIndex}
          />
        ))}
      </div>
    </Card>
  );
});

function TapeRow({ row, highlighted }: { row: MarketTapeRow; highlighted: boolean }) {
  return (
    <div
      aria-current={highlighted || undefined}
      className={cn(
        "grid grid-cols-[auto_auto_auto_auto_1fr] gap-x-3 rounded px-1 py-0.5",
        highlighted && "bg-accent/10 text-fg"
      )}
    >
      <span className="text-muted-fg">{row.ts}</span>
      <span>{row.symbol}</span>
      <span className="text-right">{row.price}</span>
      <span className="text-right">{row.qty}</span>
      <span className="truncate text-muted-fg">
        {row.buyer ?? "?"} → {row.seller ?? "?"}
      </span>
    </div>
  );
}
