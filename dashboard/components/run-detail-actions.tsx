"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, buttonClasses } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export function RunDetailActions({ runId }: { runId: string }) {
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onDelete() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status}: ${detail}`);
      }
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  }

  return (
    <>
      <div className="flex gap-2">
        <Link
          href={`/compare?a=${encodeURIComponent(runId)}`}
          className={buttonClasses({ variant: "secondary", size: "sm" })}
        >
          compare with… →
        </Link>
        <Link
          href="/studies/new"
          className={buttonClasses({ variant: "secondary", size: "sm" })}
          title="run an optuna hyperparameter search"
        >
          new study →
        </Link>
        <Button
          variant="danger"
          size="sm"
          onClick={() => setConfirmOpen(true)}
          title="delete this run"
        >
          delete
        </Button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => {
          if (!loading) {
            setConfirmOpen(false);
            setError(null);
          }
        }}
        onConfirm={onDelete}
        title="delete run"
        description={
          <>
            <code className="font-mono text-fg">{runId}</code>
          </>
        }
        loading={loading}
        error={error}
      >
        <div className="text-xs text-muted-fg">
          this removes the run doc and its artifact dir. batches / studies
          that reference this run will show a broken link.
        </div>
      </ConfirmDialog>
    </>
  );
}
