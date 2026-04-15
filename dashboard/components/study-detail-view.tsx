"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { ReplayErrorBoundary } from "@/components/replay/replay-error-boundary";
import { StudyParallelCoords } from "@/components/study-parallel-coords";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Study, StudyTrialSummary } from "@/lib/types";
import { formatInt, formatTimestamp } from "@/lib/utils";

interface Props {
  initial: Study;
  initialTrials: StudyTrialSummary[];
}

const POLL_MS = 2000;

export function StudyDetailView({ initial, initialTrials }: Props) {
  const router = useRouter();
  const [study, setStudy] = useState<Study>(initial);
  const [trials, setTrials] = useState<StudyTrialSummary[]>(initialTrials);
  const [error, setError] = useState<string | null>(null);
  const [cancelStatus, setCancelStatus] = useState<
    "idle" | "confirming" | "submitting" | "error"
  >("idle");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function onDelete() {
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/studies/${encodeURIComponent(study._id)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      router.push("/studies");
    } catch (err) {
      setDeleteError((err as Error).message);
      setDeleteLoading(false);
    }
  }

  const isTerminal =
    study.status === "succeeded" ||
    study.status === "failed" ||
    study.status === "cancelled";

  async function onCancelClick() {
    if (cancelStatus === "confirming") {
      setCancelStatus("submitting");
      try {
        const res = await fetch(
          `/api/studies/${encodeURIComponent(study._id)}/cancel`,
          { method: "POST" }
        );
        if (!res.ok) throw new Error(`cancel failed: ${res.status}`);
        const doc = (await res.json()) as Study;
        setStudy(doc);
        setCancelStatus("idle");
      } catch {
        setCancelStatus("error");
      }
      return;
    }
    setCancelStatus("confirming");
  }

  useEffect(() => {
    if (isTerminal) return;
    let cancelled = false;

    async function poll() {
      try {
        const [studyRes, trialsRes] = await Promise.all([
          fetch(`/api/studies/${encodeURIComponent(study._id)}`),
          fetch(`/api/studies/${encodeURIComponent(study._id)}/trials`),
        ]);
        if (!studyRes.ok) throw new Error(`poll study failed: ${studyRes.status}`);
        if (!trialsRes.ok) throw new Error(`poll trials failed: ${trialsRes.status}`);
        const doc = (await studyRes.json()) as Study;
        const ts = (await trialsRes.json()) as StudyTrialSummary[];
        if (!cancelled) {
          setStudy(doc);
          setTrials(ts);
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    }

    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [isTerminal, study._id]);

  const sortedTrials = useMemo(() => {
    if (!isTerminal) {
      return [...trials].sort((a, b) => a.trial_number - b.trial_number);
    }
    const mul = study.direction === "maximize" ? -1 : 1;
    return [...trials].sort((a, b) => {
      const av = a.value ?? 0;
      const bv = b.value ?? 0;
      return mul * (av - bv);
    });
  }, [trials, isTerminal, study.direction]);

  const paramNames = useMemo(() => Object.keys(study.space), [study.space]);

  return (
    <div className="space-y-6">
      <Link
        href="/studies"
        className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
      >
        ← back to studies
      </Link>

      <PageHeader
        eyebrow={`study · ${study._id}`}
        title={study.strategy_filename}
        description={`r${study.round} / d${study.day} · ${study.matcher} · ${study.objective} (${study.direction})`}
        actions={
          <>
            {!isTerminal && (
              <Button
                variant={cancelStatus === "confirming" ? "danger" : "secondary"}
                onClick={onCancelClick}
                disabled={cancelStatus === "submitting"}
                loading={cancelStatus === "submitting"}
              >
                {cancelStatus === "confirming"
                  ? "really cancel?"
                  : cancelStatus === "submitting"
                    ? "cancelling…"
                    : "cancel study"}
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => setDeleteOpen(true)}
              disabled={!isTerminal}
              title={
                isTerminal
                  ? "delete this study"
                  : "cancel the study before deleting"
              }
            >
              delete
            </Button>
          </>
        }
      />

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => {
          if (!deleteLoading) {
            setDeleteOpen(false);
            setDeleteError(null);
          }
        }}
        onConfirm={onDelete}
        title="delete study"
        description={
          <>
            <code className="font-mono text-fg">{study._id}</code>
          </>
        }
        loading={deleteLoading}
        error={deleteError}
      >
        <div className="text-xs text-muted-fg">
          this removes the study doc and its optuna SQLite storage. the
          child trial runs stay where they are.
        </div>
      </ConfirmDialog>

      {cancelStatus === "error" && (
        <ErrorCard title="cancel failed">try again.</ErrorCard>
      )}

      <div className="grid gap-4 md:grid-cols-4">
        <Card tone="subtle">
          <CardHeader>created</CardHeader>
          <div className="font-mono text-sm text-fg">{formatTimestamp(study.created_at)}</div>
          {study.finished_at && (
            <div className="mt-1 text-xs text-muted-fg">
              finished {formatTimestamp(study.finished_at)}
            </div>
          )}
        </Card>
        <Card tone="subtle">
          <CardHeader>objective</CardHeader>
          <div className="font-mono text-sm text-fg">{study.objective}</div>
          <div className="mt-1 text-xs text-muted-fg">{study.direction}</div>
        </Card>
        <Card tone="subtle">
          <CardHeader>status</CardHeader>
          <StatusBadge status={study.status} />
        </Card>
        <Card tone="subtle">
          <CardHeader>progress</CardHeader>
          <ProgressBar
            total={study.progress.total}
            completed={study.progress.completed}
            failed={study.progress.failed}
            running={study.progress.running}
          />
        </Card>
      </div>

      {error && (
        <div className="rounded-card border border-warn/60 bg-warn/10 px-3 py-2 text-xs text-warn">
          polling error: {error} — will retry
        </div>
      )}

      <BestTrialCard study={study} />

      <Card>
        <CardHeader>parallel coordinates</CardHeader>
        <ReplayErrorBoundary>
          <StudyParallelCoords
            space={study.space}
            trials={trials}
            objective={study.objective}
            direction={study.direction}
            bestTrialNumber={study.best_trial?.number ?? null}
          />
        </ReplayErrorBoundary>
      </Card>

      <Card padded={false}>
        <div className="flex items-baseline justify-between px-5 py-4">
          <div className="text-sm font-medium text-fg">trials</div>
          <div className="text-[10px] uppercase tracking-[0.08em] text-muted-fg">
            {isTerminal
              ? `sorted by ${study.objective} (${study.direction})`
              : "sorted by trial number"}
          </div>
        </div>
        {sortedTrials.length === 0 ? (
          <div className="px-5 pb-5 text-sm text-muted-fg">
            {study.status === "queued" ? "queued — waiting for first trial" : "no trials yet"}
          </div>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>#</Th>
                <Th className="text-right">value</Th>
                {paramNames.map((name) => (
                  <Th key={name} className="text-right">
                    {name}
                  </Th>
                ))}
                <Th className="text-right">duration</Th>
                <Th>run</Th>
              </Tr>
            </Thead>
            <Tbody>
              {sortedTrials.map((trial) => (
                <TrialRow
                  key={trial.trial_number}
                  trial={trial}
                  paramNames={paramNames}
                />
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function ProgressBar({
  total,
  completed,
  failed,
  running,
}: {
  total: number;
  completed: number;
  failed: number;
  running: number;
}) {
  const pct = total === 0 ? 0 : ((completed + failed) / total) * 100;
  const failedPct = total === 0 ? 0 : (failed / total) * 100;
  const okPct = pct - failedPct;
  return (
    <div>
      <div className="font-mono text-xs tabular-nums text-muted-fg">
        <span className="text-fg">{completed + failed}</span> / {total}
        {running > 0 && <span className="ml-1">· {running} running</span>}
        {failed > 0 && <span className="ml-1 text-sell">· {failed} failed</span>}
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="flex h-full">
          <div className="h-full bg-buy/80 transition-all duration-fast" style={{ width: `${okPct}%` }} />
          <div className="h-full bg-sell/80 transition-all duration-fast" style={{ width: `${failedPct}%` }} />
        </div>
      </div>
    </div>
  );
}

function BestTrialCard({ study }: { study: Study }) {
  if (!study.best_trial) {
    return (
      <Card>
        <CardHeader>best trial</CardHeader>
        <div className="text-sm text-muted-fg">no completed trials yet</div>
      </Card>
    );
  }
  const best = study.best_trial;
  const paramNames = Object.keys(best.params);
  return (
    <Card>
      <CardHeader>best trial</CardHeader>
      <div className="flex flex-wrap items-baseline gap-6">
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">trial</div>
          <div className="font-mono text-xl text-fg">#{best.number}</div>
        </div>
        <div>
          <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
            {study.objective}
          </div>
          <div className="font-mono text-xl font-semibold text-buy">{best.value.toFixed(2)}</div>
        </div>
        <div className="flex-1">
          <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">params</div>
          <div className="font-mono text-sm text-fg">
            {paramNames.map((name, i) => (
              <span key={name}>
                {i > 0 && <span className="text-muted-fg"> · </span>}
                <span className="text-muted-fg">{name}=</span>
                {String(best.params[name])}
              </span>
            ))}
          </div>
        </div>
        {best.run_id && (
          <Link
            href={`/runs/${encodeURIComponent(best.run_id)}`}
            className={buttonClasses({ variant: "secondary" })}
          >
            open run →
          </Link>
        )}
      </div>
    </Card>
  );
}

function TrialRow({
  trial,
  paramNames,
}: {
  trial: StudyTrialSummary;
  paramNames: string[];
}) {
  return (
    <Tr>
      <Td className="text-muted-fg">#{trial.trial_number}</Td>
      <Td className="text-right font-semibold text-fg">
        {trial.value !== null ? trial.value.toFixed(2) : "—"}
      </Td>
      {paramNames.map((name) => {
        const val = trial.params[name];
        return (
          <Td key={name} className="text-right text-xs text-muted-fg">
            {val === undefined ? "—" : String(val)}
          </Td>
        );
      })}
      <Td className="text-right text-muted-fg">
        {trial.duration_ms !== null ? `${formatInt(trial.duration_ms)} ms` : "—"}
      </Td>
      <Td>
        {trial.run_id ? (
          <Link
            href={`/runs/${encodeURIComponent(trial.run_id)}`}
            className="text-xs text-accent transition-colors duration-fast hover:underline"
          >
            open →
          </Link>
        ) : (
          <span className="text-xs text-muted-fg">—</span>
        )}
      </Td>
    </Tr>
  );
}
