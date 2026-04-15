import Link from "next/link";
import { Suspense } from "react";
import { McTable } from "@/components/mc/mc-table";
import { buttonClasses } from "@/components/ui/button";
import { ErrorCard } from "@/components/ui/error-card";
import { PageHeader } from "@/components/ui/page-header";
import { listMcSimulations } from "@/lib/api";

export const dynamic = "force-dynamic";

async function McPanel() {
  try {
    const mcs = await listMcSimulations(0, 200);
    return <McTable mcs={mcs} />;
  } catch (error) {
    return (
      <ErrorCard title="could not reach API">
        <code className="font-mono">{String((error as Error).message)}</code>
      </ErrorCard>
    );
  }
}

export default function McPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="monte carlo"
        description="distribution-based strategy evaluation across synthetic market paths."
        actions={
          <Link href="/mc/new" className={buttonClasses({ variant: "primary" })}>
            + new simulation
          </Link>
        }
      />
      <Suspense
        fallback={<div className="text-sm text-muted-fg">loading simulations…</div>}
      >
        <McPanel />
      </Suspense>
    </div>
  );
}
