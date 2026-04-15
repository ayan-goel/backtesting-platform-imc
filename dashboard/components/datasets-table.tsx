"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Dataset } from "@/lib/types";
import { formatInt, formatTimestamp } from "@/lib/utils";

interface DeletePreview {
  runs: number;
  batches: number;
  studies: number;
}

export function DatasetsTable({ datasets }: { datasets: Dataset[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<Dataset | null>(null);
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openDelete(d: Dataset) {
    setTarget(d);
    setPreview(null);
    setError(null);
    try {
      const res = await fetch(`/api/datasets/${d.round}/${d.day}/delete-preview`);
      if (!res.ok) throw new Error(`preview failed: ${res.status}`);
      setPreview((await res.json()) as DeletePreview);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function closeDialog() {
    if (loading) return;
    setTarget(null);
    setPreview(null);
    setError(null);
  }

  async function doDelete() {
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/datasets/${target.round}/${target.day}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      setTarget(null);
      setPreview(null);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (datasets.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no datasets uploaded yet — use the form below
      </div>
    );
  }

  const targetName = target ? `r${target.round}d${target.day}` : undefined;

  return (
    <>
      <Table>
        <Thead>
          <Tr>
            <Th>round / day</Th>
            <Th>products</Th>
            <Th className="text-right">timestamps</Th>
            <Th className="text-right">prices bytes</Th>
            <Th className="text-right">trades bytes</Th>
            <Th>uploaded</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {datasets.map((d) => (
            <Tr key={d._id}>
              <Td>
                r{d.round} / d{d.day}
              </Td>
              <Td>{d.products.join(", ")}</Td>
              <Td className="text-right">{formatInt(d.num_timestamps)}</Td>
              <Td className="text-right">{formatInt(d.prices_bytes)}</Td>
              <Td className="text-right">{formatInt(d.trades_bytes)}</Td>
              <Td>{formatTimestamp(d.uploaded_at)}</Td>
              <Td className="text-right">
                <button
                  type="button"
                  onClick={() => openDelete(d)}
                  className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell focus-visible:text-sell focus-visible:outline-none"
                  aria-label={`delete r${d.round}d${d.day}`}
                  title="delete dataset"
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
        title="delete dataset"
        description={
          target && (
            <>
              <code className="font-mono text-fg">{targetName}</code>{" "}
              <span className="text-muted-fg">· {target.products.join(", ")}</span>
            </>
          )
        }
        requireTypedConfirmation={targetName}
        loading={loading}
        error={error}
      >
        {preview ? (
          <div className="rounded-control border border-warn/40 bg-warn/5 p-3 text-xs text-warn">
            this will also delete{" "}
            <span className="font-semibold">{preview.runs}</span> run
            {preview.runs === 1 ? "" : "s"},{" "}
            <span className="font-semibold">{preview.batches}</span> batch
            {preview.batches === 1 ? "" : "es"}, and{" "}
            <span className="font-semibold">{preview.studies}</span> stud
            {preview.studies === 1 ? "y" : "ies"}.
          </div>
        ) : (
          <div className="text-xs text-muted-fg">calculating cascade…</div>
        )}
      </ConfirmDialog>
    </>
  );
}
