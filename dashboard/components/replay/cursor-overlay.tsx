"use client";

// Y axis width + right margin + top margin + (X axis height) used by both
// PriceChart and TimeSeriesChart. If you change those recharts props you must
// update these constants too.
const Y_AXIS_WIDTH = 70;
const RIGHT_MARGIN = 16;
const TOP_MARGIN = 8;
const X_AXIS_HEIGHT = 28;

/**
 * A vertical accent line positioned inside the recharts plot area by CSS
 * `calc()`. Absolutely positioned over its container, so the only thing that
 * re-renders when the cursor moves is this one div's `style.left`.
 *
 * The parent is responsible for placing this inside a `relative` wrapper that
 * matches the chart's outer dimensions.
 */
export function CursorOverlay({
  ts,
  tsMin,
  tsMax,
}: {
  ts: number;
  tsMin: number;
  tsMax: number;
}) {
  if (tsMax <= tsMin) return null;
  const clamped = Math.max(tsMin, Math.min(tsMax, ts));
  const pct = ((clamped - tsMin) / (tsMax - tsMin)) * 100;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute w-px bg-accent/80"
      style={{
        left: `calc(${Y_AXIS_WIDTH}px + ${pct} * (100% - ${Y_AXIS_WIDTH + RIGHT_MARGIN}px) / 100)`,
        top: TOP_MARGIN,
        bottom: X_AXIS_HEIGHT,
      }}
    />
  );
}
