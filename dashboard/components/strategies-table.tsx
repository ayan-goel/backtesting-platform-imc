"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/table";
import type { Strategy } from "@/lib/types";
import { formatInt, formatTimestamp } from "@/lib/utils";

interface DeletePreview {
  runs: number;
  batches: number;
  studies: number;
}

export function StrategiesTable({ strategies }: { strategies: Strategy[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<Strategy | null>(null);
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openDelete(s: Strategy) {
    setTarget(s);
    setPreview(null);
    setError(null);
    try {
      const res = await fetch(
        `/api/strategies/${encodeURIComponent(s._id)}/delete-preview`
      );
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
      const res = await fetch(
        `/api/strategies/${encodeURIComponent(target._id)}`,
        { method: "DELETE" }
      );
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

  if (strategies.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center text-sm text-muted-fg">
        no strategies uploaded yet — drop a Python file below
      </div>
    );
  }

  return (
    <>
      <Table>
        <Thead>
          <Tr>
            <Th>id</Th>
            <Th>filename</Th>
            <Th>sha256</Th>
            <Th className="text-right">size</Th>
            <Th>uploaded</Th>
            <Th>{""}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {strategies.map((s) => (
            <Tr key={s._id}>
              <Td>{s._id}</Td>
              <Td>{s.filename}</Td>
              <Td className="text-muted-fg">{s.sha256.slice(7, 19)}…</Td>
              <Td className="text-right">{formatInt(s.size_bytes)}</Td>
              <Td>{formatTimestamp(s.uploaded_at)}</Td>
              <Td className="text-right">
                <button
                  type="button"
                  onClick={() => openDelete(s)}
                  className="text-base leading-none text-muted-fg transition-colors duration-fast hover:text-sell focus-visible:text-sell focus-visible:outline-none"
                  aria-label={`delete ${s.filename}`}
                  title="delete strategy"
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
        title="delete strategy"
        description={
          target && (
            <>
              <code className="font-mono text-fg">{target.filename}</code>{" "}
              <span className="text-muted-fg">· {target._id}</span>
            </>
          )
        }
        requireTypedConfirmation={target?.filename}
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
