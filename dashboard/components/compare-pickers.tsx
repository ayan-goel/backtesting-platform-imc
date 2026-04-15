"use client";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { RunSummary } from "@/lib/types";
import { cn, formatCurrency, formatTimestamp } from "@/lib/utils";

interface Props {
  runs: RunSummary[];
  a: string;
  b: string;
  onChangeA: (id: string) => void;
  onChangeB: (id: string) => void;
  onSwap: () => void;
}

export function ComparePickers({ runs, a, b, onChangeA, onChangeB, onSwap }: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-end">
      <Picker label="run A" value={a} runs={runs} onChange={onChangeA} tone="buy" />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onSwap}
        aria-label="swap runs"
        className="mb-0.5 self-end"
      >
        ⇄ swap
      </Button>
      <Picker label="run B" value={b} runs={runs} onChange={onChangeB} tone="accent" />
    </div>
  );
}

function Picker({
  label,
  value,
  runs,
  onChange,
  tone,
}: {
  label: string;
  value: string;
  runs: RunSummary[];
  onChange: (id: string) => void;
  tone: "buy" | "accent";
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span
        className={cn(
          "flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.08em]",
          tone === "buy" ? "text-buy" : "text-accent"
        )}
      >
        <span
          className={cn(
            "inline-block h-2 w-2 rounded-full",
            tone === "buy" ? "bg-buy" : "bg-accent"
          )}
        />
        {label}
      </span>
      <Select
        mono
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 text-xs"
      >
        <option value="">—</option>
        {runs.map((r) => (
          <option key={r._id} value={r._id}>
            {formatTimestamp(r.created_at)} · {r.strategy_path} · r{r.round}d{r.day}
            {" · "}
            {formatCurrency(r.pnl_total)}
          </option>
        ))}
      </Select>
    </label>
  );
}
