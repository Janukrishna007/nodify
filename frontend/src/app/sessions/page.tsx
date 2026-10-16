import { SessionHistory } from '@/components/workspace/SessionHistory';

export default async function SessionsPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = '' } = await searchParams;
  return <SessionHistory key={q} initialQuery={q} />;
}
