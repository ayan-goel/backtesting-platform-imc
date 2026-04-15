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

interface ChartPoint {
  ts: number;
  value: number;
}

interface TimeSeriesChartProps {
  points: ChartPoint[];
  title: string;
  color: string;
  onClick?: (ts: number) => void;
  height?: number;
}

export const TimeSeriesChart = memo(function TimeSeriesChart({
  points,
  title,
  color,
  onClick,
  height = 220,
}: TimeSeriesChartProps) {
  return (
    <div>
      {title && (
        <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
          {title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={points}
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          onClick={(e) => {
            if (onClick && e && typeof e.activeLabel === "number") {
              onClick(e.activeLabel);
            } else if (onClick && e?.activeLabel !== undefined) {
              onClick(Number(e.activeLabel));
            }
          }}
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
            width={70}
            domain={["dataMin - 1", "dataMax + 1"]}
            allowDecimals
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
            dataKey="value"
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
});
