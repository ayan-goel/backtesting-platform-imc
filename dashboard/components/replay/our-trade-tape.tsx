"use client";

import { memo } from "react";
import { Card, CardHeader } from "@/components/ui/card";
import type { OurTapeRow } from "@/lib/replay";
import { windowRows } from "@/lib/replay";
import { cn } from "@/lib/utils";

interface OurTradeTapeProps {
  rows: readonly OurTapeRow[];
  currentTs: number;
  windowSize?: number;
}

export const OurTradeTape = memo(function OurTradeTape({
  rows,
  currentTs,
  windowSize = 20,
}: OurTradeTapeProps) {
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>our fills</CardHeader>
        <div className="text-sm text-muted-fg">no fills in this run</div>
      </Card>
    );
  }

  const { slice, highlightIndex } = windowRows(rows, currentTs, windowSize);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between">
          <span>our fills</span>
          <span className="text-[10px] uppercase tracking-wider text-muted-fg">
            {rows.length} total
          </span>
        </div>
      </CardHeader>
      <div className="grid grid-cols-[auto_auto_auto_auto_auto_1fr] gap-x-3 px-1 text-[10px] uppercase tracking-wider text-muted-fg">
        <span>ts</span>
        <span>symbol</span>
        <span>side</span>
        <span className="text-right">qty</span>
        <span className="text-right">price</span>
        <span className="text-right">cum pos</span>
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-xs tabular-nums">
        {slice.map((row, i) => (
          <TapeRow
            key={`${row.ts}-${row.symbol}-${i}`}
            row={row}
            highlighted={i === highlightIndex}
          />
        ))}
      </div>
    </Card>
  );
});

function TapeRow({ row, highlighted }: { row: OurTapeRow; highlighted: boolean }) {
  const sideClass = row.side === "buy" ? "text-buy" : "text-sell";
  return (
    <div
      aria-current={highlighted || undefined}
      className={cn(
        "grid grid-cols-[auto_auto_auto_auto_auto_1fr] gap-x-3 rounded px-1 py-0.5",
        highlighted && "bg-accent/10"
      )}
    >
      <span className="text-muted-fg">{row.ts}</span>
      <span>{row.symbol}</span>
      <span className={sideClass}>{row.side === "buy" ? "BUY" : "SELL"}</span>
      <span className={cn("text-right", sideClass)}>{row.qty}</span>
      <span className={cn("text-right", sideClass)}>{row.price}</span>
      <span
        className={cn(
          "text-right",
          row.cumulativePosition > 0 && "text-buy",
          row.cumulativePosition < 0 && "text-sell",
          row.cumulativePosition === 0 && "text-muted-fg"
        )}
      >
        {row.cumulativePosition >= 0 ? `+${row.cumulativePosition}` : row.cumulativePosition}
      </span>
    </div>
  );
}
