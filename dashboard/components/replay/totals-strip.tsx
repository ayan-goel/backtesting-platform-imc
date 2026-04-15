"use client";

import { memo } from "react";
import { Card } from "@/components/ui/card";
import { computeMid } from "@/lib/replay";
import type { EventRecord } from "@/lib/types";
import { cn, formatCurrency, formatInt } from "@/lib/utils";

interface TotalsStripProps {
  event: EventRecord | null;
  product: string;
  finalPnl?: number;
}

/**
 * Compact per-product stats shown at the top of the replay view.
 *
 * Reads from the committed event (at the nuqs `ts`, not the drag cursor),
 * so this strip doesn't re-render while the scrubber is being dragged.
 * Shows: current pnl, delta from final, position, open orders, mid.
 */
export const TotalsStrip = memo(function TotalsStrip({
  event,
  product,
  finalPnl,
}: TotalsStripProps) {
  if (!event) {
    return (
      <Card>
        <div className="font-mono text-xs text-muted-fg">no data at cursor</div>
      </Card>
    );
  }

  const pnl = event.pnl.total;
  const position = event.state.position;
  const openOrders = event.actions.orders.length;
  const mid = computeMid(event);
  const delta = finalPnl !== undefined ? finalPnl - pnl : null;

  return (
    <Card>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-5">
        <Stat label="product" value={product} tone="fg" mono />
        <Stat
          label="pnl @ cursor"
          value={formatCurrency(pnl)}
          tone={pnl > 0 ? "buy" : pnl < 0 ? "sell" : "muted"}
          mono
        />
        {delta !== null && (
          <Stat
            label="Δ to final"
            value={`${delta >= 0 ? "+" : ""}${formatCurrency(delta)}`}
            tone={delta > 0 ? "buy" : delta < 0 ? "sell" : "muted"}
            mono
          />
        )}
        <Stat
          label="position"
          value={formatInt(position)}
          tone={position > 0 ? "buy" : position < 0 ? "sell" : "muted"}
          mono
        />
        <Stat
          label="open orders · mid"
          value={`${openOrders} · ${mid ?? "—"}`}
          tone="fg"
          mono
        />
      </div>
    </Card>
  );
});

function Stat({
  label,
  value,
  tone,
  mono,
}: {
  label: string;
  value: string;
  tone: "buy" | "sell" | "fg" | "muted";
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-fg">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-sm",
          mono && "font-mono tabular-nums",
          tone === "buy" && "text-buy",
          tone === "sell" && "text-sell",
          tone === "muted" && "text-muted-fg",
          tone === "fg" && "text-fg"
        )}
      >
        {value}
      </div>
    </div>
  );
}
