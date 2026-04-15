"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Batch } from "@/lib/types";
import { formatInt, formatTimestamp } from "@/lib/utils";

export function BatchesTable({ batches }: { batches: Batch[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<Batch | null>(null);
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
      const res = await fetch(`/api/batches/${encodeURIComponent(target._id)}`, {
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

  if (batches.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no batches yet —{" "}
        <Link
          href="/batches/new"
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
            <Th>matcher</Th>
            <Th className="text-right">progress</Th>
            <Th>status</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {batches.map((b) => {
            const isTerminal =
              b.status === "succeeded" || b.status === "failed";
            return (
              <Tr key={b._id}>
                <Td>
                  <Link
                    href={`/batches/${encodeURIComponent(b._id)}`}
                    className="text-muted-fg transition-colors duration-fast hover:text-fg"
                  >
                    {formatTimestamp(b.created_at)}
                  </Link>
                </Td>
                <Td>
                  <Link
                    href={`/batches/${encodeURIComponent(b._id)}`}
                    className="font-medium text-fg transition-colors duration-fast hover:text-accent"
                  >
                    {b.strategy_filename}
                  </Link>
                </Td>
                <Td className="text-muted-fg">{b.matcher}</Td>
                <Td className="text-right tabular-nums">
                  <span className="text-fg">
                    {formatInt(b.progress.completed + b.progress.failed)}
                  </span>
                  <span className="text-muted-fg"> / {formatInt(b.progress.total)}</span>
                  {b.progress.failed > 0 && (
                    <span className="ml-2 text-sell">· {b.progress.failed} failed</span>
                  )}
                </Td>
                <Td>
                  <StatusBadge status={b.status} />
                </Td>
                <Td className="text-right">
                  <button
                    type="button"
                    onClick={() => setTarget(b)}
                    disabled={!isTerminal}
                    className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell disabled:opacity-30 disabled:cursor-not-allowed focus-visible:text-sell focus-visible:outline-none"
                    aria-label={`delete batch ${b._id}`}
                    title={
                      isTerminal ? "delete batch" : "cancel it first"
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
        title="delete batch"
        description={
          target && <code className="font-mono text-fg">{target._id}</code>
        }
        loading={loading}
        error={error}
      >
        <div className="text-xs text-muted-fg">
          this removes the batch doc only. the child runs stay where they are.
        </div>
      </ConfirmDialog>
    </>
  );
}
