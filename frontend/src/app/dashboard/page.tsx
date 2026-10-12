import Link from 'next/link';
import { AnalysisDashboard } from '@/components/dashboard/AnalysisDashboard';

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<{ session?: string }>;
}) {
  const { session } = await searchParams;
  if (!session) return <main className='mx-auto max-w-3xl space-y-4 p-12'>
    <h1 className='text-2xl font-semibold'>Choose a video to analyze</h1>
    <p className='text-white/60'>Upload footage or open a saved analysis to inspect its detections and heatmaps.</p>
    <Link className='inline-block rounded-xl bg-white px-5 py-3 text-black' href='/upload'>Open video upload</Link>
  </main>;
  return <AnalysisDashboard key={session} sessionId={session} />;
}
