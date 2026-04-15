"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { RunSummary } from "@/lib/types";
import { cn, formatCurrency, formatInt, formatTimestamp } from "@/lib/utils";

export function RunsTable({ runs }: { runs: RunSummary[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<RunSummary | null>(null);
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
      const res = await fetch(`/api/runs/${encodeURIComponent(target._id)}`, {
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

  if (runs.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no runs yet
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
            <Th>matcher</Th>
            <Th className="text-right">pnl</Th>
            <Th className="text-right">events</Th>
            <Th>status</Th>
            <Th>{""}</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {runs.map((run) => (
            <Tr key={run._id}>
              <Td>
                <Link
                  href={`/runs/${encodeURIComponent(run._id)}`}
                  className="text-muted-fg transition-colors duration-fast hover:text-fg"
                >
                  {formatTimestamp(run.created_at)}
                </Link>
              </Td>
              <Td>
                <Link
                  href={`/runs/${encodeURIComponent(run._id)}`}
                  className="font-medium text-fg transition-colors duration-fast hover:text-accent"
                >
                  {run.strategy_path}
                </Link>
              </Td>
              <Td className="text-muted-fg">
                r{run.round} / d{run.day}
              </Td>
              <Td className="text-muted-fg">{run.matcher}</Td>
              <Td
                className={cn(
                  "text-right font-semibold",
                  run.pnl_total >= 0 ? "text-buy" : "text-sell"
                )}
              >
                {formatCurrency(run.pnl_total)}
              </Td>
              <Td className="text-right text-muted-fg">{formatInt(run.num_events)}</Td>
              <Td className="text-muted-fg">{run.status}</Td>
              <Td className="text-right">
                <Link
                  href={`/compare?a=${encodeURIComponent(run._id)}`}
                  className="text-xs text-muted-fg transition-colors duration-fast hover:text-accent"
                  title="compare this run against another"
                >
                  compare →
                </Link>
              </Td>
              <Td className="text-right">
                <button
                  type="button"
                  onClick={() => setTarget(run)}
                  className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell focus-visible:text-sell focus-visible:outline-none"
                  aria-label={`delete run ${run._id}`}
                  title="delete run"
                >
                  ×
                </button>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>

      <ConfirmDialog
        open={target !== null}
        onClose={closeDialog}
        onConfirm={doDelete}
        title="delete run"
        description={
          target && <code className="font-mono text-fg">{target._id}</code>
        }
        loading={loading}
        error={error}
      >
        <div className="text-xs text-muted-fg">
          this removes the run doc and its artifact dir. any batch or study
          referencing it will show a broken link.
        </div>
      </ConfirmDialog>
    </>
  );
}
