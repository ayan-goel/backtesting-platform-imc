import Link from "next/link";
import { StudyDetailView } from "@/components/study-detail-view";
import { ErrorCard } from "@/components/ui/error-card";
import { getStudy, listStudyTrials } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function StudyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: rawId } = await params;
  const studyId = decodeURIComponent(rawId);

  try {
    const [study, trials] = await Promise.all([
      getStudy(studyId),
      listStudyTrials(studyId),
    ]);
    return <StudyDetailView initial={study} initialTrials={trials} />;
  } catch {
    return (
      <div className="space-y-4">
        <Link
          href="/studies"
          className="text-xs text-muted-fg transition-colors duration-fast hover:text-fg"
        >
          ← back to studies
        </Link>
        <ErrorCard title="could not load study">
          <code className="font-mono">{studyId}</code>
        </ErrorCard>
      </div>
    );
  }
}
