"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { parseAsInteger, parseAsString, useQueryState } from "nuqs";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ComparePickers } from "@/components/compare-pickers";
import { CompareSummary } from "@/components/compare-summary";
import { ComparePnlChart, ComparePositionChart } from "@/components/compare-charts";
import { CursorOverlay } from "@/components/replay/cursor-overlay";
import {
  checkCompatibility,
  computeSummaryDelta,
  pairPnlSeries,
  pairPositionSeries,
} from "@/lib/compare";
import { snapToNearestTs } from "@/lib/replay";
import type { EventRecord, RunSummary } from "@/lib/types";

interface Props {
  runs: RunSummary[];
}

type EventMap = Record<string, EventRecord[]>;

type FetchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: EventMap }
  | { status: "error"; message: string };

export function CompareView({ runs }: Props) {
  const runMap = useMemo(() => {
    const m = new Map<string, RunSummary>();
    for (const r of runs) m.set(r._id, r);
    return m;
  }, [runs]);

  const defaultA = runs[0]?._id ?? "";
  const defaultB = runs[1]?._id ?? runs[0]?._id ?? "";

  const [a, setA] = useQueryState("a", parseAsString.withDefault(defaultA));
  const [b, setB] = useQueryState("b", parseAsString.withDefault(defaultB));
  const [product, setProduct] = useQueryState("product", parseAsString.withDefault(""));
  const [ts, setTs] = useQueryState("ts", parseAsInteger.withDefault(0));

  const [dragTs, setDragTs] = useState<number | null>(null);
  const cursorTs = dragTs ?? ts;

  const summaryA = runMap.get(a) ?? null;
  const summaryB = runMap.get(b) ?? null;

  const compatibility = useMemo(() => {
    if (!summaryA || !summaryB) {
      return { compatible: false, reasons: [], sharedProducts: [] as string[] };
    }
    return checkCompatibility(summaryA, summaryB);
  }, [summaryA, summaryB]);

  const delta = useMemo(() => {
    if (!summaryA || !summaryB) return null;
    return computeSummaryDelta(summaryA, summaryB);
  }, [summaryA, summaryB]);

  const onSwap = useCallback(() => {
    const currentA = a;
    const currentB = b;
    setA(currentB);
    setB(currentA);
  }, [a, b, setA, setB]);

  const onChangeA = useCallback((id: string) => setA(id), [setA]);
  const onChangeB = useCallback((id: string) => setB(id), [setB]);

  const [eventsA, setEventsA] = useState<FetchState>({ status: "idle" });
  const [eventsB, setEventsB] = useState<FetchState>({ status: "idle" });

  const sharedProductsKey = compatibility.sharedProducts.join(",");

  useEffect(() => {
    if (!summaryA || compatibility.sharedProducts.length === 0) {
      setEventsA({ status: "idle" });
      return;
    }
    let cancelled = false;
    setEventsA({ status: "loading" });
    Promise.all(
      compatibility.sharedProducts.map(async (p) => {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(summaryA._id)}/events?product=${encodeURIComponent(p)}`
        );
        if (!res.ok) throw new Error(`A events fetch failed: ${res.status}`);
        const text = await res.text();
        const records = text
          .split("\n")
          .filter((line) => line.trim().length > 0)
          .map((line) => JSON.parse(line) as EventRecord);
        return [p, records] as const;
      })
    )
      .then((entries) => {
        if (cancelled) return;
        const map: EventMap = {};
        for (const [p, r] of entries) map[p] = r;
        setEventsA({ status: "ok", data: map });
      })
      .catch((e) => {
        if (!cancelled) setEventsA({ status: "error", message: (e as Error).message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaryA?._id, sharedProductsKey]);

  useEffect(() => {
    if (!summaryB || compatibility.sharedProducts.length === 0) {
      setEventsB({ status: "idle" });
      return;
    }
    let cancelled = false;
    setEventsB({ status: "loading" });
    Promise.all(
      compatibility.sharedProducts.map(async (p) => {
        const res = await fetch(
          `/api/runs/${encodeURIComponent(summaryB._id)}/events?product=${encodeURIComponent(p)}`
        );
        if (!res.ok) throw new Error(`B events fetch failed: ${res.status}`);
        const text = await res.text();
        const records = text
          .split("\n")
          .filter((line) => line.trim().length > 0)
          .map((line) => JSON.parse(line) as EventRecord);
        return [p, records] as const;
      })
    )
      .then((entries) => {
        if (cancelled) return;
        const map: EventMap = {};
        for (const [p, r] of entries) map[p] = r;
        setEventsB({ status: "ok", data: map });
      })
      .catch((e) => {
        if (!cancelled) setEventsB({ status: "error", message: (e as Error).message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaryB?._id, sharedProductsKey]);

  // Pick a default product: first shared one, or the URL param if still valid.
  const effectiveProduct = useMemo(() => {
    if (product && compatibility.sharedProducts.includes(product)) return product;
    return compatibility.sharedProducts[0] ?? "";
  }, [product, compatibility.sharedProducts]);

  useEffect(() => {
    if (effectiveProduct && effectiveProduct !== product) {
      setProduct(effectiveProduct);
    }
  }, [effectiveProduct, product, setProduct]);

  const productEventsA = useMemo(() => {
    if (eventsA.status !== "ok" || !effectiveProduct) return [];
    return eventsA.data[effectiveProduct] ?? [];
  }, [eventsA, effectiveProduct]);
  const productEventsB = useMemo(() => {
    if (eventsB.status !== "ok" || !effectiveProduct) return [];
    return eventsB.data[effectiveProduct] ?? [];
  }, [eventsB, effectiveProduct]);

  const pnlSeries = useMemo(
    () => pairPnlSeries(productEventsA, productEventsB, effectiveProduct),
    [productEventsA, productEventsB, effectiveProduct]
  );
  const positionSeries = useMemo(
    () => pairPositionSeries(productEventsA, productEventsB, effectiveProduct),
    [productEventsA, productEventsB, effectiveProduct]
  );

  const tsDomain = useMemo(() => {
    // Union of ts across both runs' events for this product.
    let min = Infinity;
    let max = -Infinity;
    for (const point of pnlSeries) {
      if (point.ts < min) min = point.ts;
      if (point.ts > max) max = point.ts;
    }
    if (!Number.isFinite(min)) return { min: 0, max: 0 };
    return { min, max };
  }, [pnlSeries]);

  // When the series updates (product switch / new fetch), snap ts into range.
  useEffect(() => {
    if (pnlSeries.length === 0) return;
    const allTs = pnlSeries.map((p) => p.ts);
    if (!allTs.includes(ts)) {
      const snapped = snapToNearestTs(
        allTs.map((t) => ({ ts: t }) as unknown as EventRecord),
        ts
      );
      if (snapped !== ts) setTs(snapped);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pnlSeries]);

  const commitDrag = useCallback(() => {
    setDragTs((drag) => {
      if (drag !== null) setTs(drag);
      return null;
    });
  }, [setTs]);

  if (runs.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no runs to compare — create a few from the runs page first
      </div>
    );
  }

  const chartsLoading =
    compatibility.compatible &&
    (eventsA.status === "loading" || eventsB.status === "loading");
  const chartsError =
    (eventsA.status === "error" && eventsA.message) ||
    (eventsB.status === "error" && eventsB.message) ||
    null;
  const chartsReady =
    compatibility.compatible &&
    eventsA.status === "ok" &&
    eventsB.status === "ok" &&
    pnlSeries.length > 0;

  return (
    <div className="space-y-4">
      <Card>
        <ComparePickers
          runs={runs}
          a={a}
          b={b}
          onChangeA={onChangeA}
          onChangeB={onChangeB}
          onSwap={onSwap}
        />
      </Card>

      {!summaryA || !summaryB ? (
        <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-8 text-center text-sm text-muted-fg">
          pick two runs to compare
        </div>
      ) : (
        <>
          {!compatibility.compatible && (
            <div className="rounded-card border border-warn/60 bg-warn/10 px-4 py-2 text-xs text-warn">
              runs are not directly comparable: {compatibility.reasons.join("; ")}.
              charts will be hidden until you pick a compatible pair.
            </div>
          )}

          {delta && <CompareSummary a={summaryA} b={summaryB} delta={delta} />}

          {compatibility.compatible && (
            <Card>
              <CardHeader>charts</CardHeader>
              <div className="mb-4 flex items-end gap-4">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                    product
                  </span>
                  <Select
                    mono
                    value={effectiveProduct}
                    onChange={(e) => setProduct(e.target.value)}
                    className="w-auto min-w-[8rem]"
                  >
                    {compatibility.sharedProducts.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </Select>
                </label>
                <div className="flex-1">
                  <div className="flex items-baseline justify-between">
                    <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                      timestamp
                    </div>
                    <div className="font-mono text-sm tabular-nums">
                      {cursorTs}
                      <span className="ml-2 text-xs text-muted-fg">/ {tsDomain.max}</span>
                    </div>
                  </div>
                  <input
                    type="range"
                    min={tsDomain.min}
                    max={tsDomain.max || 0}
                    value={cursorTs}
                    onChange={(e) => setDragTs(Number(e.target.value))}
                    onPointerUp={commitDrag}
                    onPointerCancel={commitDrag}
                    aria-label="timestamp scrubber"
                    role="slider"
                    aria-valuemin={tsDomain.min}
                    aria-valuemax={tsDomain.max}
                    aria-valuenow={cursorTs}
                    className="replay-scrubber mt-2 h-2 w-full accent-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  />
                </div>
              </div>

              {chartsLoading && (
                <div className="h-[500px] rounded-card border border-border bg-surface-1/40" />
              )}
              {chartsError && (
                <div className="rounded-card border border-sell/40 bg-sell/5 p-3 text-xs text-sell">
                  {chartsError}
                </div>
              )}
              {chartsReady && (
                <div className="space-y-4">
                  <div className="relative">
                    <ComparePnlChart series={pnlSeries} />
                    <CursorOverlay
                      ts={cursorTs}
                      tsMin={tsDomain.min}
                      tsMax={tsDomain.max}
                    />
                  </div>
                  <div className="relative">
                    <ComparePositionChart series={positionSeries} />
                    <CursorOverlay
                      ts={cursorTs}
                      tsMin={tsDomain.min}
                      tsMax={tsDomain.max}
                    />
                  </div>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
