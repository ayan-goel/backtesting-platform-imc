// Pure helpers for the replay view. Kept free of React so they can be unit-tested
// (and so re-renders stay cheap via useMemo). Every function takes a pre-sorted
// ascending-by-ts event array and returns a plain value.

import type { EventRecord } from "./types";

/**
 * Find the nearest event timestamp to `ts` in a sorted ascending `events` array.
 *
 * Ties go to the earlier event (the one just before `ts`). If `events` is empty,
 * returns the input `ts` unchanged — the caller is responsible for checking the
 * empty case before using the result.
 *
 * O(log n) binary search.
 */
export function snapToNearestTs(events: readonly EventRecord[], ts: number): number {
  if (events.length === 0) return ts;
  if (ts <= events[0].ts) return events[0].ts;
  const last = events[events.length - 1].ts;
  if (ts >= last) return last;

  let lo = 0;
  let hi = events.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (events[mid].ts <= ts) lo = mid;
    else hi = mid;
  }

  const before = events[lo].ts;
  const after = events[hi].ts;
  // Ties (equal distance) go to `before` so scrubbing left-to-right doesn't
  // skip frames visually.
  return ts - before <= after - ts ? before : after;
}

export interface DepthLevel {
  price: number;
  qty: number; // always positive
}

export interface Depth {
  bids: DepthLevel[]; // descending by price (best bid first)
  asks: DepthLevel[]; // ascending by price (best ask first)
}

/**
 * Parse the engine's order_depth dict into sorted level arrays with positive
 * quantities. Sell volumes are negative ints in the raw log — we abs them.
 */
export function depthLevels(orderDepth: {
  buy: Record<string, number>;
  sell: Record<string, number>;
}): Depth {
  const bids = Object.entries(orderDepth.buy)
    .map(([p, q]) => ({ price: Number(p), qty: Math.abs(q) }))
    .sort((a, b) => b.price - a.price);
  const asks = Object.entries(orderDepth.sell)
    .map(([p, q]) => ({ price: Number(p), qty: Math.abs(q) }))
    .sort((a, b) => a.price - b.price);
  return { bids, asks };
}

/**
 * Compute mid-price from an event's order_depth. Returns null if either side
 * of the book is empty — the caller should draw a gap instead of an invalid
 * point. `sell` volumes in the event log are negative ints; we only need the
 * prices (keys), so the sign doesn't matter here.
 */
export function computeMid(event: EventRecord): number | null {
  const buyPrices = Object.keys(event.state.order_depth.buy).map(Number);
  const sellPrices = Object.keys(event.state.order_depth.sell).map(Number);
  if (buyPrices.length === 0 || sellPrices.length === 0) return null;
  const bestBid = Math.max(...buyPrices);
  const bestAsk = Math.min(...sellPrices);
  return (bestBid + bestAsk) / 2;
}

export interface ChartPoint {
  ts: number;
  value: number;
}

export interface FillPoint {
  ts: number;
  value: number;
  side: "buy" | "sell";
}

export interface PriceSeries {
  mid: ChartPoint[];
  bids: ChartPoint[];
  asks: ChartPoint[];
  fills: FillPoint[];
}

/**
 * Derive the R3 price-chart series from an event array.
 *
 * - `mid` skips events with a one-sided book so the line has gaps instead of
 *   jumping to 0.
 * - `bids` / `asks` enumerate every posted order with its price, keyed by the
 *   event ts.
 * - `fills` attach the side inferred from `qty > 0`.
 */
export function buildPriceSeries(events: readonly EventRecord[]): PriceSeries {
  const mid: ChartPoint[] = [];
  const bids: ChartPoint[] = [];
  const asks: ChartPoint[] = [];
  const fills: FillPoint[] = [];

  for (const e of events) {
    const m = computeMid(e);
    if (m !== null) mid.push({ ts: e.ts, value: m });

    for (const o of e.actions.orders) {
      if (o.qty > 0) bids.push({ ts: e.ts, value: o.price });
      else if (o.qty < 0) asks.push({ ts: e.ts, value: o.price });
    }
    for (const f of e.fills) {
      fills.push({
        ts: e.ts,
        value: f.price,
        side: f.qty > 0 ? "buy" : "sell",
      });
    }
  }

  return { mid, bids, asks, fills };
}

