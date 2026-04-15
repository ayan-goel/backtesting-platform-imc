import Link from "next/link";
import { Suspense } from "react";
import { BatchCreateForm } from "@/components/batch-create-form";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listDatasets, listStrategies } from "@/lib/api";

export const dynamic = "force-dynamic";

async function NewBatch() {
  try {
    const [strategies, datasets] = await Promise.all([listStrategies(), listDatasets()]);
    return <BatchCreateForm strategies={strategies} datasets={datasets} />;
  } catch (error) {
    return (
      <ErrorCard title="could not load strategies / datasets">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function NewBatchPage() {
  return (
    <div className="space-y-8">
      <Link
        href="/batches"
        className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
      >
        ← back to batches
      </Link>
      <PageHeader
        title="new batch"
        description="run one strategy across multiple (round, day) datasets in parallel."
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading inputs…</div>}
      >
        <NewBatch />
      </Suspense>
    </div>
  );
}
