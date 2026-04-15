import Link from "next/link";
import { McCreateForm } from "@/components/mc/mc-create-form";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listDatasets, listStrategies } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function McNewPage() {
  let strategies;
  let datasets;
  try {
    [strategies, datasets] = await Promise.all([listStrategies(), listDatasets()]);
  } catch (error) {
    return (
      <div className="space-y-4">
        <Link
          href="/mc"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to monte carlo
        </Link>
        <ErrorCard title="could not reach API">
          <code className="font-mono">{String((error as Error).message)}</code>
        </ErrorCard>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="new monte carlo simulation"
        description="evaluate a strategy against many synthetic market paths."
      />
      <McCreateForm strategies={strategies} datasets={datasets} />
    </div>
  );
}
