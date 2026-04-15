"use client";

import { memo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PriceSeries } from "@/lib/replay";

interface PriceChartProps {
  series: PriceSeries;
  onJump?: (ts: number) => void;
  height?: number;
}

export const PriceChart = memo(function PriceChart({
  series,
  onJump,
  height = 260,
}: PriceChartProps) {
  // ComposedChart needs a single shared XAxis domain. `mid` may have gaps, so
  // derive the domain from all series combined.
  const allTs: number[] = [];
  for (const p of series.mid) allTs.push(p.ts);
  for (const p of series.bids) allTs.push(p.ts);
  for (const p of series.asks) allTs.push(p.ts);
  for (const p of series.fills) allTs.push(p.ts);
  const tsMin = allTs.length > 0 ? Math.min(...allTs) : 0;
  const tsMax = allTs.length > 0 ? Math.max(...allTs) : 0;

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          onClick={(e) => {
            if (onJump && e && typeof e.activeLabel === "number") {
              onJump(e.activeLabel);
            } else if (onJump && e?.activeLabel !== undefined) {
              onJump(Number(e.activeLabel));
            }
          }}
        >
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" />
          <XAxis
            dataKey="ts"
            type="number"
            domain={[tsMin, tsMax]}
            stroke="hsl(var(--muted-fg))"
            fontSize={11}
            allowDuplicatedCategory={false}
          />
          <YAxis
            stroke="hsl(var(--muted-fg))"
            fontSize={11}
            width={70}
            domain={["dataMin - 2", "dataMax + 2"]}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--bg))",
              border: "1px solid hsl(var(--border))",
              fontSize: 12,
            }}
          />
          <Line
            data={series.mid}
            dataKey="value"
            name="mid"
            type="monotone"
            stroke="hsl(var(--muted-fg))"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Scatter
            data={series.bids}
            dataKey="value"
            name="our bids"
            fill="hsl(var(--buy))"
            shape="circle"
            isAnimationActive={false}
            legendType="none"
          />
          <Scatter
            data={series.asks}
            dataKey="value"
            name="our asks"
            fill="hsl(var(--sell))"
            shape="circle"
            isAnimationActive={false}
            legendType="none"
          />
          <Scatter
            data={series.fills.filter((f) => f.side === "buy")}
            dataKey="value"
            name="fills (buy)"
            fill="hsl(var(--buy))"
            shape="triangle"
            isAnimationActive={false}
            legendType="none"
          />
          <Scatter
            data={series.fills.filter((f) => f.side === "sell")}
            dataKey="value"
            name="fills (sell)"
            fill="hsl(var(--sell))"
            shape="triangle"
            isAnimationActive={false}
            legendType="none"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mt-1 flex gap-4 px-1 text-[10px] uppercase tracking-wider text-muted-fg">
        <LegendDot className="bg-muted-fg" /> mid
        <LegendDot className="bg-buy" /> our bid
        <LegendDot className="bg-sell" /> our ask
        <LegendTri className="text-buy" /> buy fill
        <LegendTri className="text-sell" /> sell fill
      </div>
    </div>
  );
});

function LegendDot({ className }: { className: string }) {
  return <span className={`inline-block h-2 w-2 rounded-full align-middle ${className}`} />;
}

function LegendTri({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 10 10" className={`inline-block h-2.5 w-2.5 align-middle ${className}`}>
      <polygon points="5,0 10,10 0,10" fill="currentColor" />
    </svg>
  );
}
