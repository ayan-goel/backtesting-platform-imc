import Link from "next/link";
import { Suspense } from "react";
import { BatchesTable } from "@/components/batches-table";
import { buttonClasses } from "@/components/ui/button";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listBatches } from "@/lib/api";

export const dynamic = "force-dynamic";

async function BatchesList() {
  try {
    const batches = await listBatches(0, 100);
    return <BatchesTable batches={batches} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function BatchesPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="batches"
        description="one strategy, many (round, day) datasets."
        actions={
          <Link
            href="/batches/new"
            className={buttonClasses({ variant: "primary" })}
          >
            + new batch
          </Link>
        }
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading batches…</div>}
      >
        <BatchesList />
      </Suspense>
    </div>
  );
}
