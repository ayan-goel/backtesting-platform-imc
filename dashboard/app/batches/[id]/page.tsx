import Link from "next/link";
import { BatchDetailView } from "@/components/batch-detail-view";
import { ErrorCard } from "@/components/ui/error-card";
import { getBatch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function BatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idRaw } = await params;
  const batchId = decodeURIComponent(idRaw);

  try {
    const batch = await getBatch(batchId);
    return <BatchDetailView initial={batch} />;
  } catch {
    return (
      <div className="space-y-4">
        <Link
          href="/batches"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to batches
        </Link>
        <ErrorCard title="could not load batch">
          <code className="font-mono">{batchId}</code>
        </ErrorCard>
      </div>
    );
  }
}
