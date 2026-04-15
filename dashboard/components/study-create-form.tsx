"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  buildSearchSpace,
  SearchSpaceBuilder,
  type SpaceRow,
} from "@/components/search-space-builder";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Dataset, ParamSpec, Strategy, Study } from "@/lib/types";
import { validateSpace } from "@/lib/study-space";
import { cn } from "@/lib/utils";

interface DetectedParam {
  name: string;
  class_name: string;
  default: number;
  type: "int" | "float";
  suggested_low: number;
  suggested_high: number;
}

function detectedToRow(p: DetectedParam): SpaceRow {
  const spec: ParamSpec =
    p.type === "int"
      ? { type: "int", low: Math.floor(p.suggested_low), high: Math.ceil(p.suggested_high) }
      : { type: "float", low: p.suggested_low, high: p.suggested_high };
  return { name: p.name, spec };
}

interface Props {
  strategies: Strategy[];
  datasets: Dataset[];
}

type Status = "idle" | "submitting" | "ok" | "error";

export function StudyCreateForm({ strategies, datasets }: Props) {
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

  const [strategyId, setStrategyId] = useState<string>(
    sortedStrategies[0]?._id ?? ""
  );
  const [datasetKey, setDatasetKey] = useState<string>(
    sortedDatasets[0]?._id ?? ""
  );
  const [positionLimit, setPositionLimit] = useState<string>("50");
  const [nTrials, setNTrials] = useState<string>("30");
  const [direction, setDirection] = useState<"maximize" | "minimize">("maximize");
  const [objective, setObjective] = useState<string>("pnl_total");
  const [rows, setRows] = useState<SpaceRow[]>([
    { name: "edge", spec: { type: "int", low: 0, high: 5 } },
  ]);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [detectStatus, setDetectStatus] = useState<
    "idle" | "loading" | "ok" | "empty" | "error"
  >("idle");
  const [detectMessage, setDetectMessage] = useState<string | null>(null);
  // Track the last strategy we autopopulated for so we don't clobber the user's edits
  // every render.
  const lastDetectedFor = useRef<string | null>(null);

  const selectedDataset = useMemo(
    () => sortedDatasets.find((d) => d._id === datasetKey) ?? null,
    [datasetKey, sortedDatasets]
  );

  const objectiveOptions = useMemo(() => {
    const opts = ["pnl_total"];
    if (selectedDataset) {
      for (const p of selectedDataset.products) {
        opts.push(`pnl_by_product.${p}`);
      }
    }
    return opts;
  }, [selectedDataset]);

  const detectParams = useCallback(
    async (id: string, signal?: AbortSignal) => {
      if (!id) return;
      setDetectStatus("loading");
      setDetectMessage(null);
      try {
        const res = await fetch(
          `/api/strategies/${encodeURIComponent(id)}/params`,
          { signal, cache: "no-store" }
        );
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`detect failed (${res.status}): ${detail}`);
        }
        const data = (await res.json()) as DetectedParam[];
        if (signal?.aborted) return;
        if (data.length === 0) {
          setDetectStatus("empty");
          setDetectMessage("no tunable constants detected");
          return;
        }
        setRows(data.map(detectedToRow));
        setDetectStatus("ok");
        setDetectMessage(`detected ${data.length} param${data.length === 1 ? "" : "s"}`);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setDetectStatus("error");
        setDetectMessage((err as Error).message);
      }
    },
    []
  );

  // Auto-detect whenever the selected strategy changes. Each strategy is only
  // auto-populated once per mount so the user's manual edits survive re-renders.
  useEffect(() => {
    if (!strategyId) return;
    if (lastDetectedFor.current === strategyId) return;
    lastDetectedFor.current = strategyId;
    const ac = new AbortController();
    void detectParams(strategyId, ac.signal);
    return () => ac.abort();
  }, [strategyId, detectParams]);

  const space = useMemo(() => buildSearchSpace(rows), [rows]);
  const spaceErrors = useMemo(() => validateSpace(space), [space]);
  const errorsByName = useMemo(() => {
    const map: Record<string, string> = {};
    for (const err of spaceErrors) map[err.name] = err.message;
    return map;
  }, [spaceErrors]);

  const canSubmit =
    strategyId !== "" &&
    datasetKey !== "" &&
    positionLimit !== "" &&
    nTrials !== "" &&
    rows.length > 0 &&
    spaceErrors.length === 0 &&
    status !== "submitting";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDataset) return;
    setStatus("submitting");
    setMessage(null);

    try {
      const res = await fetch("/api/studies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          round: selectedDataset.round,
          day: selectedDataset.day,
          matcher: "depth_only",
          position_limit: Number(positionLimit),
          space,
          objective,
          direction,
          n_trials: Number(nTrials),
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`study submit failed (${res.status}): ${detail}`);
      }
      const doc = (await res.json()) as Study;
      setStatus("ok");
      setMessage(`created ${doc._id}`);
      router.push(`/studies/${encodeURIComponent(doc._id)}`);
    } catch (err) {
      setStatus("error");
      setMessage((err as Error).message);
    }
  }

  const missingInputs = sortedStrategies.length === 0 || sortedDatasets.length === 0;

  return (
    <Card>
      <CardHeader>new study</CardHeader>
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
                value={datasetKey}
                onChange={(e) => setDatasetKey(e.target.value)}
              >
                {sortedDatasets.map((d) => (
                  <option key={d._id} value={d._id}>
                    r{d.round} / d{d.day} — {d.products.join(", ")}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
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
            <Field label="n trials">
              <Input
                mono
                type="number"
                min="1"
                max="500"
                value={nTrials}
                onChange={(e) => setNTrials(e.target.value)}
                required
              />
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="objective">
              <Select
                mono
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
              >
                {objectiveOptions.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="direction">
              <Select
                value={direction}
                onChange={(e) =>
                  setDirection(e.target.value as "maximize" | "minimize")
                }
              >
                <option value="maximize">maximize</option>
                <option value="minimize">minimize</option>
              </Select>
            </Field>
          </div>

          <div className="flex items-center justify-between gap-3">
            <span
              className={cn(
                "text-[11px]",
                detectStatus === "loading" && "text-muted-fg",
                detectStatus === "ok" && "text-buy",
                detectStatus === "empty" && "text-muted-fg",
                detectStatus === "error" && "text-sell",
                detectStatus === "idle" && "text-muted-fg"
              )}
            >
              {detectStatus === "loading" && "detecting params…"}
              {detectStatus !== "loading" && detectMessage}
            </span>
            <button
              type="button"
              onClick={() => {
                if (strategyId) void detectParams(strategyId);
              }}
              disabled={!strategyId || detectStatus === "loading"}
              className="text-xs text-muted-fg transition-colors duration-fast hover:text-accent disabled:opacity-50"
            >
              re-detect
            </button>
          </div>

          <SearchSpaceBuilder
            rows={rows}
            onChange={setRows}
            errorsByName={errorsByName}
          />

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              type="submit"
              variant="primary"
              disabled={!canSubmit}
              loading={status === "submitting"}
            >
              {status === "submitting" ? "submitting…" : `run study (${nTrials} trials)`}
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
            trials run sequentially with optuna&apos;s TPE sampler. progress shows on
            the detail page after submit.
          </p>
        </form>
      )}
    </Card>
  );
}
