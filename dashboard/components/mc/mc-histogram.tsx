"use client";

import { useMemo } from "react";
import type { PnlHistogram } from "@/lib/types";
import { cn, formatCurrency } from "@/lib/utils";

const WIDTH = 600;
const HEIGHT = 200;
const PAD = { top: 10, right: 10, bottom: 28, left: 10 };

export function McHistogram({ histogram }: { histogram: PnlHistogram }) {
  const { bars, maxCount, zeroX } = useMemo(() => {
    const counts = histogram.counts;
    const edges = histogram.bin_edges;
    if (counts.length === 0 || edges.length < 2) {
      return { bars: [], maxCount: 0, zeroX: null };
    }
    const maxC = Math.max(...counts, 1);
    const minEdge = edges[0];
    const maxEdge = edges[edges.length - 1];
    const range = maxEdge - minEdge || 1;
    const innerW = WIDTH - PAD.left - PAD.right;
    const innerH = HEIGHT - PAD.top - PAD.bottom;

    const barsOut = counts.map((count, i) => {
      const lo = edges[i];
      const hi = edges[i + 1];
      const x = PAD.left + ((lo - minEdge) / range) * innerW;
      const w = Math.max(1, ((hi - lo) / range) * innerW - 1);
      const h = (count / maxC) * innerH;
      const y = PAD.top + innerH - h;
      const isBuy = hi > 0;
      return { x, y, w, h, count, lo, hi, isBuy };
    });

    const zero =
      minEdge <= 0 && maxEdge >= 0
        ? PAD.left + ((0 - minEdge) / range) * innerW
        : null;
    return { bars: barsOut, maxCount: maxC, zeroX: zero };
  }, [histogram]);

  if (bars.length === 0) {
    return <div className="text-xs text-muted-fg">no distribution data</div>;
  }

  const minEdge = histogram.bin_edges[0];
  const maxEdge = histogram.bin_edges[histogram.bin_edges.length - 1];

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="pnl distribution histogram"
      >
        {bars.map((b, i) => (
          <rect
            key={i}
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            className={cn(
              b.isBuy ? "fill-buy/60" : "fill-sell/60",
              "hover:fill-opacity-100"
            )}
          >
            <title>
              {`${formatCurrency(b.lo)}..${formatCurrency(b.hi)} — ${b.count} paths`}
            </title>
          </rect>
        ))}
        {zeroX !== null && (
          <line
            x1={zeroX}
            x2={zeroX}
            y1={PAD.top}
            y2={HEIGHT - PAD.bottom}
            className="stroke-muted-fg"
            strokeDasharray="4 2"
            strokeWidth={1}
          />
        )}
        <text
          x={PAD.left}
          y={HEIGHT - 8}
          className="fill-muted-fg font-mono text-[10px]"
        >
          {formatCurrency(minEdge)}
        </text>
        <text
          x={WIDTH - PAD.right}
          y={HEIGHT - 8}
          textAnchor="end"
          className="fill-muted-fg font-mono text-[10px]"
        >
          {formatCurrency(maxEdge)}
        </text>
        <text
          x={WIDTH / 2}
          y={HEIGHT - 8}
          textAnchor="middle"
          className="fill-muted-fg font-mono text-[10px]"
        >
          pnl (seashells), peak {maxCount}
        </text>
      </svg>
    </div>
  );
}
