"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { McSimulation } from "@/lib/types";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

export function McTable({ mcs }: { mcs: McSimulation[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<McSimulation | null>(null);
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
      const res = await fetch(`/api/mc/${encodeURIComponent(target._id)}`, {
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

  if (mcs.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no simulations yet —{" "}
        <Link
          href="/mc/new"
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
            <Th>generator</Th>
            <Th className="text-right">paths</Th>
            <Th className="text-right">progress</Th>
            <Th className="text-right">mean pnl</Th>
            <Th>status</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {mcs.map((m) => {
            const done = m.progress.completed + m.progress.failed;
            const isTerminal =
              m.status === "succeeded" ||
              m.status === "failed" ||
              m.status === "cancelled";
            const meanPnl = m.aggregate?.pnl_mean ?? null;
            return (
              <Tr key={m._id}>
                <Td>
                  <Link
                    href={`/mc/${encodeURIComponent(m._id)}`}
                    className="text-muted-fg transition-colors duration-fast hover:text-fg"
                  >
                    {formatTimestamp(m.created_at)}
                  </Link>
                </Td>
                <Td>
                  <Link
                    href={`/mc/${encodeURIComponent(m._id)}`}
                    className="font-medium text-fg transition-colors duration-fast hover:text-accent"
                  >
                    {m.strategy_filename}
                  </Link>
                </Td>
                <Td className="text-muted-fg">
                  r{m.round} / d{m.day}
                </Td>
                <Td className="font-mono text-xs text-muted-fg">
                  {m.generator.type}
                </Td>
                <Td className="text-right tabular-nums text-fg">
                  {formatInt(m.n_paths)}
                </Td>
                <Td className="text-right tabular-nums">
                  <span className="text-fg">{formatInt(done)}</span>
                  <span className="text-muted-fg"> / {formatInt(m.progress.total)}</span>
                  {m.progress.failed > 0 && (
                    <span className="ml-2 text-sell">· {m.progress.failed} failed</span>
                  )}
                </Td>
                <Td
                  className={cn(
                    "text-right tabular-nums font-semibold",
                    meanPnl === null
                      ? "text-muted-fg"
                      : meanPnl >= 0
                      ? "text-buy"
                      : "text-sell"
                  )}
                >
                  {meanPnl === null ? "—" : formatCurrency(meanPnl)}
                </Td>
                <Td>
                  <StatusBadge status={m.status} />
                </Td>
                <Td className="text-right">
                  <button
                    type="button"
                    onClick={() => setTarget(m)}
                    disabled={!isTerminal}
                    className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell disabled:cursor-not-allowed disabled:opacity-30 focus-visible:text-sell focus-visible:outline-none"
                    aria-label={`delete mc simulation ${m._id}`}
                    title={isTerminal ? "delete simulation" : "cancel it first"}
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
        title="delete monte carlo simulation"
        description={
          target && <code className="font-mono text-fg">{target._id}</code>
        }
        loading={loading}
        error={error}
      >
        <div className="text-xs text-muted-fg">
          removes the mc doc, its aggregate stats, and all per-path artifacts.
        </div>
      </ConfirmDialog>
    </>
  );
}
