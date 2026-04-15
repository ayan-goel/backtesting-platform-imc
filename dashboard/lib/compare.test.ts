import { describe, expect, it } from "vitest";
import {
  checkCompatibility,
  computeSummaryDelta,
  pairPnlSeries,
  pairPositionSeries,
} from "./compare";
import type { EventRecord, RunSummary } from "./types";

function mkSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    _id: "run-a",
    created_at: "2026-04-13T00:00:00Z",
    strategy_path: "a.py",
    strategy_hash: "sha256:a",
    round: 0,
    day: -2,
    matcher: "depth_only",
    params: {},
    engine_version: "0.1.0",
    status: "succeeded",
    duration_ms: 1000,
    pnl_total: 100,
    pnl_by_product: { KELP: 60, EMERALDS: 40 },
    max_inventory_by_product: { KELP: 10, EMERALDS: 5 },
    turnover_by_product: { KELP: 50, EMERALDS: 20 },
    num_events: 20000,
    artifact_dir: "runs/run-a",
    error: null,
    ...overrides,
  };
}

function mkEvent(
  ts: number,
  product: string,
  pnl: number,
  position: number
): EventRecord {
  return {
    run_id: "r",
    ts,
    product,
    state: {
      order_depth: { buy: {}, sell: {} },
      position,
      market_trades: [],
    },
    actions: { orders: [] },
    fills: [],
    pnl: { cash: 0, mark: 0, total: pnl },
    debug: {},
  };
}

describe("checkCompatibility", () => {
  it("reports compatible for same round/day/products", () => {
    const res = checkCompatibility(mkSummary(), mkSummary({ _id: "run-b" }));
    expect(res.compatible).toBe(true);
    expect(res.reasons).toEqual([]);
    expect(res.sharedProducts).toEqual(["EMERALDS", "KELP"]);
  });

  it("flags different round", () => {
    const res = checkCompatibility(mkSummary(), mkSummary({ round: 1 }));
    expect(res.compatible).toBe(false);
    expect(res.reasons.some((r) => r.includes("round"))).toBe(true);
  });

  it("flags different day", () => {
    const res = checkCompatibility(mkSummary(), mkSummary({ day: -1 }));
    expect(res.compatible).toBe(false);
    expect(res.reasons.some((r) => r.includes("day"))).toBe(true);
  });

  it("flags no shared products", () => {
    const res = checkCompatibility(
      mkSummary({ pnl_by_product: { KELP: 0 } }),
      mkSummary({ pnl_by_product: { TOMATOES: 0 } })
    );
    expect(res.compatible).toBe(false);
    expect(res.reasons.some((r) => r.includes("common"))).toBe(true);
    expect(res.sharedProducts).toEqual([]);
  });

  it("allows different strategy / matcher / params", () => {
    const res = checkCompatibility(
      mkSummary({ strategy_hash: "sha256:a", matcher: "depth_only", params: { x: 1 } }),
      mkSummary({ strategy_hash: "sha256:b", matcher: "depth_only", params: { x: 2 } })
    );
    expect(res.compatible).toBe(true);
  });

  it("collects multiple failure reasons", () => {
    const res = checkCompatibility(
      mkSummary({ round: 0, day: -2, pnl_by_product: { KELP: 0 } }),
      mkSummary({ round: 1, day: -1, pnl_by_product: { TOMATOES: 0 } })
    );
    expect(res.compatible).toBe(false);
    expect(res.reasons.length).toBe(3);
  });

  it("shared products are sorted ascending", () => {
    const res = checkCompatibility(
      mkSummary({ pnl_by_product: { TOMATOES: 0, KELP: 0, EMERALDS: 0 } }),
      mkSummary({ pnl_by_product: { EMERALDS: 0, KELP: 0, TOMATOES: 0 } })
    );
    expect(res.sharedProducts).toEqual(["EMERALDS", "KELP", "TOMATOES"]);
  });
});

