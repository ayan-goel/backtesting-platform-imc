import Link from "next/link";
import { Suspense } from "react";
import { RunCreateForm } from "@/components/run-create-form";
import { RunsTable } from "@/components/runs-table";
import { buttonClasses } from "@/components/ui/button";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listDatasets, listRuns, listStrategies } from "@/lib/api";

export const dynamic = "force-dynamic";

async function RunsList() {
  try {
    const runs = await listRuns(0, 100);
    return <RunsTable runs={runs} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

async function NewRun() {
  try {
    const [strategies, datasets] = await Promise.all([listStrategies(), listDatasets()]);
    return <RunCreateForm strategies={strategies} datasets={datasets} />;
  } catch (error) {
    return (
      <ErrorCard title="could not load strategies / datasets">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function HomePage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="home"
        title="runs"
        description="all local + remote backtests. click a row to open the replay view."
        actions={
          <>
            <Link href="/batches/new" className={buttonClasses({ variant: "secondary" })}>
              new batch →
            </Link>
            <Link href="/studies/new" className={buttonClasses({ variant: "primary" })}>
              new study →
            </Link>
          </>
        }
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading runs…</div>}
      >
        <RunsList />
      </Suspense>
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading inputs…</div>}
      >
        <NewRun />
      </Suspense>
    </div>
  );
}
