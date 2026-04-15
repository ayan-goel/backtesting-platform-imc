import { Suspense } from "react";
import { DatasetUpload } from "@/components/dataset-upload";
import { DatasetsTable } from "@/components/datasets-table";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listDatasets } from "@/lib/api";

export const dynamic = "force-dynamic";

async function DatasetsList() {
  try {
    const datasets = await listDatasets();
    return <DatasetsTable datasets={datasets} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function DatasetsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="datasets"
        description="drop a whole data folder — the server parses filenames and pairs prices/trades by (round, day). backtests look these up from the storage volume."
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading datasets…</div>}
      >
        <DatasetsList />
      </Suspense>
      <Card>
        <CardHeader>upload datasets</CardHeader>
        <DatasetUpload />
      </Card>
    </div>
  );
}
