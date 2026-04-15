"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { CursorOverlay } from "@/components/replay/cursor-overlay";
import { MarketTradeTape } from "@/components/replay/market-trade-tape";
import { OrderBookPanel } from "@/components/replay/order-book-panel";
import { OurTradeTape } from "@/components/replay/our-trade-tape";
import { PlaybackControls } from "@/components/replay/playback-controls";
import { PriceChart } from "@/components/replay/price-chart";
import { ReplayErrorBoundary } from "@/components/replay/replay-error-boundary";
import { TimeSeriesChart } from "@/components/replay/charts";
import { TotalsStrip } from "@/components/replay/totals-strip";
import {
  buildMarketTape,
  buildOurTape,
  buildPriceSeries,
  buildTickMarks,
  isInputFocused,
  snapToNearestTs,
  stepTs,
} from "@/lib/replay";
import {
  RESOLUTION_CHOICES,
  resolveStride,
  type ResolutionChoice,
} from "@/lib/replay-stride";
import { usePlayback } from "@/lib/use-playback";
import type { EventRecord } from "@/lib/types";

export function ReplayView({
  runId,
  products,
  expectedNumEvents,
  finalPnlByProduct,
}: {
  runId: string;
  products: string[];
  expectedNumEvents?: number;
  finalPnlByProduct?: Record<string, number>;
}) {
  return (
    <ReplayErrorBoundary>
      <ReplayViewInner
        runId={runId}
        products={products}
        expectedNumEvents={expectedNumEvents}
        finalPnlByProduct={finalPnlByProduct}
      />
    </ReplayErrorBoundary>
  );
}

