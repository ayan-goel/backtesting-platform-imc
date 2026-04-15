"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Dataset, Strategy } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  strategies: Strategy[];
  datasets: Dataset[];
}

type Status = "idle" | "running" | "ok" | "error";

export function RunCreateForm({ strategies, datasets }: Props) {
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
  const [datasetId, setDatasetId] = useState<string>(sortedDatasets[0]?._id ?? "");
  const [matcher, setMatcher] = useState<string>("imc");
  const [positionLimit, setPositionLimit] = useState<string>("80");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const canSubmit =
    strategyId !== "" && datasetId !== "" && positionLimit !== "" && status !== "running";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const dataset = sortedDatasets.find((d) => d._id === datasetId);
    if (!dataset) {
      setStatus("error");
      setMessage("pick a dataset");
      return;
    }

    setStatus("running");
    setMessage(null);

    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          round: dataset.round,
          day: dataset.day,
          matcher,
          position_limit: Number(positionLimit),
          params: {},
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`run failed (${res.status}): ${detail}`);
      }
      const doc = (await res.json()) as { _id: string; pnl_total: number };
      setStatus("ok");
      setMessage(`created ${doc._id} — pnl ${doc.pnl_total.toFixed(2)}`);
      router.refresh();
    } catch (err) {
      setStatus("error");
      setMessage((err as Error).message);
    }
  }

  const missingInputs = sortedStrategies.length === 0 || sortedDatasets.length === 0;

  return (
    <Card>
      <CardHeader>new run</CardHeader>
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
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
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
            <Field label="dataset">
              <Select
                mono
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
              >
                {sortedDatasets.map((d) => (
                  <option key={d._id} value={d._id}>
                    r{d.round} / d{d.day} · {d.products.join(", ")}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="matcher">
              <Select
                mono
                value={matcher}
                onChange={(e) => setMatcher(e.target.value)}
              >
                <option value="imc">imc (parity w/ prosperity4btx)</option>
                <option value="depth_and_trades">depth_and_trades</option>
                <option value="depth_only">depth_only</option>
              </Select>
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
              loading={status === "running"}
            >
              {status === "running" ? "running…" : "run backtest"}
            </Button>
            {message && (
              <span
                className={cn(
                  "text-xs",
                  status === "ok" && "text-buy",
                  status === "error" && "text-sell",
                  status === "running" && "text-muted-fg"
                )}
              >
                {message}
              </span>
            )}
          </div>

          <p className="text-xs leading-relaxed text-muted-fg">
            runs execute synchronously on the api — expect a few seconds of latency on
            a tutorial day. the row shows up in the table above when it finishes.
          </p>
        </form>
      )}
    </Card>
  );
}
