import Link from "next/link";
import { Suspense } from "react";
import { StudiesTable } from "@/components/studies-table";
import { buttonClasses } from "@/components/ui/button";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listStudies } from "@/lib/api";

export const dynamic = "force-dynamic";

async function StudiesPanel() {
  try {
    const studies = await listStudies(0, 200);
    return <StudiesTable studies={studies} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function StudiesPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="studies"
        description="optuna hyperparameter searches. sorted by created_at desc."
        actions={
          <Link
            href="/studies/new"
            className={buttonClasses({ variant: "primary" })}
          >
            + new study
          </Link>
        }
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading studies…</div>}
      >
        <StudiesPanel />
      </Suspense>
    </div>
  );
}
