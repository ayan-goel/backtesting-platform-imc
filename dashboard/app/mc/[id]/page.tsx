import Link from "next/link";
import { McDetailView } from "@/components/mc/mc-detail-view";
import { ErrorCard } from "@/components/ui/error-card";
import { getMcSimulation } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function McDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: raw } = await params;
  const mcId = decodeURIComponent(raw);

  let doc;
  try {
    doc = await getMcSimulation(mcId);
  } catch {
    return (
      <div className="space-y-4">
        <Link
          href="/mc"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to monte carlo
        </Link>
        <ErrorCard title="could not load mc simulation">
          <code className="font-mono">{mcId}</code>
        </ErrorCard>
      </div>
    );
  }

  return <McDetailView mc={doc} />;
}