export interface MarketTapeRow {
  ts: number;
  symbol: string;
  price: number;
  qty: number;
  buyer: string | null;
  seller: string | null;
}

/**
 * Flat-map every `state.market_trades` entry across every product's event
 * stream into one sorted, deduped tape. The same market trade appears on
 * every product's event at the same ts, so we key by
 * `(ts, symbol, price, qty, buyer, seller)` and keep the first occurrence.
 */
export function buildMarketTape(
  eventsByProduct: Readonly<Record<string, readonly EventRecord[]>>
): MarketTapeRow[] {
  const seen = new Set<string>();
  const out: MarketTapeRow[] = [];

  for (const events of Object.values(eventsByProduct)) {
    for (const e of events) {
      for (const t of e.state.market_trades) {
        const buyer = t.buyer ?? null;
        const seller = t.seller ?? null;
        // Market trades are already tagged with their own symbol in the P4
        // raw data, but the event log strips that — we recover it from the
        // event's product, which is correct for any trade that appears here.
        const symbol = e.product;
        const key = `${e.ts}|${symbol}|${t.price}|${t.qty}|${String(buyer)}|${String(seller)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ ts: e.ts, symbol, price: t.price, qty: t.qty, buyer, seller });
      }
    }
  }

  out.sort((a, b) => (a.ts !== b.ts ? a.ts - b.ts : a.symbol.localeCompare(b.symbol)));
  return out;
}

export interface OurTapeRow {
  ts: number;
  symbol: string;
  side: "buy" | "sell";
  price: number;
  qty: number;
  source: string;
  cumulativePosition: number;
}

/**
 * Our fills across all products, in chronological order, annotated with a
 * per-product running position so you can see "we became long 30 EMERALDS
 * at ts 12345". Fills within a single event keep their original order.
 */
export function buildOurTape(
  eventsByProduct: Readonly<Record<string, readonly EventRecord[]>>
): OurTapeRow[] {
  const out: OurTapeRow[] = [];
  for (const [symbol, events] of Object.entries(eventsByProduct)) {
    for (const e of events) {
      for (const f of e.fills) {
        out.push({
          ts: e.ts,
          symbol,
          side: f.qty > 0 ? "buy" : "sell",
          price: f.price,
          qty: Math.abs(f.qty),
          source: f.source,
          cumulativePosition: 0, // filled in below
        });
      }
    }
  }

  out.sort((a, b) => {
    if (a.ts !== b.ts) return a.ts - b.ts;
    return a.symbol.localeCompare(b.symbol);
  });

  // Running position per symbol, after sorting so the cumulative reflects
  // the displayed order.
  const position: Record<string, number> = {};
  for (const row of out) {
    const signed = row.side === "buy" ? row.qty : -row.qty;
    position[row.symbol] = (position[row.symbol] ?? 0) + signed;
    row.cumulativePosition = position[row.symbol];
  }
  return out;
}

/**
 * Return a window of `size` rows centered on the row whose ts is closest to
 * `currentTs`. The returned slice is clamped at array bounds, and the second
 * tuple element is the index of the "current" row within that slice (or -1
 * if `rows` is empty).
 */
export function windowRows<T extends { ts: number }>(
  rows: readonly T[],
  currentTs: number,
  size: number = 50
): { slice: T[]; highlightIndex: number } {
  if (rows.length === 0) return { slice: [], highlightIndex: -1 };

  // Binary search for the row whose ts is closest to currentTs (first row
  // whose ts >= currentTs; then pick whichever neighbor is closer).
  let lo = 0;
  let hi = rows.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].ts < currentTs) lo = mid + 1;
    else hi = mid;
  }
  let centerIdx = lo;
  if (centerIdx === rows.length) centerIdx = rows.length - 1;
  if (centerIdx > 0) {
    const here = rows[centerIdx].ts;
    const prev = rows[centerIdx - 1].ts;
    if (Math.abs(prev - currentTs) < Math.abs(here - currentTs)) centerIdx -= 1;
  }

  const half = Math.floor(size / 2);
  let start = centerIdx - half;
  let end = start + size;
  if (start < 0) {
    end -= start;
    start = 0;
  }
  if (end > rows.length) {
    start = Math.max(0, rows.length - size);
    end = rows.length;
  }

  return {
    slice: rows.slice(start, end),
    highlightIndex: centerIdx - start,
  };
}

export interface ReplayTotals {
  pnlTotal: number;
  exposure: number; // sum of |position| across products with an event at ts
  activeProducts: number; // products with non-zero position OR at least one order
}

/**
 * Compute cross-product totals at a specific ts by snapping each product's
 * timeline to its nearest event and summing. Products with no events at all
 * contribute nothing.
 */
export function computeTotals(
  eventsByProduct: Readonly<Record<string, readonly EventRecord[]>>,
  currentTs: number
): ReplayTotals {
  let pnlTotal = 0;
  let exposure = 0;
  let activeProducts = 0;

  for (const events of Object.values(eventsByProduct)) {
    if (events.length === 0) continue;
    const snapped = snapToNearestTs(events, currentTs);
    // Find the event at the snapped ts. snapped is guaranteed to be an exact
    // match (unless events is empty, which we've already guarded).
    const event = events.find((e) => e.ts === snapped);
    if (!event) continue;
    pnlTotal += event.pnl.total;
    exposure += Math.abs(event.state.position);
    if (event.state.position !== 0 || event.actions.orders.length > 0) {
      activeProducts += 1;
    }
  }

  return { pnlTotal, exposure, activeProducts };
}

/**
 * Return the ts of the event one step before/after the current one.
 *
 * Clamps at the ends (stepping past the last event returns the last event).
 * Runs `snapToNearestTs` first so callers can pass raw drag values safely.
 */
export function stepTs(
  events: readonly EventRecord[],
  current: number,
  dir: 1 | -1
): number {
  if (events.length === 0) return current;
  const snapped = snapToNearestTs(events, current);
  const idx = events.findIndex((e) => e.ts === snapped);
  if (idx === -1) return snapped;
  const nextIdx = Math.max(0, Math.min(events.length - 1, idx + dir));
  return events[nextIdx].ts;
}

/**
 * True when the document's active element is a text/select/editable input
 * that should absorb keyboard shortcuts. Range inputs (scrubbers) are
 * explicitly allowed to pass through so global arrow-key stepping works
 * whether or not the slider has focus. SSR-safe.
 */
export function isInputFocused(): boolean {
  if (typeof document === "undefined") return false;
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT") {
    return (el as HTMLInputElement).type !== "range";
  }
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return false;
}

/**
 * Pick ~`count` evenly-spaced timestamps from `events` to use as axis tick marks.
 *
 * Always includes the first and last event. Returns at most `events.length`
 * ticks (so a 3-event run doesn't get 10 duplicate labels).
 */
export function buildTickMarks(
  events: readonly EventRecord[],
  count: number = 10
): number[] {
  if (events.length === 0) return [];
  if (events.length <= count) return events.map((e) => e.ts);

  const ticks: number[] = [];
  const step = (events.length - 1) / (count - 1);
  for (let i = 0; i < count; i++) {
    const idx = Math.round(i * step);
    ticks.push(events[idx].ts);
  }
  // De-dupe in case rounding collapses adjacent ticks.
  return Array.from(new Set(ticks));
}
