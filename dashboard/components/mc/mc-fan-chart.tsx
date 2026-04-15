"use client";

import { useEffect, useMemo, useState } from "react";
import type { PnlCurveQuantiles } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

const WIDTH = 600;
const HEIGHT = 260;
const PAD = { top: 12, right: 12, bottom: 28, left: 52 };

interface Props {
  curve: PnlCurveQuantiles;
  referenceRunId?: string | null;
}

export function McFanChart({ curve, referenceRunId }: Props) {
  const [reference, setReference] = useState<number[] | null>(null);
  const [refError, setRefError] = useState<string | null>(null);

  useEffect(() => {
    if (!referenceRunId) {
      setReference(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(referenceRunId)}/events?stride=100`
        );
        if (!res.ok) throw new Error(`${res.status}`);
        const text = await res.text();
        const lines = text.split("\n").filter((l) => l.trim().length > 0);
        const byTs = new Map<number, number>();
        for (const line of lines) {
          const rec = JSON.parse(line);
          byTs.set(rec.ts as number, rec.pnl.total as number);
        }
        if (!cancelled) {
          const sortedTs = [...byTs.keys()].sort((a, b) => a - b);
          const values = sortedTs.map((ts) => byTs.get(ts) ?? 0);
          setReference(values);
        }
      } catch (err) {
        if (!cancelled) setRefError(String((err as Error).message));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [referenceRunId]);

  const geometry = useMemo(() => {
    const ts = curve.ts_grid;
    if (ts.length === 0) return null;
    const n = ts.length;
    const allVals = [
      ...curve.p05,
      ...curve.p25,
      ...curve.p50,
      ...curve.p75,
      ...curve.p95,
      ...(reference ?? []),
    ];
    const yMin = Math.min(...allVals, 0);
    const yMax = Math.max(...allVals, 0);
    const yRange = yMax - yMin || 1;
    const innerW = WIDTH - PAD.left - PAD.right;
    const innerH = HEIGHT - PAD.top - PAD.bottom;

    const xAt = (i: number) => PAD.left + (i / Math.max(1, n - 1)) * innerW;
    const yAt = (v: number) => PAD.top + innerH - ((v - yMin) / yRange) * innerH;

    const bandPath = (lo: number[], hi: number[]) => {
      const up = lo.map((v, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAt(v)}`);
      const down = hi
        .map((v, i) => {
          const idx = hi.length - 1 - i;
          return `L ${xAt(idx)} ${yAt(hi[idx])}`;
        })
        .join(" ");
      return `${up.join(" ")} ${down} Z`;
    };

    const linePath = (values: number[]) =>
      values.map((v, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAt(v)}`).join(" ");

    const referenceLine = reference
      ? reference.map((v, i) => {
          // rescale reference to curve.ts_grid length
          const pos = (i / Math.max(1, reference.length - 1)) * (n - 1);
          return `${i === 0 ? "M" : "L"} ${xAt(pos)} ${yAt(v)}`;
        }).join(" ")
      : null;

    return {
      yMin,
      yMax,
      xAt,
      yAt,
      outerBand: bandPath(curve.p05, curve.p95),
      innerBand: bandPath(curve.p25, curve.p75),
      medianLine: linePath(curve.p50),
      referenceLine,
    };
  }, [curve, reference]);

  if (!geometry) {
    return <div className="text-xs text-muted-fg">no curve data</div>;
  }

  return (
    <div className="w-full space-y-2">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="monte carlo equity curve fan"
      >
        <path d={geometry.outerBand} className="fill-accent/20" />
        <path d={geometry.innerBand} className="fill-accent/40" />
        <path
          d={geometry.medianLine}
          className="stroke-accent"
          strokeWidth={1.5}
          fill="none"
        />
        {geometry.referenceLine && (
          <path
            d={geometry.referenceLine}
            className="stroke-fg"
            strokeWidth={1.25}
            fill="none"
            strokeDasharray="4 3"
          />
        )}
        {geometry.yMin <= 0 && geometry.yMax >= 0 && (
          <line
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={geometry.yAt(0)}
            y2={geometry.yAt(0)}
            className="stroke-muted-fg"
            strokeDasharray="2 3"
            strokeWidth={1}
          />
        )}
        <text
          x={PAD.left - 6}
          y={geometry.yAt(geometry.yMax)}
          textAnchor="end"
          className="fill-muted-fg font-mono text-[10px]"
          dominantBaseline="hanging"
        >
          {formatCurrency(geometry.yMax)}
        </text>
        <text
          x={PAD.left - 6}
          y={geometry.yAt(geometry.yMin)}
          textAnchor="end"
          className="fill-muted-fg font-mono text-[10px]"
        >
          {formatCurrency(geometry.yMin)}
        </text>
        <text
          x={WIDTH / 2}
          y={HEIGHT - 8}
          textAnchor="middle"
          className="fill-muted-fg font-mono text-[10px]"
        >
          ts (downsampled), p5–p95 bands
        </text>
      </svg>
      <div className="flex items-center gap-3 text-[11px] text-muted-fg">
        <LegendSwatch className="bg-accent/20" label="p5–p95" />
        <LegendSwatch className="bg-accent/40" label="p25–p75" />
        <LegendLine className="bg-accent" label="median" />
        {reference ? (
          <LegendLine className="bg-fg" label="backtest" dashed />
        ) : referenceRunId && !refError ? (
          <span>loading backtest…</span>
        ) : referenceRunId && refError ? (
          <span className="text-sell">backtest load failed</span>
        ) : (
          <span>no matching backtest</span>
        )}
      </div>
    </div>
  );
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2 w-3 rounded-sm ${className}`} />
      {label}
    </span>
  );
}

function LegendLine({
  className,
  label,
  dashed,
}: {
  className: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-block h-0.5 w-4 ${className} ${dashed ? "border-t border-dashed border-fg" : ""}`}
      />
      {label}
    </span>
  );
}
