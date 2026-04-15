import { describe, expect, it } from "vitest";
import {
  buildMarketTape,
  buildOurTape,
  buildPriceSeries,
  buildTickMarks,
  computeMid,
  computeTotals,
  depthLevels,
  snapToNearestTs,
  stepTs,
  windowRows,
} from "./replay";
import type { EventRecord } from "./types";

function mkEvent(ts: number): EventRecord {
  return {
    run_id: "r",
    ts,
    product: "KELP",
    state: {
      order_depth: { buy: {}, sell: {} },
      position: 0,
      market_trades: [],
    },
    actions: { orders: [] },
    fills: [],
    pnl: { cash: 0, mark: 0, total: 0 },
    debug: {},
  };
}

function withBook(
  ts: number,
  buy: Record<number, number>,
  sell: Record<number, number>
): EventRecord {
  const e = mkEvent(ts);
  return {
    ...e,
    state: {
      ...e.state,
      order_depth: {
        buy: Object.fromEntries(Object.entries(buy).map(([k, v]) => [k, v])),
        sell: Object.fromEntries(Object.entries(sell).map(([k, v]) => [k, v])),
      },
    },
  };
}

const events = [0, 100, 200, 300, 400, 500].map(mkEvent);

describe("snapToNearestTs", () => {
  it("returns input ts when events is empty", () => {
    expect(snapToNearestTs([], 42)).toBe(42);
  });

  it("returns first ts when input is before the first event", () => {
    expect(snapToNearestTs(events, -50)).toBe(0);
  });

  it("returns last ts when input is after the last event", () => {
    expect(snapToNearestTs(events, 999)).toBe(500);
  });

  it("returns exact match", () => {
    expect(snapToNearestTs(events, 200)).toBe(200);
  });

  it("snaps to nearest neighbor — rounds down when closer to earlier", () => {
    expect(snapToNearestTs(events, 120)).toBe(100);
  });

  it("snaps to nearest neighbor — rounds up when closer to later", () => {
    expect(snapToNearestTs(events, 180)).toBe(200);
  });

  it("ties go to the earlier event", () => {
    expect(snapToNearestTs(events, 150)).toBe(100);
  });

  it("handles a single-event array", () => {
    expect(snapToNearestTs([mkEvent(42)], 0)).toBe(42);
    expect(snapToNearestTs([mkEvent(42)], 42)).toBe(42);
    expect(snapToNearestTs([mkEvent(42)], 99)).toBe(42);
  });

  it("handles non-uniform spacing", () => {
    const nonUniform = [0, 10, 1000, 1001, 5000].map(mkEvent);
    expect(snapToNearestTs(nonUniform, 500)).toBe(10);
    expect(snapToNearestTs(nonUniform, 600)).toBe(1000);
    expect(snapToNearestTs(nonUniform, 1000)).toBe(1000);
  });
});

describe("stepTs", () => {
  it("returns current when events is empty", () => {
    expect(stepTs([], 42, 1)).toBe(42);
    expect(stepTs([], 42, -1)).toBe(42);
  });

  it("steps forward from an exact match", () => {
    expect(stepTs(events, 200, 1)).toBe(300);
  });

  it("steps backward from an exact match", () => {
    expect(stepTs(events, 200, -1)).toBe(100);
  });

  it("clamps at the last event stepping forward", () => {
    expect(stepTs(events, 500, 1)).toBe(500);
  });

  it("clamps at the first event stepping backward", () => {
    expect(stepTs(events, 0, -1)).toBe(0);
  });

  it("snaps a non-matching input before stepping", () => {
    // 150 snaps to 100, step forward → 200
    expect(stepTs(events, 150, 1)).toBe(200);
    // 150 snaps to 100, step back → 0
    expect(stepTs(events, 150, -1)).toBe(0);
  });

  it("handles out-of-range input on either side", () => {
    expect(stepTs(events, -999, 1)).toBe(100); // snap to 0, step forward
    expect(stepTs(events, 9999, -1)).toBe(400); // snap to 500, step back
  });
});