describe("pairPnlSeries", () => {
  it("returns [] for empty inputs", () => {
    expect(pairPnlSeries([], [], "KELP")).toEqual([]);
  });

  it("pairs by ts when both runs have matching events", () => {
    const a = [mkEvent(0, "KELP", 10, 0), mkEvent(100, "KELP", 15, 0)];
    const b = [mkEvent(0, "KELP", 12, 0), mkEvent(100, "KELP", 20, 0)];
    const series = pairPnlSeries(a, b, "KELP");
    expect(series).toEqual([
      { ts: 0, a: 10, b: 12, delta: 2 },
      { ts: 100, a: 15, b: 20, delta: 5 },
    ]);
  });

  it("emits null on one-sided timestamps", () => {
    const a = [mkEvent(0, "KELP", 10, 0), mkEvent(100, "KELP", 15, 0)];
    const b = [mkEvent(100, "KELP", 20, 0)];
    const series = pairPnlSeries(a, b, "KELP");
    expect(series[0]).toEqual({ ts: 0, a: 10, b: null, delta: null });
    expect(series[1]).toEqual({ ts: 100, a: 15, b: 20, delta: 5 });
  });

  it("filters to the requested product", () => {
    const a = [
      mkEvent(0, "KELP", 10, 0),
      mkEvent(0, "EMERALDS", 999, 0),
    ];
    const b = [
      mkEvent(0, "KELP", 12, 0),
      mkEvent(0, "EMERALDS", 888, 0),
    ];
    const series = pairPnlSeries(a, b, "KELP");
    expect(series).toHaveLength(1);
    expect(series[0]).toEqual({ ts: 0, a: 10, b: 12, delta: 2 });
  });

  it("sorts union of timestamps ascending", () => {
    const a = [mkEvent(200, "KELP", 5, 0), mkEvent(0, "KELP", 1, 0)];
    const b = [mkEvent(100, "KELP", 3, 0)];
    const series = pairPnlSeries(a, b, "KELP");
    expect(series.map((p) => p.ts)).toEqual([0, 100, 200]);
  });
});

describe("pairPositionSeries", () => {
  it("pairs position by ts", () => {
    const a = [mkEvent(0, "KELP", 0, 5), mkEvent(100, "KELP", 0, 10)];
    const b = [mkEvent(0, "KELP", 0, 3), mkEvent(100, "KELP", 0, -2)];
    expect(pairPositionSeries(a, b, "KELP")).toEqual([
      { ts: 0, a: 5, b: 3 },
      { ts: 100, a: 10, b: -2 },
    ]);
  });

  it("handles one-sided timestamps with null", () => {
    const a = [mkEvent(0, "KELP", 0, 5)];
    const b = [mkEvent(100, "KELP", 0, -2)];
    expect(pairPositionSeries(a, b, "KELP")).toEqual([
      { ts: 0, a: 5, b: null },
      { ts: 100, a: null, b: -2 },
    ]);
  });

  it("filters by product", () => {
    const a = [
      mkEvent(0, "KELP", 0, 5),
      mkEvent(0, "EMERALDS", 0, 99),
    ];
    const b = [
      mkEvent(0, "KELP", 0, -5),
      mkEvent(0, "EMERALDS", 0, 88),
    ];
    const series = pairPositionSeries(a, b, "KELP");
    expect(series).toEqual([{ ts: 0, a: 5, b: -5 }]);
  });
});

describe("computeSummaryDelta", () => {
  it("computes scalar deltas with b - a", () => {
    const a = mkSummary({ pnl_total: 100, duration_ms: 1000 });
    const b = mkSummary({ pnl_total: 150, duration_ms: 1200 });
    const delta = computeSummaryDelta(a, b);
    expect(delta.pnlTotalDelta).toBe(50);
    expect(delta.durationDeltaMs).toBe(200);
  });

  it("produces per-product deltas keyed by union of products", () => {
    const a = mkSummary({ pnl_by_product: { KELP: 60, EMERALDS: 40 } });
    const b = mkSummary({ pnl_by_product: { KELP: 80, TOMATOES: 30 } });
    const delta = computeSummaryDelta(a, b);
    expect(delta.pnlByProductDelta.KELP).toBe(20);
    expect(delta.pnlByProductDelta.EMERALDS).toBe(-40); // a had it, b didn't
    expect(delta.pnlByProductDelta.TOMATOES).toBe(30); // b had it, a didn't
  });

  it("handles negative deltas", () => {
    const a = mkSummary({ pnl_total: 200 });
    const b = mkSummary({ pnl_total: 150 });
    expect(computeSummaryDelta(a, b).pnlTotalDelta).toBe(-50);
  });
});
