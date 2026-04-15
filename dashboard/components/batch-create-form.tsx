"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Batch, Dataset, Strategy } from "@/lib/types";
import { cn, formatInt } from "@/lib/utils";

interface Props {
  strategies: Strategy[];
  datasets: Dataset[];
}

type Status = "idle" | "submitting" | "ok" | "error";

export function BatchCreateForm({ strategies, datasets }: Props) {
  const router = useRouter();

  const sortedStrategies = useMemo(
    () =>
      [...strategies].sort((a, b) =>
        a.uploaded_at < b.uploaded_at ? 1 : a.uploaded_at > b.uploaded_at ? -1 : 0
      ),
    [strategies]
  );
  const sortedDatasets = useMemo(
    () =>
      [...datasets].sort((a, b) =>
        a.round === b.round ? a.day - b.day : a.round - b.round
      ),
    [datasets]
  );

  const [strategyId, setStrategyId] = useState<string>(sortedStrategies[0]?._id ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [positionLimit, setPositionLimit] = useState<string>("50");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(sortedDatasets.map((d) => d._id)));
  }

  function clearAll() {
    setSelected(new Set());
  }

  const canSubmit =
    strategyId !== "" &&
    selected.size > 0 &&
    positionLimit !== "" &&
    status !== "submitting";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const chosen = sortedDatasets.filter((d) => selected.has(d._id));
    if (chosen.length === 0) return;

    setStatus("submitting");
    setMessage(null);

    try {
      const res = await fetch("/api/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          datasets: chosen.map((d) => ({ round: d.round, day: d.day })),
          matcher: "depth_only",
          position_limit: Number(positionLimit),
          params: {},
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`batch submit failed (${res.status}): ${detail}`);
      }
      const doc = (await res.json()) as Batch;
      setStatus("ok");
      setMessage(`created ${doc._id} — ${doc.tasks.length} tasks queued`);
      router.push(`/batches/${encodeURIComponent(doc._id)}`);
    } catch (err) {
      setStatus("error");
      setMessage((err as Error).message);
    }
  }

  const missingInputs = sortedStrategies.length === 0 || sortedDatasets.length === 0;

  return (
    <Card>
      <CardHeader>new batch</CardHeader>
      {missingInputs ? (
        <div className="text-sm text-muted-fg">
          {sortedStrategies.length === 0 && (
            <div>upload a strategy on the strategies page first</div>
          )}
          {sortedDatasets.length === 0 && (
            <div>upload a dataset on the datasets page first</div>
          )}
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5">
          <Field label="strategy">
            <Select
              mono
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
            >
              {sortedStrategies.map((s) => (
                <option key={s._id} value={s._id}>
                  {s.filename} · {s._id}
                </option>
              ))}
            </Select>
          </Field>

          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
                datasets ({selected.size} selected)
              </div>
              <div className="flex gap-3 text-xs">
                <button
                  type="button"
                  onClick={selectAll}
                  className="text-muted-fg transition-colors duration-fast hover:text-accent"
                >
                  select all
                </button>
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-muted-fg transition-colors duration-fast hover:text-accent"
                >
                  clear
                </button>
              </div>
            </div>
            <div className="max-h-72 overflow-y-auto rounded-card border border-border">
              <table className="w-full font-mono text-xs">
                <thead className="bg-surface-2/60 text-[10px] uppercase tracking-[0.08em] text-muted-fg">
                  <tr>
                    <th className="w-10 px-3 py-2" />
                    <th className="px-3 py-2 text-left font-medium">round / day</th>
                    <th className="px-3 py-2 text-left font-medium">products</th>
                    <th className="px-3 py-2 text-right font-medium">timestamps</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {sortedDatasets.map((d) => {
                    const isSelected = selected.has(d._id);
                    return (
                      <tr
                        key={d._id}
                        onClick={() => toggle(d._id)}
                        className={cn(
                          "cursor-pointer transition-colors duration-fast hover:bg-surface-1/80",
                          isSelected && "bg-accent/5"
                        )}
                      >
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggle(d._id)}
                            onClick={(e) => e.stopPropagation()}
                            className="accent-accent"
                          />
                        </td>
                        <td className="px-3 py-2 tabular-nums text-fg">
                          r{d.round} / d{d.day}
                        </td>
                        <td className="px-3 py-2 text-muted-fg">
                          {d.products.join(", ")}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted-fg">
                          {formatInt(d.num_timestamps)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="matcher">
              <div className="flex h-8 items-center rounded-control border border-border bg-surface-2 px-2.5 font-mono text-sm text-muted-fg">
                depth_only
              </div>
            </Field>
            <Field label="position limit">
              <Input
                mono
                type="number"
                min="1"
                value={positionLimit}
                onChange={(e) => setPositionLimit(e.target.value)}
                required
              />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              type="submit"
              variant="primary"
              disabled={!canSubmit}
              loading={status === "submitting"}
            >
              {status === "submitting"
                ? "submitting…"
                : `run batch (${selected.size} tasks)`}
            </Button>
            {message && (
              <span
                className={cn(
                  "text-xs",
                  status === "ok" && "text-buy",
                  status === "error" && "text-sell",
                  status === "submitting" && "text-muted-fg"
                )}
              >
                {message}
              </span>
            )}
          </div>

          <p className="text-xs leading-relaxed text-muted-fg">
            tasks execute on the api with up to 2 workers in parallel. follow progress
            on the batch detail page after submit.
          </p>
        </form>
      )}
    </Card>
  );
}
