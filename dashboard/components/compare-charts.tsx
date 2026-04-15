"use client";

import { memo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PnlPoint, PositionPoint } from "@/lib/compare";

// Margins match CursorOverlay's hardcoded constants so the overlay line
// sits correctly inside the plot area.
const Y_AXIS_WIDTH = 70;
const RIGHT_MARGIN = 16;
const TOP_MARGIN = 8;

interface PnlProps {
  series: PnlPoint[];
  height?: number;
}

export const ComparePnlChart = memo(function ComparePnlChart({
  series,
  height = 240,
}: PnlProps) {
  return (
    <Frame title="pnl (total)" height={height}>
      <LineChart
        data={series}
        margin={{ top: TOP_MARGIN, right: RIGHT_MARGIN, left: 0, bottom: 0 }}
      >
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" />
        <XAxis
          dataKey="ts"
          type="number"
          domain={["dataMin", "dataMax"]}
          stroke="hsl(var(--muted-fg))"
          fontSize={11}
        />
        <YAxis
          stroke="hsl(var(--muted-fg))"
          fontSize={11}
          width={Y_AXIS_WIDTH}
          domain={["dataMin - 1", "dataMax + 1"]}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(var(--bg))",
            border: "1px solid hsl(var(--border))",
            fontSize: 12,
          }}
        />
        <Line
          type="monotone"
          dataKey="a"
          name="A"
          stroke="hsl(var(--buy))"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="b"
          name="B"
          stroke="hsl(var(--accent))"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </Frame>
  );
});

interface PositionProps {
  series: PositionPoint[];
  height?: number;
}

export const ComparePositionChart = memo(function ComparePositionChart({
  series,
  height = 240,
}: PositionProps) {
  return (
    <Frame title="position" height={height}>
      <LineChart
        data={series}
        margin={{ top: TOP_MARGIN, right: RIGHT_MARGIN, left: 0, bottom: 0 }}
      >
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" />
        <XAxis
          dataKey="ts"
          type="number"
          domain={["dataMin", "dataMax"]}
          stroke="hsl(var(--muted-fg))"
          fontSize={11}
        />
        <YAxis
          stroke="hsl(var(--muted-fg))"
          fontSize={11}
          width={Y_AXIS_WIDTH}
          domain={["dataMin - 1", "dataMax + 1"]}
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
          type="monotone"
          dataKey="a"
          name="A"
          stroke="hsl(var(--buy))"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="b"
          name="B"
          stroke="hsl(var(--accent))"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </Frame>
  );
});

function Frame({
  title,
  height,
  children,
}: {
  title: string;
  height: number;
  children: React.ReactElement;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-3 text-[10px] uppercase tracking-wider text-muted-fg">
        <span>{title}</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-buy" /> A
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-accent" /> B
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        {children}
      </ResponsiveContainer>
    </div>
  );
}
