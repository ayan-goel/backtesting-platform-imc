import { Suspense } from "react";
import { StrategiesTable } from "@/components/strategies-table";
import { StrategyUpload } from "@/components/strategy-upload";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listStrategies } from "@/lib/api";

export const dynamic = "force-dynamic";

async function StrategiesList() {
  try {
    const strategies = await listStrategies();
    return <StrategiesTable strategies={strategies} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function StrategiesPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="strategies"
        description="upload python trader files. each upload is content-addressed — re-uploading the same file returns the same id."
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading strategies…</div>}
      >
        <StrategiesList />
      </Suspense>
      <Card>
        <CardHeader>upload strategy</CardHeader>
        <StrategyUpload />
      </Card>
    </div>
  );
}
