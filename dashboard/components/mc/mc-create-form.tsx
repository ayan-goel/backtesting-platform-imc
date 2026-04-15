"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  Dataset,
  McGeneratorSpec,
  McSimulation,
  Strategy,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  strategies: Strategy[];
  datasets: Dataset[];
}

type GeneratorType = McGeneratorSpec["type"];
type Status = "idle" | "submitting" | "ok" | "error";

export function McCreateForm({ strategies, datasets }: Props) {
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

  const [strategyId, setStrategyId] = useState(sortedStrategies[0]?._id ?? "");
  const [datasetKey, setDatasetKey] = useState(sortedDatasets[0]?._id ?? "");
  const [matcher, setMatcher] = useState("imc");
  const [positionLimit, setPositionLimit] = useState("50");
  const [nPaths, setNPaths] = useState("100");
  const [seed, setSeed] = useState("42");
  const [numWorkers, setNumWorkers] = useState("2");

  const [generatorType, setGeneratorType] = useState<GeneratorType>("block_bootstrap");
  const [blockSize, setBlockSize] = useState("50");
  const [gbmMuScale, setGbmMuScale] = useState("1.0");
  const [gbmSigmaScale, setGbmSigmaScale] = useState("1.0");
  const [gbmStart, setGbmStart] = useState<"historical_first" | "historical_last">(
    "historical_first"
  );
  const [ouPhiScale, setOuPhiScale] = useState("1.0");
  const [ouSigmaScale, setOuSigmaScale] = useState("1.0");

  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const selectedDataset = useMemo(
    () => sortedDatasets.find((d) => d._id === datasetKey) ?? null,
    [datasetKey, sortedDatasets]
  );

  const canSubmit =
    strategyId !== "" &&
    datasetKey !== "" &&
    positionLimit !== "" &&
    nPaths !== "" &&
    status !== "submitting";

  function buildGenerator(): McGeneratorSpec {
    switch (generatorType) {
      case "identity":
        return { type: "identity" };
      case "block_bootstrap":
        return { type: "block_bootstrap", block_size: Number(blockSize) };
      case "gbm":
        return {
          type: "gbm",
          mu_scale: Number(gbmMuScale),
          sigma_scale: Number(gbmSigmaScale),
          starting_price_from: gbmStart,
        };
      case "ou":
        return {
          type: "ou",
          phi_scale: Number(ouPhiScale),
          sigma_scale: Number(ouSigmaScale),
        };
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDataset) return;
    setStatus("submitting");
    setMessage(null);
    try {
      const res = await fetch("/api/mc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: strategyId,
          round: selectedDataset.round,
          day: selectedDataset.day,
          matcher,
          position_limit: Number(positionLimit),
          n_paths: Number(nPaths),
          seed: Number(seed),
          num_workers: Number(numWorkers),
          generator: buildGenerator(),
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`mc submit failed (${res.status}): ${detail}`);
      }
      const doc = (await res.json()) as McSimulation;
      setStatus("ok");
      setMessage(`created ${doc._id}`);
      router.push(`/mc/${encodeURIComponent(doc._id)}`);
    } catch (err) {
      setStatus("error");
      setMessage((err as Error).message);
    }
  }

  const missingInputs =
    sortedStrategies.length === 0 || sortedDatasets.length === 0;

  return (
    <Card>
      <CardHeader>new simulation</CardHeader>
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

          <div className="grid gap-3 md:grid-cols-4">
            <Field label="matcher">
              <Select mono value={matcher} onChange={(e) => setMatcher(e.target.value)}>
                <option value="imc">imc</option>
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
            <Field label="n paths">
              <Input
                mono
                type="number"
                min="1"
                max="1000"
                value={nPaths}
                onChange={(e) => setNPaths(e.target.value)}
                required
              />
            </Field>
            <Field label="seed">
              <Input
                mono
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                required
              />
            </Field>
          </div>

          <Field label="generator">
            <Select
              mono
              value={generatorType}
              onChange={(e) => setGeneratorType(e.target.value as GeneratorType)}
            >
              <option value="identity">identity (regression anchor)</option>
              <option value="block_bootstrap">block bootstrap</option>
              <option value="gbm">geometric brownian motion</option>
              <option value="ou">ornstein-uhlenbeck (mean-reverting)</option>
            </Select>
          </Field>

          {generatorType === "block_bootstrap" && (
            <Field label="block size">
              <Input
                mono
                type="number"
                min="1"
                value={blockSize}
                onChange={(e) => setBlockSize(e.target.value)}
              />
            </Field>
          )}

          {generatorType === "gbm" && (
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="mu scale">
                <Input
                  mono
                  type="number"
                  step="0.01"
                  value={gbmMuScale}
                  onChange={(e) => setGbmMuScale(e.target.value)}
                />
              </Field>
              <Field label="sigma scale">
                <Input
                  mono
                  type="number"
                  step="0.01"
                  value={gbmSigmaScale}
                  onChange={(e) => setGbmSigmaScale(e.target.value)}
                />
              </Field>
              <Field label="start from">
                <Select
                  mono
                  value={gbmStart}
                  onChange={(e) =>
                    setGbmStart(e.target.value as "historical_first" | "historical_last")
                  }
                >
                  <option value="historical_first">historical_first</option>
                  <option value="historical_last">historical_last</option>
                </Select>
              </Field>
            </div>
          )}

          {generatorType === "ou" && (
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="phi scale">
                <Input
                  mono
                  type="number"
                  step="0.01"
                  value={ouPhiScale}
                  onChange={(e) => setOuPhiScale(e.target.value)}
                />
              </Field>
              <Field label="sigma scale">
                <Input
                  mono
                  type="number"
                  step="0.01"
                  value={ouSigmaScale}
                  onChange={(e) => setOuSigmaScale(e.target.value)}
                />
              </Field>
            </div>
          )}

          <Field label="workers (advanced)">
            <Input
              mono
              type="number"
              min="1"
              max="16"
              value={numWorkers}
              onChange={(e) => setNumWorkers(e.target.value)}
            />
          </Field>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button
              type="submit"
              variant="primary"
              disabled={!canSubmit}
              loading={status === "submitting"}
            >
              {status === "submitting" ? "submitting…" : `run mc (${nPaths} paths)`}
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
            each path runs the same strategy against a synthetic day. the identity
            generator returns the historical day unchanged — any run with it should
            produce one path whose pnl equals the deterministic backtest.
          </p>
        </form>
      )}
    </Card>
  );
}
