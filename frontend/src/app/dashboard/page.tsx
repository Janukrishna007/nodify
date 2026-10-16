import { WorkspaceOverview } from '@/components/workspace/WorkspaceOverview';
import { AnalysisDashboard } from '@/components/dashboard/AnalysisDashboard';

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<{ session?: string }>;
}) {
  const { session } = await searchParams;
  if (!session) return <WorkspaceOverview />;
  return <AnalysisDashboard key={session} sessionId={session} />;
}
