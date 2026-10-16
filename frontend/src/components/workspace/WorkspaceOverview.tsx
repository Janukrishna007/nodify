'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Activity, ArrowRight, ArrowUpRight, Bell, CheckCheck, FileVideo, Flame, Focus, Layers3, Radio, ScanLine, Upload, Waves, Wind } from 'lucide-react';
import { useWorkspace } from './WorkspaceProvider';
import { MetricCard, PageHeading, SessionTable, StatusBadge } from './DashboardPrimitives';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from '@/components/ui/empty';
import { fetchFrame } from '@/services/api';
import { number, sessionHref, title } from '@/lib/presentation';
import { useUIStore, type FrameData } from '@/lib/state';
import { CumulativePanel } from '@/components/dashboard/CumulativePanel';

export function WorkspaceOverview() {
  const { sessions, connected, loading, error, activeSession } = useWorkspace();
  const latest = sessions.find((session) => session.analyzedFrames > 0 && session.status !== 'failed');
  const [preview, setPreview] = useState<{ id: string; frame: FrameData }>();
  const frame = preview?.id === latest?.id ? preview?.frame : undefined;
  const { filters } = useUIStore();
  useEffect(() => {
    let mounted = true;
    if (latest?.id && latest.latestIndex !== null) {
      void fetchFrame(latest.id, latest.latestIndex).then((result) => { if (mounted) setPreview({ id: latest.id, frame: result }); }).catch(() => {});
    }
    return () => { mounted = false; };
  }, [latest?.id, latest?.latestIndex]);
  const frames = sessions.reduce((sum, session) => sum + session.analyzedFrames, 0);
  const counts = { fire: 0, smoke: 0, flood: 0 };
  sessions.forEach((session) => { for (const key of ['fire', 'smoke', 'flood'] as const) counts[key] += session.detectionCounts[key] ?? 0; });
  const total = counts.fire + counts.smoke + counts.flood;
  const alerts = sessions.flatMap((session) => session.alerts ?? []).filter((alert) => !alert.acknowledgedAt);
  const hazards = [{ key: 'fire', label: 'Fire', icon: Flame, color: 'text-fire', bar: 'bg-fire' }, { key: 'smoke', label: 'Smoke', icon: Wind, color: 'text-smoke', bar: 'bg-smoke' }, { key: 'flood', label: 'Flood', icon: Waves, color: 'text-flood', bar: 'bg-flood' }] as const;

  return <main className='fade-in flex flex-col gap-6'>
    <PageHeading eyebrow='Your response starts here' title='Intelligence overview' description='A clear view of your footage, detected hazards and the areas that need attention.' actions={<Button asChild><Link href='/upload'><Upload data-icon='inline-start' />New analysis</Link></Button>} />
    {error && <Alert variant='destructive'><Radio /><AlertTitle>Analysis service disconnected</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    <section className='grid grid-cols-2 gap-3 xl:grid-cols-4'>
      <MetricCard label='Total analyses' value={loading ? '—' : number(sessions.length)} detail={`${sessions.filter((session) => session.status === 'completed').length} completed sessions`} icon={FileVideo} />
      <MetricCard label='Frames analyzed' value={loading ? '—' : number(frames)} detail='Sampled frames processed by your models' icon={Layers3} tone='flood' />
      <MetricCard label='Hazard detections' value={loading ? '—' : number(total)} detail='Fire, smoke and flood observations' icon={Focus} tone='fire' />
      <MetricCard label='Open alerts' value={loading ? '—' : number(alerts.length)} detail='Alerts waiting for acknowledgement' icon={Bell} tone='warning' />
    </section>
    <section className='grid gap-5 xl:grid-cols-[1.65fr_1fr]'>
      <Card className='hero-panel'><CardHeader><div className='flex items-center gap-2'><span className={connected ? 'status-dot text-primary' : 'status-dot text-muted-foreground'} /><p className='eyebrow'>{connected ? 'Analysis workspace ready' : 'Connect your analysis service'}</p></div></CardHeader><CardContent className='relative flex min-h-40 items-center justify-between gap-5'>
        <div className='relative z-10 flex max-w-md flex-col gap-4'><h2 className='text-[25px] font-medium leading-tight tracking-tight md:text-[30px]'>From aerial footage.<br /><span className='text-primary'>To actionable insight.</span></h2><p className='max-w-sm text-xs leading-6 text-muted-foreground'>Detect hazards, track their presence, and understand spatial risk. All from one focused workspace.</p><div className='flex flex-wrap items-center gap-3'><Button asChild size='sm'><Link href={activeSession ? sessionHref(activeSession) : '/upload'}>{activeSession ? 'Continue live analysis' : 'Analyze new footage'}<ArrowRight data-icon='inline-end' /></Link></Button><span className='flex items-center gap-1.5 text-[10px] text-muted-foreground'><CheckCheck className='size-3.5 text-primary' />Processed locally</span></div></div>
        <div aria-hidden='true' className='relative hidden size-48 shrink-0 items-center justify-center sm:flex'><div className='absolute inset-0 rounded-full border border-primary/10 bg-primary/[.025]' /><div className='absolute inset-6 rounded-full border border-primary/15' /><div className='absolute inset-12 rounded-full border border-primary/20 bg-primary/5' /><div className='absolute inset-x-1 top-1/2 border-t border-primary/10' /><div className='absolute inset-y-1 left-1/2 border-l border-primary/10' /><ScanLine className='relative size-14 text-primary/80' strokeWidth={1} /><span className='absolute left-8 top-10 size-2 rounded-full bg-primary shadow-[0_0_15px_var(--primary)]' /><span className='absolute bottom-9 right-10 size-1.5 rounded-full bg-flood' /><span className='absolute bottom-2 left-1/2 -translate-x-1/2 text-[8px] tracking-[.2em] text-primary/50'>DETECT · ANALYZE · RESPOND</span></div>
      </CardContent></Card>
      <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Detection breakdown</CardTitle><CardDescription>Observation mix across all sessions</CardDescription></div><Activity className='size-4 text-muted-foreground' /></CardHeader><CardContent className='flex flex-col gap-5'>
        {hazards.map((hazard) => <div key={hazard.key} className='flex flex-col gap-2.5'><div className='flex items-center justify-between text-xs'><span className='flex items-center gap-2'><hazard.icon className={`size-3.5 ${hazard.color}`} />{hazard.label}</span><span className='font-mono text-muted-foreground'>{number(counts[hazard.key])}<span className='ml-3 text-[10px]'>{total ? Math.round(counts[hazard.key] / total * 100) : 0}%</span></span></div><div className='h-1.5 overflow-hidden rounded-full bg-muted'><div className={`h-full rounded-full ${hazard.bar}`} style={{ width: `${total ? counts[hazard.key] / total * 100 : 0}%` }} /></div></div>)}
        <p className='text-[10px] text-muted-foreground'>Counts represent observations, not unique objects.</p>
      </CardContent></Card>
    </section>
    <section className='grid gap-5 xl:grid-cols-[1.65fr_1fr]'>
      <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Latest analysis</CardTitle><CardDescription>{latest ? title(latest.filename) : 'Your next perspective starts with a video'}</CardDescription></div>{latest && <StatusBadge status={latest.status} />}</CardHeader><CardContent>
        {latest ? <Link href={sessionHref(latest.id)} className='group relative block h-[230px] overflow-hidden rounded-xl border border-border bg-background'>
          {frame ? <Image src={frame.heatmapUrl} alt='Latest analyzed footage with detection heatmap' fill unoptimized className='object-cover object-center transition-transform duration-500 group-hover:scale-[1.02]' /> : <Skeleton className='size-full' />}
          <div className='absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent' /><div className='absolute inset-x-4 bottom-4 flex items-end justify-between'><div className='flex flex-col gap-1'><p className='text-[10px] uppercase tracking-wider text-primary'>Analysis ready to explore</p><p className='text-xs text-foreground'>{number(latest.analyzedFrames)} frames · Fire, smoke & flood</p></div><span className='flex size-8 items-center justify-center rounded-full border border-border bg-background/60 backdrop-blur'><ArrowUpRight className='size-4' /></span></div>
        </Link> : <Empty><EmptyHeader><EmptyMedia variant='icon'><VideoIcon /></EmptyMedia><EmptyTitle>No footage analyzed yet</EmptyTitle><EmptyDescription>Your latest analysis preview will appear here.</EmptyDescription></EmptyHeader><Button asChild size='sm'><Link href='/upload'>Upload your first video</Link></Button></Empty>}
      </CardContent></Card>
      <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Response activity</CardTitle><CardDescription>Latest alerts from your analyses</CardDescription></div><Badge variant='secondary'>{alerts.length} open</Badge></CardHeader><CardContent className='flex flex-col gap-4'>
        {alerts.length ? alerts.slice(-3).reverse().map((alert) => <Link key={alert.id} href={sessionHref(alert.sessionId)} className='flex items-start gap-3 rounded-xl border border-border bg-background/25 p-3'><span className='mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg bg-warning/10 text-warning'><Bell className='size-3.5' /></span><span className='flex min-w-0 flex-col gap-1'><span className='text-xs font-medium capitalize'>{alert.type} · {alert.severity} intensity</span><span className='line-clamp-2 text-[11px] leading-5 text-muted-foreground'>{alert.message}</span></span></Link>) : <div className='flex min-h-40 flex-col items-center justify-center gap-2 text-center'><CheckCheck className='size-7 text-success/70' /><p className='text-xs'>All clear for now</p><p className='text-[11px] text-muted-foreground'>No alerts waiting for acknowledgement.</p></div>}
        <Button asChild variant='ghost' size='sm'><Link href='/alerts'>View alert center<ArrowRight data-icon='inline-end' /></Link></Button>
      </CardContent></Card>
    </section>
    <SessionTable sessions={sessions.slice(0, 4)} actions={<Button asChild variant='ghost' size='sm'><Link href='/sessions'>View all<ArrowRight data-icon='inline-end' /></Link></Button>} />
    {frame && <CumulativePanel cells={frame.cells} filters={filters} />}
  </main>;
}

function VideoIcon() { return <Radio />; }