describe("depthLevels", () => {
  it("sorts bids descending and asks ascending with positive qtys", () => {
    const d = depthLevels({
      buy: { "9990": 25, "9992": 11, "9991": 5 },
      sell: { "10010": -25, "10008": -11, "10009": -5 },
    });
    expect(d.bids).toEqual([
      { price: 9992, qty: 11 },
      { price: 9991, qty: 5 },
      { price: 9990, qty: 25 },
    ]);
    expect(d.asks).toEqual([
      { price: 10008, qty: 11 },
      { price: 10009, qty: 5 },
      { price: 10010, qty: 25 },
    ]);
  });

  it("absolutizes negative sell volumes", () => {
    const d = depthLevels({ buy: {}, sell: { "100": -42 } });
    expect(d.asks[0].qty).toBe(42);
  });

  it("handles an empty book", () => {
    const d = depthLevels({ buy: {}, sell: {} });
    expect(d.bids).toEqual([]);
    expect(d.asks).toEqual([]);
  });

  it("handles a one-sided book", () => {
    const d = depthLevels({ buy: { "99": 5 }, sell: {} });
    expect(d.bids.length).toBe(1);
    expect(d.asks.length).toBe(0);
  });
});

describe("computeMid", () => {
  it("returns the midpoint of best bid and best ask", () => {
    const e = withBook(0, { 9998: 10, 9999: 5 }, { 10001: -5, 10002: -10 });
    expect(computeMid(e)).toBe(10000);
  });

  it("returns null when bids are empty", () => {
    const e = withBook(0, {}, { 10001: -5 });
    expect(computeMid(e)).toBeNull();
  });

  it("returns null when asks are empty", () => {
    const e = withBook(0, { 9999: 5 }, {});
    expect(computeMid(e)).toBeNull();
  });

  it("returns null on a totally empty book", () => {
    expect(computeMid(mkEvent(0))).toBeNull();
  });

  it("handles a single-level book on each side", () => {
    const e = withBook(0, { 100: 1 }, { 102: -1 });
    expect(computeMid(e)).toBe(101);
  });
});

describe("buildPriceSeries", () => {
  it("returns empty series for empty events", () => {
    const s = buildPriceSeries([]);
    expect(s.mid).toEqual([]);
    expect(s.bids).toEqual([]);
    expect(s.asks).toEqual([]);
    expect(s.fills).toEqual([]);
  });

  it("skips mid points for one-sided books (gap preserved)", () => {
    const e1 = withBook(0, { 99: 1 }, { 101: -1 });
    const e2 = withBook(100, { 99: 1 }, {}); // one-sided
    const e3 = withBook(200, { 100: 1 }, { 102: -1 });
    const s = buildPriceSeries([e1, e2, e3]);
    expect(s.mid.map((p) => p.ts)).toEqual([0, 200]);
    expect(s.mid.map((p) => p.value)).toEqual([100, 101]);
  });

  it("splits orders into bids (qty > 0) and asks (qty < 0)", () => {
    const e: EventRecord = {
      ...mkEvent(0),
      actions: {
        orders: [
          { price: 99, qty: 5 },
          { price: 101, qty: -5 },
          { price: 98, qty: 3 },
        ],
      },
    };
    const s = buildPriceSeries([e]);
    expect(s.bids).toEqual([
      { ts: 0, value: 99 },
      { ts: 0, value: 98 },
    ]);
    expect(s.asks).toEqual([{ ts: 0, value: 101 }]);
  });

  it("derives fill side from qty sign", () => {
    const e: EventRecord = {
      ...mkEvent(0),
      fills: [
        { price: 100, qty: 5, source: "book" },
        { price: 101, qty: -3, source: "book" },
      ],
    };
    const s = buildPriceSeries([e]);
    expect(s.fills).toEqual([
      { ts: 0, value: 100, side: "buy" },
      { ts: 0, value: 101, side: "sell" },
    ]);
  });
});

