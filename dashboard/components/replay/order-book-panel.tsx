"use client";

import { Card, CardHeader } from "@/components/ui/card";
import { depthLevels } from "@/lib/replay";
import type { EventRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

export function OrderBookPanel({
  event,
  loading = false,
}: {
  event: EventRecord | null;
  loading?: boolean;
}) {
  if (!event) {
    return (
      <Card>
        <CardHeader>order book</CardHeader>
        <div className="text-sm text-muted-fg">
          {loading ? "loading full-resolution book…" : "no event at this timestamp"}
        </div>
      </Card>
    );
  }

  const { bids, asks } = depthLevels(event.state.order_depth);
  const bestAsk = asks.length > 0 ? asks[0].price : null;
  const bestBid = bids.length > 0 ? bids[0].price : null;
  const spread = bestAsk !== null && bestBid !== null ? bestAsk - bestBid : null;
  const mid = bestAsk !== null && bestBid !== null ? (bestAsk + bestBid) / 2 : null;

  const ourOrders = event.actions.orders;
  const fills = event.fills;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-baseline justify-between">
          <span>order book</span>
          <span className="font-mono text-xs text-muted-fg">
            ts {event.ts} · pos {event.state.position}
            {mid !== null && ` · mid ${mid}`}
          </span>
        </div>
      </CardHeader>

      <DepthChart bids={bids} asks={asks} spread={spread} />

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-fg">
            our orders
          </div>
          {ourOrders.length === 0 ? (
            <div className="font-mono text-xs text-muted-fg">—</div>
          ) : (
            <div className="space-y-0.5">
              {ourOrders.map((o, i) => (
                <OurOrderRow key={i} qty={o.qty} price={o.price} />
              ))}
            </div>
          )}
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-fg">fills</div>
          {fills.length === 0 ? (
            <div className="font-mono text-xs text-muted-fg">—</div>
          ) : (
            <div className="space-y-0.5">
              {fills.map((f, i) => (
                <FillRow key={i} qty={f.qty} price={f.price} source={f.source} />
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

interface Level {
  price: number;
  qty: number;
}

function DepthChart({
  bids,
  asks,
  spread,
}: {
  bids: Level[];
  asks: Level[];
  spread: number | null;
}) {
  if (bids.length === 0 && asks.length === 0) {
    return <div className="text-center text-sm text-muted-fg">empty book</div>;
  }

  const allQtys = [...bids.map((l) => l.qty), ...asks.map((l) => l.qty)];
  const maxQty = Math.max(1, ...allQtys);

  // Stack: asks (highest → best, top-down) then spread line then bids (best → lowest).
  const asksDesc = [...asks].reverse();

  const rowH = 18;
  const rowPad = 2;
  const labelW = 64;
  const centerGap = 8;
  const totalRows = asksDesc.length + bids.length;
  const spreadRowH = 22;
  const svgH = totalRows * (rowH + rowPad) + spreadRowH + 4;

  // Full width drives the visual bar max; we read it from a CSS var on the
  // wrapper and use an SVG viewBox for responsive scaling.
  const viewBoxW = 400;
  const barAreaW = (viewBoxW - centerGap) / 2 - labelW / 2;
  const centerX = viewBoxW / 2;

  let y = 0;
  const nodes: React.ReactNode[] = [];

  for (const level of asksDesc) {
    const w = (level.qty / maxQty) * barAreaW;
    nodes.push(
      <DepthRow
        key={`ask-${level.price}`}
        side="ask"
        y={y}
        rowH={rowH}
        labelW={labelW}
        centerX={centerX}
        centerGap={centerGap}
        width={w}
        level={level}
      />
    );
    y += rowH + rowPad;
  }

  // Spread divider
  nodes.push(
    <g key="spread" transform={`translate(0, ${y})`}>
      <line
        x1="0"
        x2={viewBoxW}
        y1={spreadRowH / 2}
        y2={spreadRowH / 2}
        stroke="hsl(var(--border))"
        strokeDasharray="3 3"
      />
      <text
        x={centerX}
        y={spreadRowH / 2 + 4}
        textAnchor="middle"
        className="fill-muted-fg"
        style={{ fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase" }}
      >
        spread {spread !== null ? spread : "—"}
      </text>
    </g>
  );
  y += spreadRowH;

  for (const level of bids) {
    const w = (level.qty / maxQty) * barAreaW;
    nodes.push(
      <DepthRow
        key={`bid-${level.price}`}
        side="bid"
        y={y}
        rowH={rowH}
        labelW={labelW}
        centerX={centerX}
        centerGap={centerGap}
        width={w}
        level={level}
      />
    );
    y += rowH + rowPad;
  }

  return (
    <div className="mx-auto max-w-md">
      <svg
        viewBox={`0 0 ${viewBoxW} ${svgH}`}
        width="100%"
        height={svgH}
        className="overflow-visible font-mono"
        role="img"
        aria-label="order book depth"
      >
        {nodes}
      </svg>
    </div>
  );
}

function DepthRow({
  side,
  y,
  rowH,
  labelW,
  centerX,
  centerGap,
  width,
  level,
}: {
  side: "bid" | "ask";
  y: number;
  rowH: number;
  labelW: number;
  centerX: number;
  centerGap: number;
  width: number;
  level: Level;
}) {
  const color = side === "bid" ? "hsl(var(--buy))" : "hsl(var(--sell))";
  const barX =
    side === "bid"
      ? centerX - centerGap / 2 - labelW / 2 - width
      : centerX + centerGap / 2 + labelW / 2;
  const priceX =
    side === "bid" ? centerX - centerGap / 2 - labelW / 2 : centerX + centerGap / 2 + labelW / 2;
  const priceAnchor: "start" | "end" = side === "bid" ? "end" : "start";
  const qtyX = side === "bid" ? barX - 4 : barX + width + 4;
  const qtyAnchor: "start" | "end" = side === "bid" ? "end" : "start";

  return (
    <g transform={`translate(0, ${y})`}>
      <rect
        x={barX}
        y={2}
        width={Math.max(1, width)}
        height={rowH - 4}
        fill={color}
        opacity={0.35}
        rx={2}
      />
      <text
        x={priceX}
        y={rowH / 2 + 4}
        textAnchor={priceAnchor}
        fill={color}
        style={{ fontSize: 11 }}
      >
        {level.price}
      </text>
      <text
        x={qtyX}
        y={rowH / 2 + 4}
        textAnchor={qtyAnchor}
        className="fill-muted-fg"
        style={{ fontSize: 10 }}
      >
        {level.qty}
      </text>
    </g>
  );
}

function OurOrderRow({ qty, price }: { qty: number; price: number }) {
  const side = qty > 0 ? "buy" : "sell";
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_auto_1fr] gap-2 font-mono text-xs tabular-nums",
        side === "buy" ? "text-buy" : "text-sell"
      )}
    >
      <span className="w-10">{qty > 0 ? "BUY" : "SELL"}</span>
      <span className="w-8 text-right">{Math.abs(qty)}</span>
      <span>@ {price}</span>
    </div>
  );
}

function FillRow({ qty, price, source }: { qty: number; price: number; source: string }) {
  const side = qty > 0 ? "buy" : "sell";
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_auto_1fr_auto] gap-2 font-mono text-xs tabular-nums",
        side === "buy" ? "text-buy" : "text-sell"
      )}
    >
      <span className="w-10">{qty > 0 ? "BOUGHT" : "SOLD"}</span>
      <span className="w-8 text-right">{Math.abs(qty)}</span>
      <span>@ {price}</span>
      <span className="text-muted-fg">({source})</span>
    </div>
  );
}
