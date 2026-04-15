import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Suspense } from "react";
import { CompareView } from "@/components/compare-view";
import { ReplayErrorBoundary } from "@/components/replay/replay-error-boundary";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listRuns } from "@/lib/api";

export const dynamic = "force-dynamic";

async function ComparePanel() {
  try {
    const runs = await listRuns(0, 200);
    return (
      <NuqsAdapter>
        <ReplayErrorBoundary>
          <CompareView runs={runs} />
        </ReplayErrorBoundary>
      </NuqsAdapter>
    );
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function ComparePage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="compare"
        description="side-by-side view of two runs on the same (round, day)."
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading runs…</div>}
      >
        <ComparePanel />
      </Suspense>
    </div>
  );
}