describe("buildMarketTape", () => {
  function tradedEvent(
    product: string,
    ts: number,
    trades: Array<{
      price: number;
      qty: number;
      buyer: string | null;
      seller: string | null;
    }>
  ): EventRecord {
    return {
      ...mkEvent(ts),
      product,
      state: { ...mkEvent(ts).state, market_trades: trades },
    };
  }

  it("returns [] for empty input", () => {
    expect(buildMarketTape({})).toEqual([]);
  });

  it("flat-maps market trades from a single product", () => {
    const e1 = tradedEvent("KELP", 100, [
      { price: 10000, qty: 3, buyer: "A", seller: "B" },
    ]);
    const e2 = tradedEvent("KELP", 200, [
      { price: 10001, qty: 2, buyer: null, seller: null },
    ]);
    const tape = buildMarketTape({ KELP: [e1, e2] });
    expect(tape.length).toBe(2);
    expect(tape[0]).toEqual({
      ts: 100,
      symbol: "KELP",
      price: 10000,
      qty: 3,
      buyer: "A",
      seller: "B",
    });
    expect(tape[1].ts).toBe(200);
  });

  it("interleaves multiple products by ts", () => {
    const kelp = tradedEvent("KELP", 100, [
      { price: 100, qty: 1, buyer: null, seller: null },
    ]);
    const emeralds = tradedEvent("EMERALDS", 50, [
      { price: 200, qty: 1, buyer: null, seller: null },
    ]);
    const tape = buildMarketTape({ KELP: [kelp], EMERALDS: [emeralds] });
    expect(tape.map((r) => r.ts)).toEqual([50, 100]);
  });
});

describe("buildOurTape", () => {
  function filledEvent(
    product: string,
    ts: number,
    fills: Array<{ price: number; qty: number; source: string }>
  ): EventRecord {
    return { ...mkEvent(ts), product, fills };
  }

  it("returns [] for empty input", () => {
    expect(buildOurTape({})).toEqual([]);
  });

  it("derives cumulative position per product", () => {
    const tape = buildOurTape({
      KELP: [
        filledEvent("KELP", 100, [{ price: 10, qty: 5, source: "book" }]),
        filledEvent("KELP", 200, [{ price: 11, qty: -2, source: "book" }]),
        filledEvent("KELP", 300, [{ price: 10, qty: 3, source: "book" }]),
      ],
    });
    expect(tape.map((r) => r.cumulativePosition)).toEqual([5, 3, 6]);
  });

  it("keeps per-product positions independent", () => {
    const tape = buildOurTape({
      KELP: [filledEvent("KELP", 100, [{ price: 10, qty: 5, source: "book" }])],
      EMERALDS: [
        filledEvent("EMERALDS", 150, [{ price: 100, qty: -3, source: "book" }]),
      ],
    });
    expect(tape).toHaveLength(2);
    // Sorted by ts
    expect(tape[0].symbol).toBe("KELP");
    expect(tape[0].cumulativePosition).toBe(5);
    expect(tape[1].symbol).toBe("EMERALDS");
    expect(tape[1].cumulativePosition).toBe(-3);
  });

  it("derives side from qty sign", () => {
    const tape = buildOurTape({
      KELP: [
        filledEvent("KELP", 100, [
          { price: 10, qty: 5, source: "book" },
          { price: 11, qty: -3, source: "book" },
        ]),
      ],
    });
    expect(tape[0].side).toBe("buy");
    expect(tape[0].qty).toBe(5);
    expect(tape[1].side).toBe("sell");
    expect(tape[1].qty).toBe(3);
  });
});

describe("windowRows", () => {
  const rows = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((ts) => ({ ts }));

  it("returns empty slice for empty rows", () => {
    expect(windowRows([], 0, 5)).toEqual({ slice: [], highlightIndex: -1 });
  });

  it("centers around the nearest ts", () => {
    const { slice, highlightIndex } = windowRows(rows, 500, 5);
    expect(slice.map((r) => r.ts)).toEqual([300, 400, 500, 600, 700]);
    expect(highlightIndex).toBe(2);
  });

  it("clamps at the start", () => {
    const { slice, highlightIndex } = windowRows(rows, 0, 5);
    expect(slice.map((r) => r.ts)).toEqual([0, 100, 200, 300, 400]);
    expect(highlightIndex).toBe(0);
  });

  it("clamps at the end", () => {
    const { slice, highlightIndex } = windowRows(rows, 900, 5);
    expect(slice.map((r) => r.ts)).toEqual([500, 600, 700, 800, 900]);
    expect(highlightIndex).toBe(4);
  });

  it("handles a window bigger than the array", () => {
    const { slice, highlightIndex } = windowRows(rows, 400, 50);
    expect(slice.length).toBe(10);
    expect(highlightIndex).toBe(4);
  });

  it("snaps to nearest neighbor when ts falls between rows", () => {
    const { highlightIndex } = windowRows(rows, 230, 5);
    // 230 is closer to 200 (diff 30) than to 300 (diff 70), so center is
    // index 2 and with size=5 the slice is [0,100,200,300,400], highlight=2.
    expect(highlightIndex).toBe(2);
  });
});

