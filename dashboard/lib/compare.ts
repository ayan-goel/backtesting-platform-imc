// Pure helpers for the /compare page. React-free so they're unit-testable
// and drag-path cheap via useMemo. All inputs are ascending-ts arrays; all
// outputs keep that invariant.

import type { EventRecord, RunSummary } from "./types";

export interface CompatibilityResult {
  compatible: boolean;
  reasons: string[];
  sharedProducts: string[];
}

/**
 * Two runs are "compatible" for charting when they share round, day, and at
 * least one product. Strategy hash, matcher, and params are explicitly not
 * checked — comparing two strategies (or two parameter sets of one strategy)
 * on the same day is a primary use case.
 */
export function checkCompatibility(
  a: RunSummary,
  b: RunSummary
): CompatibilityResult {
  const reasons: string[] = [];
  if (a.round !== b.round) {
    reasons.push(`different round (${a.round} vs ${b.round})`);
  }
  if (a.day !== b.day) {
    reasons.push(`different day (${a.day} vs ${b.day})`);
  }

  const aProducts = Object.keys(a.pnl_by_product);
  const bProducts = new Set(Object.keys(b.pnl_by_product));
  const sharedProducts = aProducts.filter((p) => bProducts.has(p)).sort();
  if (sharedProducts.length === 0) {
    reasons.push("no products in common");
  }

  return {
    compatible: reasons.length === 0,
    reasons,
    sharedProducts,
  };
}

export interface PnlPoint {
  ts: number;
  a: number | null;
  b: number | null;
  delta: number | null;
}

/**
 * Zip both runs' event streams by timestamp and emit one row per union ts.
 * The event log is per-(ts, product), so we filter each stream to the chosen
 * product first and read `pnl.total` — which in the engine is a cross-product
 * running total. That's the right thing to plot: the effect of this product's
 * decisions on the overall book.
 */
export function pairPnlSeries(
  eventsA: readonly EventRecord[],
  eventsB: readonly EventRecord[],
  product: string
): PnlPoint[] {
  const mapA = new Map<number, number>();
  for (const e of eventsA) {
    if (e.product === product) mapA.set(e.ts, e.pnl.total);
  }
  const mapB = new Map<number, number>();
  for (const e of eventsB) {
    if (e.product === product) mapB.set(e.ts, e.pnl.total);
  }

  const allTs = new Set<number>([...mapA.keys(), ...mapB.keys()]);
  const out: PnlPoint[] = [];
  for (const ts of allTs) {
    const a = mapA.get(ts) ?? null;
    const b = mapB.get(ts) ?? null;
    const delta = a !== null && b !== null ? b - a : null;
    out.push({ ts, a, b, delta });
  }
  out.sort((x, y) => x.ts - y.ts);
  return out;
}

export interface PositionPoint {
  ts: number;
  a: number | null;
  b: number | null;
}

/**
 * Same pairing shape as `pairPnlSeries` but reading `state.position` from the
 * selected product's rows.
 */
export function pairPositionSeries(
  eventsA: readonly EventRecord[],
  eventsB: readonly EventRecord[],
  product: string
): PositionPoint[] {
  const mapA = new Map<number, number>();
  for (const e of eventsA) {
    if (e.product === product) mapA.set(e.ts, e.state.position);
  }
  const mapB = new Map<number, number>();
  for (const e of eventsB) {
    if (e.product === product) mapB.set(e.ts, e.state.position);
  }

  const allTs = new Set<number>([...mapA.keys(), ...mapB.keys()]);
  const out: PositionPoint[] = [];
  for (const ts of allTs) {
    out.push({
      ts,
      a: mapA.get(ts) ?? null,
      b: mapB.get(ts) ?? null,
    });
  }
  out.sort((x, y) => x.ts - y.ts);
  return out;
}

export interface SummaryDelta {
  pnlTotalDelta: number;
  pnlByProductDelta: Record<string, number>;
  durationDeltaMs: number;
}

/**
 * Scalar deltas for the summary strip at the top of the compare page.
 * All deltas are `b - a` so a positive number means B did better / took
 * longer / held more.
 */
export function computeSummaryDelta(a: RunSummary, b: RunSummary): SummaryDelta {
  const products = new Set<string>([
    ...Object.keys(a.pnl_by_product),
    ...Object.keys(b.pnl_by_product),
  ]);
  const pnlByProductDelta: Record<string, number> = {};
  for (const p of products) {
    const aPnl = a.pnl_by_product[p] ?? 0;
    const bPnl = b.pnl_by_product[p] ?? 0;
    pnlByProductDelta[p] = bPnl - aPnl;
  }

  return {
    pnlTotalDelta: b.pnl_total - a.pnl_total,
    pnlByProductDelta,
    durationDeltaMs: b.duration_ms - a.duration_ms,
  };
}
