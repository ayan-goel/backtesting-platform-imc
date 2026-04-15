import { describe, expect, it } from "vitest";
import { pickStride, resolveStride } from "@/lib/replay-stride";

describe("pickStride", () => {
  it("returns 1 when count is already under target", () => {
    expect(pickStride(100, 2)).toBe(1);
    expect(pickStride(9_999, 2, 5_000)).toBe(1); // 4999 per product
  });

  it("picks a stride that brings per-product count to target", () => {
    expect(pickStride(50_000, 2, 5_000)).toBe(5); // 25k per product → stride 5
    expect(pickStride(200_000, 2, 5_000)).toBe(20);
  });

  it("rounds up rather than down (no accidental oversampling)", () => {
    // 12k per product, target 5k → ceil(12000/5000) = 3
    expect(pickStride(24_000, 2, 5_000)).toBe(3);
  });

  it("handles degenerate inputs", () => {
    expect(pickStride(0, 2)).toBe(1);
    expect(pickStride(100, 0)).toBe(1);
    expect(pickStride(-5, 2)).toBe(1);
  });
});

describe("resolveStride", () => {
  it("delegates to pickStride for auto", () => {
    expect(resolveStride("auto", 50_000, 2)).toBe(5);
    expect(resolveStride("auto", 100, 2)).toBe(1);
  });

  it("parses numeric choices", () => {
    expect(resolveStride("1", 999_999, 2)).toBe(1);
    expect(resolveStride("5", 100, 2)).toBe(5);
    expect(resolveStride("10", 100, 2)).toBe(10);
    expect(resolveStride("20", 100, 2)).toBe(20);
  });
});
