import { describe, expect, it } from "vitest";
import type { SearchSpace } from "@/lib/types";
import { parseChoices, validateSpace, validateSpec } from "@/lib/study-space";

describe("validateSpec", () => {
  it("accepts a valid int spec", () => {
    expect(validateSpec({ type: "int", low: 0, high: 5 })).toBeNull();
  });

  it("rejects inverted int low/high", () => {
    expect(validateSpec({ type: "int", low: 5, high: 0 })).toMatch(/low/);
  });

  it("rejects zero int step", () => {
    expect(validateSpec({ type: "int", low: 0, high: 5, step: 0 })).toMatch(/step/);
  });

  it("accepts a valid float spec", () => {
    expect(validateSpec({ type: "float", low: 0.0, high: 1.0 })).toBeNull();
  });

  it("rejects NaN float bounds", () => {
    expect(validateSpec({ type: "float", low: NaN, high: 1.0 })).toMatch(/numbers/);
  });

  it("rejects inverted float bounds", () => {
    expect(validateSpec({ type: "float", low: 2.0, high: 1.0 })).toMatch(/low/);
  });

  it("accepts categorical with choices", () => {
    expect(validateSpec({ type: "categorical", choices: ["a", "b"] })).toBeNull();
  });

  it("rejects empty categorical", () => {
    expect(validateSpec({ type: "categorical", choices: [] })).toMatch(/empty/);
  });
});

describe("validateSpace", () => {
  it("rejects empty space", () => {
    const errors = validateSpace({} as SearchSpace);
    expect(errors).toHaveLength(1);
    expect(errors[0].message).toMatch(/empty/);
  });

  it("rejects blank param name", () => {
    const errors = validateSpace({ "  ": { type: "int", low: 0, high: 5 } });
    expect(errors.some((e) => /blank/.test(e.message))).toBe(true);
  });

  it("surfaces per-param errors", () => {
    const space: SearchSpace = {
      edge: { type: "int", low: 10, high: 0 },
      mode: { type: "categorical", choices: [] },
    };
    const errors = validateSpace(space);
    expect(errors).toHaveLength(2);
    expect(errors.map((e) => e.name).sort()).toEqual(["edge", "mode"]);
  });

  it("returns no errors for a valid multi-param space", () => {
    const space: SearchSpace = {
      edge: { type: "int", low: 0, high: 5 },
      aggro: { type: "float", low: 0.0, high: 1.0 },
      mode: { type: "categorical", choices: ["mm", "taker"] },
    };
    expect(validateSpace(space)).toEqual([]);
  });
});

describe("parseChoices", () => {
  it("splits comma-separated and trims", () => {
    expect(parseChoices("a, b,c ,d")).toEqual(["a", "b", "c", "d"]);
  });

  it("drops empties", () => {
    expect(parseChoices("a,,b")).toEqual(["a", "b"]);
  });
});
