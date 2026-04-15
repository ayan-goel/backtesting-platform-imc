"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Study } from "@/lib/types";
import { formatInt, formatTimestamp } from "@/lib/utils";

export function StudiesTable({ studies }: { studies: Study[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<Study | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function closeDialog() {
    if (loading) return;
    setTarget(null);
    setError(null);
  }

  async function doDelete() {
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/studies/${encodeURIComponent(target._id)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      setTarget(null);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (studies.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no studies yet —{" "}
        <Link
          href="/studies/new"
          className="text-accent transition-colors duration-fast hover:underline"
        >
          create one
        </Link>
      </div>
    );
  }

  return (
    <>
      <Table>
        <Thead>
          <Tr>
            <Th>created</Th>
            <Th>strategy</Th>
            <Th>round / day</Th>
            <Th className="text-right">params</Th>
            <Th className="text-right">progress</Th>
            <Th className="text-right">best</Th>
            <Th>status</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {studies.map((s) => {
            const paramCount = Object.keys(s.space).length;
            const done = s.progress.completed + s.progress.failed;
            const isTerminal =
              s.status === "succeeded" ||
              s.status === "failed" ||
              s.status === "cancelled";
            return (
              <Tr key={s._id}>
                <Td>
                  <Link
                    href={`/studies/${encodeURIComponent(s._id)}`}
                    className="text-muted-fg transition-colors duration-fast hover:text-fg"
                  >
                    {formatTimestamp(s.created_at)}
                  </Link>
                </Td>
                <Td>
                  <Link
                    href={`/studies/${encodeURIComponent(s._id)}`}
                    className="font-medium text-fg transition-colors duration-fast hover:text-accent"
                  >
                    {s.strategy_filename}
                  </Link>
                </Td>
                <Td className="text-muted-fg">
                  r{s.round} / d{s.day}
                </Td>
                <Td className="text-right tabular-nums text-muted-fg">{paramCount}</Td>
                <Td className="text-right tabular-nums">
                  <span className="text-fg">{formatInt(done)}</span>
                  <span className="text-muted-fg"> / {formatInt(s.progress.total)}</span>
                  {s.progress.failed > 0 && (
                    <span className="ml-2 text-sell">· {s.progress.failed} failed</span>
                  )}
                </Td>
                <Td className="text-right tabular-nums font-semibold text-fg">
                  {s.best_trial !== null ? s.best_trial.value.toFixed(2) : "—"}
                </Td>
                <Td>
                  <StatusBadge status={s.status} />
                </Td>
                <Td className="text-right">
                  <button
                    type="button"
                    onClick={() => setTarget(s)}
                    disabled={!isTerminal}
                    className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell disabled:opacity-30 disabled:cursor-not-allowed focus-visible:text-sell focus-visible:outline-none"
                    aria-label={`delete study ${s._id}`}
                    title={
                      isTerminal ? "delete study" : "cancel it first"
                    }
                  >
                    ×
                  </button>
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>

      <ConfirmDialog
        open={target !== null}
        onClose={closeDialog}
        onConfirm={doDelete}
        title="delete study"
        description={
          target && <code className="font-mono text-fg">{target._id}</code>
        }
        loading={loading}
        error={error}
      >
        <div className="text-xs text-muted-fg">
          this removes the study doc and its optuna SQLite file. the child
          trial runs stay where they are.
        </div>
      </ConfirmDialog>
    </>
  );
}
