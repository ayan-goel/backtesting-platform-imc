// Pure helpers for the parallel-coordinates chart on /studies/[id].

import type { ParamSpec, SearchSpace, StudyTrialSummary } from "@/lib/types";

export interface Axis {
  kind: "numeric" | "categorical";
  name: string;
  /** Numeric domain (min, max) for numeric axes. */
  domain?: [number, number];
  /** Ordered list of possible values for categorical axes. */
  categories?: (string | number)[];
}

/** Build one Axis per search-space param + a trailing objective axis. */
export function buildAxisDomains(
  space: SearchSpace,
  trials: StudyTrialSummary[],
  objectiveName: string
): Axis[] {
  const axes: Axis[] = [];
  for (const name of Object.keys(space)) {
    const spec = space[name];
    axes.push(axisForSpec(name, spec));
  }

  // Objective axis. Domain derived from trial values (finite only).
  const values = trials
    .map((t) => t.value)
    .filter((v): v is number => v !== null && Number.isFinite(v));
  let lo = 0;
  let hi = 1;
  if (values.length > 0) {
    lo = Math.min(...values);
    hi = Math.max(...values);
    if (lo === hi) {
      lo -= 1;
      hi += 1;
    }
  }
  axes.push({
    kind: "numeric",
    name: objectiveName,
    domain: [lo, hi],
  });
  return axes;
}

function axisForSpec(name: string, spec: ParamSpec): Axis {
  if (spec.type === "int" || spec.type === "float") {
    return { kind: "numeric", name, domain: [spec.low, spec.high] };
  }
  return { kind: "categorical", name, categories: [...spec.choices] };
}

/** Normalize a value to [0, 1] along its axis. Returns null if unknown. */
export function normalizeAxis(axis: Axis, value: unknown): number | null {
  if (axis.kind === "numeric") {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    const [lo, hi] = axis.domain ?? [0, 1];
    if (hi === lo) return 0.5;
    const n = (value - lo) / (hi - lo);
    return Math.max(0, Math.min(1, n));
  }
  const categories = axis.categories ?? [];
  if (categories.length === 0) return null;
  const idx = categories.findIndex((c) => c === value);
  if (idx === -1) return null;
  if (categories.length === 1) return 0.5;
  return idx / (categories.length - 1);
}

/** Map a trial's [rank, total] to a color. Best = buy green, worst = muted. */
export function rankToColor(rank: number, total: number, isBest: boolean): string {
  if (isBest) return "hsl(var(--buy))";
  if (total <= 1) return "hsl(var(--accent) / 0.7)";
  // Linearly interpolate between accent and muted based on rank.
  const t = rank / (total - 1);
  const alpha = 0.15 + (1 - t) * 0.55;
  return `hsl(var(--accent) / ${alpha.toFixed(2)})`;
}

/** Rank trials by objective (direction-aware) and return a map trial_number → rank. */
export function buildRankMap(
  trials: StudyTrialSummary[],
  direction: "maximize" | "minimize"
): Map<number, number> {
  const valued = trials.filter((t) => t.value !== null && Number.isFinite(t.value));
  const mul = direction === "maximize" ? -1 : 1;
  const sorted = [...valued].sort((a, b) => mul * ((a.value ?? 0) - (b.value ?? 0)));
  const map = new Map<number, number>();
  sorted.forEach((t, i) => map.set(t.trial_number, i));
  return map;
}