function ReplayViewInner({
  runId,
  products,
  expectedNumEvents,
  finalPnlByProduct,
}: {
  runId: string;
  products: string[];
  expectedNumEvents?: number;
  finalPnlByProduct?: Record<string, number>;
}) {
  const [product, setProduct] = useQueryState(
    "product",
    parseAsString.withDefault(products[0] ?? "")
  );
  const [ts, setTs] = useQueryState("ts", parseAsInteger.withDefault(0));
  const [res, setRes] = useQueryState(
    "res",
    parseAsString.withDefault("auto")
  );
  const resolutionChoice: ResolutionChoice = (
    (RESOLUTION_CHOICES as readonly string[]).includes(res) ? res : "auto"
  ) as ResolutionChoice;

  // Two live cursor sources layered on top of the committed nuqs ts:
  //   dragTs:         raw scrubber value while the user is dragging.
  //   playbackCursor: raw rAF-driven value while playback is running.
  // The overlay line reads `cursorTs` so it moves smoothly in both cases.
  // Data consumers (book panel, tapes, totals, charts) keep reading `ts`
  // and only re-render when a new event boundary is crossed.
  const [dragTs, setDragTs] = useState<number | null>(null);
  const [playbackCursor, setPlaybackCursor] = useState<number | null>(null);
  const cursorTs = playbackCursor ?? dragTs ?? ts;

  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);

  const [allEvents, setAllEvents] = useState<Record<string, EventRecord[]>>({});
  const [bookEvents, setBookEvents] = useState<EventRecord[]>([]);
  const [bookLoading, setBookLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stride picker: target ~5000 points per product in charts/tapes. The
  // order book panel reads from a separate full-res stream scoped to the
  // current product so the book always reflects the exact snapped ts.
  const stride = useMemo(
    () => resolveStride(resolutionChoice, expectedNumEvents ?? 0, products.length),
    [resolutionChoice, expectedNumEvents, products.length]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      const url = `/api/runs/${encodeURIComponent(runId)}/events${stride > 1 ? `?stride=${stride}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`events fetch failed: ${res.status}`);
      const text = await res.text();
      const map: Record<string, EventRecord[]> = {};
      for (const p of products) map[p] = [];
      for (const line of text.split("\n")) {
        if (!line) continue;
        const record = JSON.parse(line) as EventRecord;
        const bucket = map[record.product];
        if (bucket) bucket.push(record);
      }
      return map;
    })()
      .then((map) => {
        if (cancelled) return;
        setAllEvents(map);
        setLoading(false);

        const first = map[products[0] ?? ""] ?? [];
        if (first.length > 0) {
          const snapped = snapToNearestTs(first, ts);
          if (snapped !== ts) setTs(snapped);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, products, stride]);

  const events = useMemo(() => allEvents[product] ?? [], [allEvents, product]);

  // Full-resolution per-product stream for the order book panel. Loads in
  // parallel with the strided bundle and refetches on product change.
  useEffect(() => {
    if (!product) return;
    let cancelled = false;
    setBookLoading(true);
    (async () => {
      const res = await fetch(
        `/api/runs/${encodeURIComponent(runId)}/events?product=${encodeURIComponent(product)}`
      );
      if (!res.ok) throw new Error(`book events fetch failed: ${res.status}`);
      const text = await res.text();
      const out: EventRecord[] = [];
      for (const line of text.split("\n")) {
        if (!line) continue;
        out.push(JSON.parse(line) as EventRecord);
      }
      return out;
    })()
      .then((arr) => {
        if (cancelled) return;
        setBookEvents(arr);
        setBookLoading(false);
      })
      .catch(() => {
        if (!cancelled) setBookLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, product]);

  const bookTsToEvent = useMemo(() => {
    const m = new Map<number, EventRecord>();
    for (const e of bookEvents) m.set(e.ts, e);
    return m;
  }, [bookEvents]);

  const tsToEvent = useMemo(() => {
    const m = new Map<number, EventRecord>();
    for (const e of events) m.set(e.ts, e);
    return m;
  }, [events]);

  // Live cursor: updates every drag frame. Used by the book panel and
  // scrubber display span only (both cheap to re-render).
  const snappedCursorTs = useMemo(
    () => snapToNearestTs(events, cursorTs),
    [events, cursorTs]
  );
  // The book panel prefers the full-res stream so it shows the exact
  // snapped ts. Falls back to the strided map if the book fetch hasn't
  // landed yet or an exact match isn't available.
  const displayEvent = useMemo(() => {
    if (bookEvents.length > 0) {
      const snapped = snapToNearestTs(bookEvents, cursorTs);
      return bookTsToEvent.get(snapped) ?? null;
    }
    if (events.length === 0) return null;
    return tsToEvent.get(snappedCursorTs) ?? null;
  }, [bookEvents, bookTsToEvent, events.length, snappedCursorTs, tsToEvent, cursorTs]);

  // Committed cursor: only updates when ts changes (release, keyboard,
  // playback tick). Everything expensive reads this.
  const snappedTs = useMemo(() => snapToNearestTs(events, ts), [events, ts]);
  const committedEvent = useMemo(() => {
    if (bookEvents.length > 0) {
      const snapped = snapToNearestTs(bookEvents, ts);
      return bookTsToEvent.get(snapped) ?? null;
    }
    if (events.length === 0) return null;
    return tsToEvent.get(snappedTs) ?? null;
  }, [bookEvents, bookTsToEvent, events.length, snappedTs, tsToEvent, ts]);

  const pnlPoints = useMemo(
    () => events.map((e) => ({ ts: e.ts, value: e.pnl.total })),
    [events]
  );
  const positionPoints = useMemo(
    () => events.map((e) => ({ ts: e.ts, value: e.state.position })),
    [events]
  );
  const priceSeries = useMemo(() => buildPriceSeries(events), [events]);
  const marketTape = useMemo(() => buildMarketTape(allEvents), [allEvents]);
  const ourTape = useMemo(() => buildOurTape(allEvents), [allEvents]);

  const tsMin = events[0]?.ts ?? 0;
  const tsMax = events[events.length - 1]?.ts ?? 0;
  const tickMarks = useMemo(() => buildTickMarks(events, 10), [events]);
  const finalPnlForProduct = finalPnlByProduct?.[product];

  usePlayback({
    events,
    ts,
    setTs,
    setPlaybackCursor,
    isPlaying,
    onEnd: () => setIsPlaying(false),
    speed,
  });

  // Keyboard shortcuts: space play/pause, ← → step, home/end jump.
  // Ref mirror avoids re-binding on every state change.
  const kbdRef = useRef({ events, ts });
  kbdRef.current = { events, ts };
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isInputFocused()) return;
      const { events: evs, ts: current } = kbdRef.current;
      if (evs.length === 0) return;

      if (e.code === "Space") {
        e.preventDefault();
        setIsPlaying((p) => !p);
        return;
      }
      if (e.code === "ArrowLeft") {
        e.preventDefault();
        setIsPlaying(false);
        setTs(stepTs(evs, current, -1));
        return;
      }
      if (e.code === "ArrowRight") {
        e.preventDefault();
        setIsPlaying(false);
        setTs(stepTs(evs, current, 1));
        return;
      }
      if (e.code === "Home") {
        e.preventDefault();
        setIsPlaying(false);
        setTs(evs[0].ts);
        return;
      }
      if (e.code === "End") {
        e.preventDefault();
        setIsPlaying(false);
        setTs(evs[evs.length - 1].ts);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setTs]);

  const onPlayPause = useCallback(() => {
    setIsPlaying((p) => {
      if (p) return false;
      if (events.length > 0 && ts === events[events.length - 1].ts) {
        setTs(events[0].ts);
      }
      return true;
    });
  }, [events, ts, setTs]);

  // When playback stops (user pause, keyboard Space, end-of-run), commit the
  // live rAF cursor back to `ts` so the URL + idle state reflect where the
  // user left off. Clearing playbackCursor is what drops cursorTs back down
  // to `ts` on the next render.
  useEffect(() => {
    if (!isPlaying && playbackCursor !== null) {
      const snapped = snapToNearestTs(events, playbackCursor);
      if (snapped !== ts) setTs(snapped);
      setPlaybackCursor(null);
    }
  }, [isPlaying, playbackCursor, events, ts, setTs]);

  // Callbacks handed to memoized children. Stable identities during drag so
  // React.memo sees identical props and skips rendering.
  const onJump = useCallback(
    (newTs: number) => setTs(snapToNearestTs(events, newTs)),
    [events, setTs]
  );

  const onProductChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setIsPlaying(false);
      setProduct(e.target.value);
    },
    [setProduct]
  );

  const onScrubberChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setDragTs(Number(e.target.value));
    },
    []
  );

  const commitDrag = useCallback(() => {
    setDragTs((drag) => {
      if (drag !== null) {
        setTs(snapToNearestTs(events, drag));
      }
      return null;
    });
  }, [events, setTs]);

  const totalLoadedEvents = useMemo(
    () => Object.values(allEvents).reduce((acc, arr) => acc + arr.length, 0),
    [allEvents]
  );
  // When stride > 1 the loaded count is intentionally smaller than the
  // server-reported total, so only flag a mismatch on stride=1.
  const eventCountMismatch =
    !loading &&
    stride === 1 &&
    expectedNumEvents !== undefined &&
    totalLoadedEvents !== expectedNumEvents;

  if (error) {
    return (
      <div className="rounded-card border border-sell/40 bg-sell/5 p-4 text-sm text-sell">
        {error}
      </div>
    );
  }

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (events.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-fg">
        no events for {product}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {eventCountMismatch && (
        <div className="rounded-card border border-warn/60 bg-warn/10 px-4 py-2 text-xs text-warn">
          event count mismatch: summary says {expectedNumEvents}, loaded{" "}
          {totalLoadedEvents}. the run may be truncated or filtered.
        </div>
      )}

      <TotalsStrip
        event={committedEvent}
        product={product}
        finalPnl={finalPnlForProduct}
      />

      <Card>
        <div className="grid gap-4 md:grid-cols-[auto_1fr] md:items-end">
          <div className="flex items-end gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                product
              </span>
              <Select
                mono
                value={product}
                onChange={onProductChange}
                className="w-auto min-w-[8rem]"
              >
                {products.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span
                className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg"
                title={`current stride: ${stride}`}
              >
                resolution
              </span>
              <Select
                mono
                value={resolutionChoice}
                onChange={(e) => setRes(e.target.value as ResolutionChoice)}
                className="w-auto min-w-[7rem]"
                aria-label="chart resolution"
              >
                {RESOLUTION_CHOICES.map((c) => (
                  <option key={c} value={c}>
                    {c === "auto" ? `auto (${stride}x)` : `${c}x`}
                  </option>
                ))}
              </Select>
            </label>
            <PlaybackControls
              isPlaying={isPlaying}
              onPlayPause={onPlayPause}
              speed={speed}
              onSpeedChange={setSpeed}
            />
          </div>

          <div>
            <div className="flex items-baseline justify-between">
              <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                timestamp
              </div>
              <div className="font-mono text-sm tabular-nums">
                {snappedCursorTs}
                <span className="ml-2 text-xs text-muted-fg">/ {tsMax}</span>
              </div>
            </div>
            <input
              type="range"
              min={tsMin}
              max={tsMax}
              value={cursorTs}
              onChange={onScrubberChange}
              onPointerDown={() => setIsPlaying(false)}
              onPointerUp={commitDrag}
              onPointerCancel={commitDrag}
              aria-label="timestamp scrubber"
              role="slider"
              aria-valuemin={tsMin}
              aria-valuemax={tsMax}
              aria-valuenow={snappedCursorTs}
              className="replay-scrubber mt-2 h-2 w-full accent-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
            />
            <div
              className="relative mt-1 h-4 w-full text-[10px] text-muted-fg"
              aria-hidden="true"
            >
              {tickMarks.map((t, i) => {
                const isFirst = i === 0;
                const isLast = i === tickMarks.length - 1;
                const pct =
                  tsMax === tsMin ? 0 : ((t - tsMin) / (tsMax - tsMin)) * 100;
                const style: React.CSSProperties = isFirst
                  ? { left: 0 }
                  : isLast
                    ? { right: 0 }
                    : { left: `${pct}%` };
                const translate = isFirst || isLast ? "" : "-translate-x-1/2";
                return (
                  <span
                    key={t}
                    className={`absolute font-mono tabular-nums ${translate}`}
                    style={style}
                  >
                    {t}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader>price · our orders · fills</CardHeader>
        <div className="relative">
          <PriceChart series={priceSeries} onJump={onJump} />
          <CursorOverlay ts={cursorTs} tsMin={tsMin} tsMax={tsMax} />
        </div>
      </Card>

      <OrderBookPanel event={displayEvent} loading={bookLoading} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>pnl</CardHeader>
          <div className="relative">
            <TimeSeriesChart
              points={pnlPoints}
              title=""
              color="hsl(var(--accent))"
              onClick={onJump}
            />
            <CursorOverlay ts={cursorTs} tsMin={tsMin} tsMax={tsMax} />
          </div>
        </Card>

        <Card>
          <CardHeader>position</CardHeader>
          <div className="relative">
            <TimeSeriesChart
              points={positionPoints}
              title=""
              color="hsl(var(--buy))"
              onClick={onJump}
            />
            <CursorOverlay ts={cursorTs} tsMin={tsMin} tsMax={tsMax} />
          </div>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <MarketTradeTape rows={marketTape} currentTs={snappedTs} />
        <OurTradeTape rows={ourTape} currentTs={snappedTs} />
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-16 rounded-card border border-border bg-surface-1/40" />
      <div className="h-24 rounded-card border border-border bg-surface-1/40" />
      <div className="h-64 rounded-card border border-border bg-surface-1/40" />
      <div className="h-56 rounded-card border border-border bg-surface-1/40" />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-52 rounded-card border border-border bg-surface-1/40" />
        <div className="h-52 rounded-card border border-border bg-surface-1/40" />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-48 rounded-card border border-border bg-surface-1/40" />
        <div className="h-48 rounded-card border border-border bg-surface-1/40" />
      </div>
      <div className="mt-2 text-center text-[10px] uppercase tracking-wider text-muted-fg">
        loading replay…
      </div>
    </div>
  );
}