describe("computeTotals", () => {
  function ev(ts: number, pnl: number, position: number, orders: number[] = []): EventRecord {
    return {
      ...mkEvent(ts),
      actions: { orders: orders.map((p) => ({ price: p, qty: 1 })) },
      pnl: { cash: 0, mark: 0, total: pnl },
      state: { ...mkEvent(ts).state, position },
    };
  }

  it("returns zeros for empty input", () => {
    expect(computeTotals({}, 0)).toEqual({
      pnlTotal: 0,
      exposure: 0,
      activeProducts: 0,
    });
  });

  it("sums pnl and abs positions across products", () => {
    const totals = computeTotals(
      {
        KELP: [ev(0, 100, 20)],
        EMERALDS: [ev(0, -30, -10)],
      },
      0
    );
    expect(totals.pnlTotal).toBe(70);
    expect(totals.exposure).toBe(30);
    expect(totals.activeProducts).toBe(2);
  });

  it("counts activeProducts by position or orders", () => {
    const totals = computeTotals(
      {
        KELP: [ev(0, 0, 0)],
        EMERALDS: [ev(0, 0, 0, [100])],
        SHELLS: [ev(0, 0, 5)],
      },
      0
    );
    expect(totals.activeProducts).toBe(2);
  });

  it("snaps each product's timeline independently", () => {
    const totals = computeTotals(
      {
        KELP: [ev(0, 5, 1), ev(200, 10, 2)],
        EMERALDS: [ev(100, 3, 1)],
      },
      150
    );
    // KELP snaps to 200 (pnl 10, pos 2); EMERALDS snaps to 100 (pnl 3, pos 1)
    expect(totals.pnlTotal).toBe(13);
    expect(totals.exposure).toBe(3);
  });

  it("skips products with no events at all", () => {
    const totals = computeTotals(
      {
        KELP: [ev(0, 5, 1)],
        EMPTY: [],
      },
      0
    );
    expect(totals.pnlTotal).toBe(5);
    expect(totals.activeProducts).toBe(1);
  });
});

describe("buildTickMarks", () => {
  it("returns [] for empty events", () => {
    expect(buildTickMarks([])).toEqual([]);
  });

  it("returns all timestamps when events fit under the count", () => {
    const small = [0, 50, 100].map(mkEvent);
    expect(buildTickMarks(small, 10)).toEqual([0, 50, 100]);
  });

  it("always includes first and last event ts", () => {
    const ticks = buildTickMarks(events, 3);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBe(500);
  });

  it("returns ~count ticks for a large event array", () => {
    const large = Array.from({ length: 1000 }, (_, i) => mkEvent(i * 100));
    const ticks = buildTickMarks(large, 10);
    expect(ticks.length).toBeLessThanOrEqual(10);
    expect(ticks.length).toBeGreaterThanOrEqual(9);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBe(99900);
  });

  it("de-duplicates when rounding collapses adjacent ticks", () => {
    // Two events + ask for 10 ticks: we can only produce 2 unique values.
    const two = [0, 100].map(mkEvent);
    expect(buildTickMarks(two, 10)).toEqual([0, 100]);
  });

  it("returns ticks in ascending order", () => {
    const ticks = buildTickMarks(events, 5);
    for (let i = 1; i < ticks.length; i++) {
      expect(ticks[i]).toBeGreaterThan(ticks[i - 1]);
    }
  });
});
