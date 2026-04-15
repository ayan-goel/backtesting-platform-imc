"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Batch, BatchTask } from "@/lib/types";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

interface Props {
  initial: Batch;
}

const POLL_MS = 2000;

export function BatchDetailView({ initial }: Props) {
  const router = useRouter();
  const [batch, setBatch] = useState<Batch>(initial);
  const [error, setError] = useState<string | null>(null);
  const [rerunStatus, setRerunStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function onDelete() {
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/batches/${encodeURIComponent(batch._id)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      router.push("/batches");
    } catch (err) {
      setDeleteError((err as Error).message);
      setDeleteLoading(false);
    }
  }

  const isTerminal = batch.status === "succeeded" || batch.status === "failed";

  async function onRerun() {
    setRerunStatus("submitting");
    try {
      const res = await fetch("/api/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_id: batch.strategy_id,
          datasets: batch.tasks.map((t) => ({ round: t.round, day: t.day })),
          matcher: batch.matcher,
          position_limit: batch.position_limit,
          params: batch.params,
        }),
      });
      if (!res.ok) throw new Error(`rerun failed: ${res.status}`);
      const doc = (await res.json()) as Batch;
      router.push(`/batches/${encodeURIComponent(doc._id)}`);
    } catch {
      setRerunStatus("error");
    }
  }

  useEffect(() => {
    if (isTerminal) return;
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(`/api/batches/${encodeURIComponent(batch._id)}`);
        if (!res.ok) throw new Error(`poll failed: ${res.status}`);
        const doc = (await res.json()) as Batch;
        if (!cancelled) setBatch(doc);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    }

    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [isTerminal, batch._id]);

  const sortedTasks = useMemo(() => {
    if (isTerminal) {
      return [...batch.tasks].sort((a, b) => {
        const av = a.pnl_total ?? -Infinity;
        const bv = b.pnl_total ?? -Infinity;
        return bv - av;
      });
    }
    return [...batch.tasks].sort((a, b) =>
      a.round === b.round ? a.day - b.day : a.round - b.round
    );
  }, [batch.tasks, isTerminal]);

  return (
    <div className="space-y-6">
      <Link
        href="/batches"
        className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
      >
        ← back to batches
      </Link>

      <PageHeader
        eyebrow={`batch · ${batch._id}`}
        title={batch.strategy_filename}
        description={`${batch.matcher} · position limit ${batch.position_limit}`}
        actions={
          <>
            {isTerminal && (
              <Button
                variant="secondary"
                onClick={onRerun}
                disabled={rerunStatus === "submitting"}
                loading={rerunStatus === "submitting"}
              >
                rerun batch
              </Button>
            )}
            <Button
              variant="danger"
              onClick={() => setDeleteOpen(true)}
              disabled={!isTerminal}
              title={
                isTerminal
                  ? "delete this batch"
                  : "cancel the batch before deleting"
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
        title="delete batch"
        description={
          <>
            <code className="font-mono text-fg">{batch._id}</code>
          </>
        }
        loading={deleteLoading}
        error={deleteError}
      >
        <div className="text-xs text-muted-fg">
          this removes the batch doc only. the child runs stay where they are.
        </div>
      </ConfirmDialog>

      {rerunStatus === "error" && (
        <ErrorCard title="rerun failed">try again from /batches/new.</ErrorCard>
      )}

      <div className="grid gap-4 md:grid-cols-4">
        <Card tone="subtle">
          <CardHeader>created</CardHeader>
          <div className="font-mono text-sm text-fg">{formatTimestamp(batch.created_at)}</div>
          {batch.finished_at && (
            <div className="mt-1 text-xs text-muted-fg">
              finished {formatTimestamp(batch.finished_at)}
            </div>
          )}
        </Card>
        <Card tone="subtle">
          <CardHeader>status</CardHeader>
          <StatusBadge status={batch.status} />
        </Card>
        <Card tone="subtle" className="md:col-span-2">
          <CardHeader>progress</CardHeader>
          <ProgressBar
            total={batch.progress.total}
            completed={batch.progress.completed}
            failed={batch.progress.failed}
          />
        </Card>
      </div>

      {error && (
        <div className="rounded-card border border-warn/60 bg-warn/10 px-3 py-2 text-xs text-warn">
          polling error: {error} — will retry
        </div>
      )}

      <Card padded={false}>
        <div className="flex items-baseline justify-between px-5 py-4">
          <div className="text-sm font-medium text-fg">results</div>
          <div className="text-[10px] uppercase tracking-[0.08em] text-muted-fg">
            {isTerminal ? "sorted by pnl" : "sorted by round / day"}
          </div>
        </div>
        {sortedTasks.length === 0 ? (
          <div className="px-5 pb-5 text-sm text-muted-fg">no tasks</div>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>round / day</Th>
                <Th>status</Th>
                <Th className="text-right">pnl</Th>
                <Th className="text-right">duration</Th>
                <Th>run</Th>
              </Tr>
            </Thead>
            <Tbody>
              {sortedTasks.map((task) => (
                <TaskRow key={`${task.round}-${task.day}`} task={task} />
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
}: {
  total: number;
  completed: number;
  failed: number;
}) {
  const pct = total === 0 ? 0 : ((completed + failed) / total) * 100;
  const failedPct = total === 0 ? 0 : (failed / total) * 100;
  const okPct = pct - failedPct;
  return (
    <div>
      <div className="font-mono text-sm tabular-nums">
        <span className="text-fg">{completed + failed}</span>
        <span className="text-muted-fg"> / {total}</span>
        {failed > 0 && <span className="ml-2 text-sell">· {failed} failed</span>}
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="flex h-full">
          <div
            className="h-full bg-buy/80 transition-all duration-fast"
            style={{ width: `${okPct}%` }}
          />
          <div
            className="h-full bg-sell/80 transition-all duration-fast"
            style={{ width: `${failedPct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task }: { task: BatchTask }) {
  return (
    <Tr>
      <Td className="text-fg">
        r{task.round} / d{task.day}
      </Td>
      <Td>
        <div className="flex items-center gap-2">
          <StatusBadge status={task.status} />
          {task.error && (
            <span className="text-xs text-sell" title={task.error}>
              {task.error.length > 40 ? task.error.slice(0, 40) + "…" : task.error}
            </span>
          )}
        </div>
      </Td>
      <Td
        className={cn(
          "text-right font-semibold",
          task.pnl_total !== null && task.pnl_total >= 0 && "text-buy",
          task.pnl_total !== null && task.pnl_total < 0 && "text-sell"
        )}
      >
        {task.pnl_total !== null ? formatCurrency(task.pnl_total) : "—"}
      </Td>
      <Td className="text-right text-muted-fg">
        {task.duration_ms !== null ? `${formatInt(task.duration_ms)} ms` : "—"}
      </Td>
      <Td>
        {task.run_id ? (
          <Link
            href={`/runs/${encodeURIComponent(task.run_id)}`}
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
