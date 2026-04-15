"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  buildAxisDomains,
  buildRankMap,
  normalizeAxis,
  rankToColor,
  type Axis,
} from "@/lib/study-parallel";
import type { SearchSpace, StudyTrialSummary } from "@/lib/types";

interface Props {
  space: SearchSpace;
  trials: StudyTrialSummary[];
  objective: string;
  direction: "maximize" | "minimize";
  bestTrialNumber: number | null;
}

const WIDTH = 880;
const HEIGHT = 260;
const MARGIN = { top: 20, right: 30, bottom: 30, left: 30 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;

export function StudyParallelCoords({
  space,
  trials,
  objective,
  direction,
  bestTrialNumber,
}: Props) {
  const router = useRouter();
  const [hover, setHover] = useState<number | null>(null);

  const axes = useMemo(
    () => buildAxisDomains(space, trials, objective),
    [space, trials, objective]
  );
  const rankMap = useMemo(() => buildRankMap(trials, direction), [trials, direction]);
  const succeededTrials = useMemo(
    () => trials.filter((t) => t.value !== null && Number.isFinite(t.value)),
    [trials]
  );

  if (axes.length === 0 || succeededTrials.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-fg">
        parallel coordinates appear after the first completed trial
      </div>
    );
  }

  const axisCount = axes.length;
  const axisX = (i: number) => (axisCount === 1 ? PLOT_W / 2 : (i / (axisCount - 1)) * PLOT_W);
  const yFromNorm = (n: number) => PLOT_H - n * PLOT_H;

  function pathForTrial(trial: StudyTrialSummary): string | null {
    const points: [number, number][] = [];
    for (let i = 0; i < axes.length; i++) {
      const axis = axes[i];
      const raw =
        axis.name === objective ? trial.value : trial.params[axis.name];
      const norm = normalizeAxis(axis, raw);
      if (norm === null) return null;
      points.push([axisX(i), yFromNorm(norm)]);
    }
    return points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  }

  const lines = succeededTrials.map((trial) => {
    const d = pathForTrial(trial);
    if (d === null) return null;
    const isBest = trial.trial_number === bestTrialNumber;
    const rank = rankMap.get(trial.trial_number) ?? 0;
    const color = rankToColor(rank, succeededTrials.length, isBest);
    return { trial, d, color, isBest };
  });

  const hoveredTrial =
    hover !== null ? succeededTrials.find((t) => t.trial_number === hover) ?? null : null;

  return (
    <div className="relative w-full overflow-x-auto">
      <svg
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mx-auto block"
        role="img"
        aria-label="parallel coordinates of study trials"
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {axes.map((axis, i) => (
            <AxisLine key={axis.name} axis={axis} x={axisX(i)} />
          ))}

          {/* Non-best lines */}
          {lines.map((line) =>
            line && !line.isBest ? (
              <path
                key={`line-${line.trial.trial_number}`}
                d={line.d}
                fill="none"
                stroke={line.color}
                strokeWidth={hover === line.trial.trial_number ? 2.5 : 1}
                onMouseEnter={() => setHover(line.trial.trial_number)}
                onMouseLeave={() => setHover(null)}
                onClick={() => line.trial.run_id && router.push(`/runs/${encodeURIComponent(line.trial.run_id)}`)}
                className="cursor-pointer"
              />
            ) : null
          )}

          {/* Best line drawn last so it sits on top */}
          {lines.map((line) =>
            line && line.isBest ? (
              <path
                key={`best-${line.trial.trial_number}`}
                d={line.d}
                fill="none"
                stroke={line.color}
                strokeWidth={3}
                onMouseEnter={() => setHover(line.trial.trial_number)}
                onMouseLeave={() => setHover(null)}
                onClick={() => line.trial.run_id && router.push(`/runs/${encodeURIComponent(line.trial.run_id)}`)}
                className="cursor-pointer"
              />
            ) : null
          )}
        </g>
      </svg>

      {hoveredTrial && (
        <div className="pointer-events-none absolute left-4 top-2 rounded border border-border bg-bg/95 px-2 py-1 font-mono text-xs shadow">
          <div>
            #{hoveredTrial.trial_number} · {objective}={" "}
            <span className="text-buy">{hoveredTrial.value?.toFixed(2)}</span>
          </div>
          <div className="text-muted-fg">
            {Object.entries(hoveredTrial.params)
              .map(([k, v]) => `${k}=${String(v)}`)
              .join(" · ")}
          </div>
        </div>
      )}
    </div>
  );
}

function AxisLine({ axis, x }: { axis: Axis; x: number }) {
  const yTop = 0;
  const yBot = PLOT_H;

  const labels: { y: number; text: string }[] = [];
  if (axis.kind === "numeric") {
    const [lo, hi] = axis.domain ?? [0, 1];
    labels.push({ y: yBot, text: lo.toString() });
    labels.push({ y: yTop, text: hi.toString() });
  } else {
    const cats = axis.categories ?? [];
    const n = cats.length;
    cats.forEach((c, i) => {
      const norm = n === 1 ? 0.5 : i / (n - 1);
      labels.push({ y: PLOT_H - norm * PLOT_H, text: String(c) });
    });
  }

  return (
    <g>
      <line
        x1={x}
        y1={yTop}
        x2={x}
        y2={yBot}
        stroke="hsl(var(--border))"
        strokeWidth={1}
      />
      {labels.map((lbl, i) => (
        <text
          key={i}
          x={x}
          y={lbl.y}
          dy={4}
          textAnchor="middle"
          className="fill-muted-fg font-mono text-[9px]"
        >
          {lbl.text}
        </text>
      ))}
      <text
        x={x}
        y={-6}
        textAnchor="middle"
        className="fill-fg font-mono text-[10px]"
      >
        {axis.name}
      </text>
    </g>
  );
}
