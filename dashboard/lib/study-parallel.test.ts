import { describe, expect, it } from "vitest";
import type { SearchSpace, StudyTrialSummary } from "@/lib/types";
import {
  buildAxisDomains,
  buildRankMap,
  normalizeAxis,
  rankToColor,
  type Axis,
} from "@/lib/study-parallel";

function trial(
  number: number,
  value: number | null,
  params: Record<string, unknown> = {}
): StudyTrialSummary {
  return {
    trial_number: number,
    status: "succeeded",
    value,
    params,
    run_id: `run-${number}`,
    duration_ms: 100,
  };
}

describe("buildAxisDomains", () => {
  it("builds a numeric axis for each int / float spec + trailing objective", () => {
    const space: SearchSpace = {
      edge: { type: "int", low: 0, high: 5 },
      aggro: { type: "float", low: 0.0, high: 1.0 },
    };
    const trials = [trial(0, 10), trial(1, 20), trial(2, 30)];
    const axes = buildAxisDomains(space, trials, "pnl_total");
    expect(axes).toHaveLength(3);
    expect(axes[0]).toEqual({ kind: "numeric", name: "edge", domain: [0, 5] });
    expect(axes[1]).toEqual({ kind: "numeric", name: "aggro", domain: [0, 1] });
    expect(axes[2].kind).toBe("numeric");
    expect(axes[2].name).toBe("pnl_total");
    expect(axes[2].domain).toEqual([10, 30]);
  });

  it("builds a categorical axis preserving choice order", () => {
    const space: SearchSpace = {
      mode: { type: "categorical", choices: ["mm", "taker", "hybrid"] },
    };
    const axes = buildAxisDomains(space, [], "pnl_total");
    expect(axes[0]).toEqual({
      kind: "categorical",
      name: "mode",
      categories: ["mm", "taker", "hybrid"],
    });
  });

  it("widens the objective axis when all trial values are equal", () => {
    const space: SearchSpace = { edge: { type: "int", low: 0, high: 5 } };
    const trials = [trial(0, 5), trial(1, 5)];
    const axes = buildAxisDomains(space, trials, "pnl_total");
    expect(axes[1].domain).toEqual([4, 6]);
  });

  it("falls back to [0, 1] when no values exist", () => {
    const axes = buildAxisDomains({ edge: { type: "int", low: 0, high: 5 } }, [], "pnl_total");
    expect(axes[1].domain).toEqual([0, 1]);
  });
});

describe("normalizeAxis", () => {
  it("maps numeric to [0, 1]", () => {
    const axis: Axis = { kind: "numeric", name: "x", domain: [0, 10] };
    expect(normalizeAxis(axis, 0)).toBe(0);
    expect(normalizeAxis(axis, 10)).toBe(1);
    expect(normalizeAxis(axis, 5)).toBe(0.5);
  });

  it("clamps out-of-range numeric values", () => {
    const axis: Axis = { kind: "numeric", name: "x", domain: [0, 10] };
    expect(normalizeAxis(axis, -5)).toBe(0);
    expect(normalizeAxis(axis, 15)).toBe(1);
  });

  it("handles degenerate numeric domain", () => {
    const axis: Axis = { kind: "numeric", name: "x", domain: [5, 5] };
    expect(normalizeAxis(axis, 5)).toBe(0.5);
  });

  it("returns null for non-numeric numeric input", () => {
    const axis: Axis = { kind: "numeric", name: "x", domain: [0, 10] };
    expect(normalizeAxis(axis, "abc")).toBeNull();
    expect(normalizeAxis(axis, NaN)).toBeNull();
  });

  it("maps categorical by index", () => {
    const axis: Axis = {
      kind: "categorical",
      name: "mode",
      categories: ["a", "b", "c"],
    };
    expect(normalizeAxis(axis, "a")).toBe(0);
    expect(normalizeAxis(axis, "b")).toBe(0.5);
    expect(normalizeAxis(axis, "c")).toBe(1);
  });

  it("returns null for unknown categorical values", () => {
    const axis: Axis = {
      kind: "categorical",
      name: "mode",
      categories: ["a", "b"],
    };
    expect(normalizeAxis(axis, "z")).toBeNull();
  });
});

describe("buildRankMap", () => {
  it("ranks trials maximizing", () => {
    const trials = [trial(0, 10), trial(1, 30), trial(2, 20)];
    const map = buildRankMap(trials, "maximize");
    expect(map.get(1)).toBe(0); // best
    expect(map.get(2)).toBe(1);
    expect(map.get(0)).toBe(2); // worst
  });

  it("ranks trials minimizing", () => {
    const trials = [trial(0, 10), trial(1, 30), trial(2, 20)];
    const map = buildRankMap(trials, "minimize");
    expect(map.get(0)).toBe(0); // best (lowest)
    expect(map.get(1)).toBe(2);
  });

  it("ignores null / non-finite values", () => {
    const trials = [trial(0, 10), trial(1, null), trial(2, Infinity)];
    const map = buildRankMap(trials, "maximize");
    expect(map.get(0)).toBe(0);
    expect(map.size).toBe(1);
  });
});

describe("rankToColor", () => {
  it("uses buy green for the best trial", () => {
    expect(rankToColor(0, 10, true)).toBe("hsl(var(--buy))");
  });

  it("emits HSL accent strings with rank-based alpha", () => {
    const first = rankToColor(0, 10, false);
    const last = rankToColor(9, 10, false);
    expect(first).toMatch(/hsl\(var\(--accent\)/);
    expect(last).toMatch(/hsl\(var\(--accent\)/);
    // First should be more opaque than last.
    const firstAlpha = Number(first.match(/\/ ([\d.]+)\)/)?.[1]);
    const lastAlpha = Number(last.match(/\/ ([\d.]+)\)/)?.[1]);
    expect(firstAlpha).toBeGreaterThan(lastAlpha);
  });
});
