import Link from "next/link";
import { Suspense } from "react";
import { StudyCreateForm } from "@/components/study-create-form";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listDatasets, listStrategies } from "@/lib/api";

export const dynamic = "force-dynamic";

async function NewStudy() {
  try {
    const [strategies, datasets] = await Promise.all([
      listStrategies(),
      listDatasets(),
    ]);
    return <StudyCreateForm strategies={strategies} datasets={datasets} />;
  } catch (error) {
    return (
      <ErrorCard title="could not load strategies / datasets">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function NewStudyPage() {
  return (
    <div className="space-y-8">
      <Link
        href="/studies"
        className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
      >
        ← back to studies
      </Link>
      <PageHeader
        title="new study"
        description="optuna hyperparameter search. pick a strategy + a single (round, day) + a search space, and we'll run n trials sequentially."
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading inputs…</div>}
      >
        <NewStudy />
      </Suspense>
    </div>
  );
}
