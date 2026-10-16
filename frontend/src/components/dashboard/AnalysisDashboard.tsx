'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowUpRight, Bell, BellOff, ChevronLeft, ChevronRight, CircleAlert, Download, Flame, Focus, Layers3, LoaderCircle, Pause, Play, Radio, RotateCcw, Square, Waves, Wind } from 'lucide-react';
import { cellRisk, useUIStore, type DisasterType, type FrameData, type Session, type Zone } from '@/lib/state';
import { acknowledgeAlert, cancelAnalysis, fetchFrame } from '@/services/api';
import { connectAnalysis } from '@/services/socket';
import { VideoFeed } from '@/components/video/VideoFeed';
import { Sidebar } from './Sidebar';
import { CumulativePanel } from './CumulativePanel';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Slider } from '@/components/ui/slider';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { PageHeading, MetricCard, StatusBadge } from '@/components/workspace/DashboardPrimitives';
import { AlertFeed } from '@/components/workspace/AlertFeed';
import { number, time, title } from '@/lib/presentation';
import { useBrowserAlerts } from '@/lib/browser-alerts';

export function AnalysisDashboard({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<Session>();
  const [latest, setLatest] = useState<FrameData>();
  const [review, setReview] = useState<FrameData>();
  const [error, setError] = useState('');
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [selectedZone, setSelectedZone] = useState<string>();
  const [loadingFrame, setLoadingFrame] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [playing, setPlaying] = useState(false);
  const requestIndex = useRef(0);
  const notifiedAlerts = useRef(new Set<string>());
  const { filters, toggleFilter } = useUIStore();
  const browserAlerts = useBrowserAlerts();
  const frame = review ?? latest;
  const running = !!session && ['queued', 'loading', 'processing'].includes(session.status);
  const oldestFrame = session?.oldestFrameIndex ?? 0;
  useEffect(() => connectAnalysis(sessionId, (updated, result) => {
    setSession(updated); if (result) setLatest(result); setError('');
    setReview((current) => current && current.index < (updated.oldestFrameIndex ?? 0) ? undefined : current);
    for (const alert of updated.alerts ?? []) {
      if (!notifiedAlerts.current.has(alert.id)) {
        notifiedAlerts.current.add(alert.id);
        if (browserAlerts.enabled && 'Notification' in window && Notification.permission === 'granted') new Notification('DisasterVision alert', { body: alert.message });
      }
    }
  }, setError), [sessionId, browserAlerts.enabled]);
  const enableBrowserAlerts = async () => {
    if (browserAlerts.enabled) { browserAlerts.disable(); setError(''); return; }
    try { await browserAlerts.enable(); setError(''); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not enable browser alerts.'); }
  };
  const acknowledge = async (alertId: string) => {
    try {
      const updated = await acknowledgeAlert(sessionId, alertId);
      setSession((current) => current ? { ...current, alerts: (current.alerts ?? []).map((item) => item.id === alertId ? updated : item) } : current);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not acknowledge alert.'); }
  };
  const zones = useMemo(() => (frame?.cells ?? []).map((cell): Zone => {
    const severity = cellRisk(cell, filters);
    const classes = (Object.keys(filters) as DisasterType[]).filter((key) => filters[key] && cell.byClass[key].score > 0.01);
    return { ...cell, id: `${cell.row}-${cell.col}`, type: classes.join(', '), severity };
  }).filter((zone) => zone.severity >= 0.01).sort((a, b) => b.severity - a.severity), [frame, filters]);
  const inspect = useCallback(async (index: number) => {
    const token = ++requestIndex.current;
    setLoadingFrame(true);
    try {
      const result = await fetchFrame(sessionId, Math.max(oldestFrame, index));
      if (token === requestIndex.current) { setReview(result); setError(''); }
    } catch (failure) {
      if (token === requestIndex.current) setError(failure instanceof Error ? failure.message : 'Could not load frame.');
    } finally { if (token === requestIndex.current) setLoadingFrame(false); }
  }, [sessionId, oldestFrame]);
  useEffect(() => {
    if (!playing || !frame || loadingFrame) return;
    const timer = setTimeout(() => {
      if (frame.index >= (session?.analyzedFrames ?? 1) - 1) setPlaying(false);
      else void inspect(frame.index + 1);
    }, 450);
    return () => clearTimeout(timer);
  }, [playing, frame, loadingFrame, session?.analyzedFrames, inspect]);
  const stop = async () => {
    setStopping(true);
    try { await cancelAnalysis(sessionId); } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not stop analysis.'); setStopping(false); }
  };
  const visibleDetections = frame?.detections.filter((detection) => filters[detection.type]) ?? [];

  return <main className='fade-in flex flex-col gap-6'>
    <div className='flex items-center justify-between gap-3'><Button asChild variant='ghost' size='sm'><Link href='/sessions'><ArrowLeft data-icon='inline-start' />All sessions</Link></Button><span className='font-mono text-[9px] uppercase tracking-widest text-muted-foreground'>SESSION / {sessionId.slice(0, 8)}</span></div>
    <PageHeading eyebrow={session?.isLive ? 'Drone intelligence' : 'Analysis console'} title={session ? (session.isLive ? session.filename : title(session.filename)) : 'Preparing your analysis'} description={session?.isLive ? `RTSP live analysis · ${session.sourceAddress}` : session ? session.filename : 'Connecting to your saved footage and model results.'}
      actions={<>{running && <Button variant='destructive' disabled={stopping} onClick={() => void stop()}><Square data-icon='inline-start' />{stopping ? 'Stopping…' : 'Stop analysis'}</Button>}<Button variant='outline' aria-pressed={browserAlerts.enabled} onClick={() => void enableBrowserAlerts()}>{browserAlerts.enabled ? <BellOff data-icon='inline-start' /> : <Bell data-icon='inline-start' />}{browserAlerts.enabled ? 'Disable browser alerts' : 'Enable browser alerts'}</Button>{!!session?.analyzedFrames && <Button asChild><a href={`/api/sessions/${sessionId}/report`} download={`${session.filename}-analysis.json`}><Download data-icon='inline-start' />Download report</a></Button>}</>} />
    {(error || session?.error) && <Alert variant='destructive'><CircleAlert /><AlertTitle>Analysis needs attention</AlertTitle><AlertDescription>{error || session?.error}</AlertDescription></Alert>}
    <div className='flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card/30 px-4 py-3'>
      {session ? <StatusBadge status={session.status} /> : <Badge variant='outline'><LoaderCircle className='animate-spin' />Connecting</Badge>}
      <span className='text-[11px] text-muted-foreground'>{session ? `${number(session.analyzedFrames)}${session.expectedSamples ? ' / ' + number(session.expectedSamples) : ''} frames analyzed` : 'Waiting for results'}</span>
      {session?.isLive ? <><Badge variant='outline'><Radio />{({ connecting: 'Connecting to drone', connected: 'Stream connected', reconnecting: 'Reconnecting', disconnected: 'Stream ended' } as const)[session.connectionState ?? 'connecting']}</Badge><span className='ml-auto font-mono text-[10px] text-primary'>{time(session.elapsedSeconds ?? 0)} elapsed</span></> : <><div className='min-w-24 flex-1'><Progress value={session?.progress ?? 0} aria-label='Analysis progress' /></div><span className='font-mono text-[10px] text-primary'>{session?.progress.toFixed(1) ?? '0'}%</span></>}
      {session?.tracker && <span className='flex items-center gap-1.5 text-[10px] text-muted-foreground'><Focus className='size-3.5' />{session.tracker} tracking</span>}
    </div>
    {session?.isLive && <Alert><Radio /><AlertTitle>{session.connectionState === 'reconnecting' ? `Connection interrupted · retry ${session.reconnectAttempts ?? 1} of 3` : 'Live drone analysis'}</AlertTitle><AlertDescription>Analyzes the latest available samples to keep up with your feed. {number(session.droppedSamples ?? 0)} samples skipped while inference was busy. Review retains the latest {session.retainedFrameLimit ?? 300} analyzed frames; totals and cumulative heatmaps cover the whole session. Heatmaps use camera-frame coordinates.</AlertDescription></Alert>}
    <section className='grid grid-cols-2 gap-3 xl:grid-cols-4'>
      <MetricCard label='Fire detections' value={session ? number(session.detectionCounts.fire ?? 0) : '—'} detail={`${session?.uniqueTrackCounts?.fire ?? 0} unique tracks`} icon={Flame} tone='fire' />
      <MetricCard label='Smoke detections' value={session ? number(session.detectionCounts.smoke ?? 0) : '—'} detail={`${session?.uniqueTrackCounts?.smoke ?? 0} unique tracks`} icon={Wind} tone='smoke' />
      <MetricCard label='Flood detections' value={session ? number(session.detectionCounts.flood ?? 0) : '—'} detail={`${session?.uniqueTrackCounts?.flood ?? 0} unique tracks`} icon={Waves} tone='flood' />
      <MetricCard label='Active risk zones' value={frame ? String(zones.length) : '—'} detail='Across the 48-cell frame grid' icon={Focus} />
    </section>
    <section className='grid items-start gap-5 xl:grid-cols-[minmax(0,1.9fr)_minmax(290px,1fr)]'>
      <div className='flex min-w-0 flex-col gap-5'>
        <Card><CardHeader className='flex flex-row flex-wrap items-start justify-between gap-3'><div className='flex flex-col gap-1'><CardTitle>Analyzed footage</CardTitle><CardDescription>{frame ? `Frame ${frame.frameNumber} · ${time(frame.timestamp)} into ${session?.isLive ? 'stream' : 'video'}` : 'Model detections anchored to your footage'}</CardDescription></div><div className='flex gap-1.5'><Button variant='outline' size='sm' aria-pressed={showHeatmap} onClick={() => setShowHeatmap(!showHeatmap)}><Layers3 data-icon='inline-start' />{showHeatmap ? 'Hide heatmap' : 'Show heatmap'}</Button>{frame && <Button asChild variant='outline' size='icon-sm' aria-label='Download frame heatmap'><a href={frame.heatmapUrl} download={`frame-${frame.frameNumber}-heatmap.jpg`}><Download /></a></Button>}</div></CardHeader>
          <CardContent className='flex flex-col gap-4'>
            <div className='overflow-hidden rounded-xl border border-border'><VideoFeed frame={frame} filters={filters} showHeatmap={showHeatmap} selected={selectedZone} /></div>
            {frame && <div className='flex flex-col gap-3'>
              <div className='flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground'><span>{visibleDetections.length} visible detections · {frame.inferenceMs.toFixed(0)} ms inference</span><span className='flex items-center gap-1.5'>{loadingFrame ? <LoaderCircle className='size-3 animate-spin' /> : <Radio className='size-3 text-primary' />}{loadingFrame ? 'Loading frame…' : review ? 'Reviewing saved frame' : 'Following latest result'}</span></div>
              <FieldGroup><Field><FieldLabel htmlFor='frame-review' className='sr-only'>Review analyzed frames</FieldLabel><Slider id='frame-review' aria-label='Review analyzed frames' min={oldestFrame} max={Math.max(oldestFrame + 1, (session?.analyzedFrames ?? 1) - 1)} step={1} disabled={(session?.analyzedFrames ?? 0) - oldestFrame < 2} value={[Math.max(oldestFrame, frame.index)]} onValueChange={(values) => { setPlaying(false); void inspect(values[0]); }} /></Field></FieldGroup>
              <div className='flex flex-wrap items-center justify-between gap-3'><div className='flex items-center gap-1'><Button variant='ghost' size='icon-sm' disabled={frame.index <= oldestFrame || loadingFrame} aria-label='Previous' onClick={() => { setPlaying(false); void inspect(frame.index - 1); }}><ChevronLeft /></Button><Button variant='secondary' size='icon-sm' aria-label={playing ? 'Pause frame playback' : 'Play analyzed frames'} onClick={() => { if (!playing && frame.index >= (session?.analyzedFrames ?? 1) - 1) void inspect(oldestFrame); setPlaying(!playing); }}>{playing ? <Pause /> : <Play />}</Button><Button variant='ghost' size='icon-sm' disabled={frame.index >= (session?.analyzedFrames ?? 1) - 1 || loadingFrame} aria-label='Next' onClick={() => { setPlaying(false); void inspect(frame.index + 1); }}><ChevronRight /></Button><span className='ml-2 font-mono text-[10px] text-muted-foreground'>{frame.index + 1} / {number(session?.analyzedFrames ?? 0)}</span></div><Button variant='ghost' size='sm' onClick={() => { ++requestIndex.current; setReview(undefined); setLoadingFrame(false); setPlaying(false); }}><RotateCcw data-icon='inline-start' />Follow latest</Button></div>
            </div>}
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle>Frame intelligence</CardTitle><CardDescription>Inspect the evidence behind the result</CardDescription></CardHeader><CardContent><Tabs defaultValue='detections'><TabsList><TabsTrigger value='detections'>Detections ({visibleDetections.length})</TabsTrigger><TabsTrigger value='configuration'>Session details</TabsTrigger></TabsList><TabsContent value='detections'>
          {visibleDetections.length ? <div className='max-h-60 overflow-auto'><Table><TableHeader><TableRow><TableHead>Hazard</TableHead><TableHead>Confidence</TableHead><TableHead>Track ID</TableHead></TableRow></TableHeader><TableBody>{visibleDetections.map((detection) => <TableRow key={detection.id}><TableCell className='text-xs capitalize'>{detection.type}</TableCell><TableCell className='font-mono text-xs text-primary'>{Math.round(detection.confidence * 100)}%</TableCell><TableCell className='font-mono text-[10px] text-muted-foreground'>{detection.trackId ?? '—'}</TableCell></TableRow>)}</TableBody></Table></div> : <p className='py-7 text-center text-xs leading-6 text-muted-foreground'>No supported hazard above the configured confidence in this frame.<br />Earlier evidence may remain visible as it decays.</p>}
        </TabsContent><TabsContent value='configuration'><dl className='grid grid-cols-2 gap-5 py-4 text-xs'><div><dt className='text-muted-foreground'>Sampling interval</dt><dd className='mt-2'>Every {session?.frameSkip ?? '—'} frames</dd></div><div><dt className='text-muted-foreground'>Confidence threshold</dt><dd className='mt-2'>{session ? Math.round(session.confidence * 100) + '%' : '—'}</dd></div><div><dt className='text-muted-foreground'>Source frame rate</dt><dd className='mt-2'>{session?.fps?.toFixed(1) ?? '—'} FPS</dd></div><div><dt className='text-muted-foreground'>Source frames</dt><dd className='mt-2'>{number(session?.totalFrames ?? 0)}</dd></div></dl></TabsContent></Tabs></CardContent></Card>
      </div>
      <div className='flex min-w-0 flex-col gap-5'><Sidebar zones={zones} filters={filters} onToggle={toggleFilter} onSelect={setSelectedZone} selected={selectedZone} hasFrame={!!frame} />
        <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Disaster alerts</CardTitle><CardDescription>Persistent hazards in this session</CardDescription></div><Badge variant='secondary'>{session?.alerts?.filter((alert) => !alert.acknowledgedAt).length ?? 0} open</Badge></CardHeader><CardContent><AlertFeed alerts={session?.alerts ?? []} onAcknowledge={(id) => void acknowledge(id)} limit={3} /></CardContent></Card>
      </div>
    </section>
    <section className='grid gap-5 xl:grid-cols-[1.9fr_1fr]'><CumulativePanel cells={session?.cumulativeCells ?? []} filters={filters} /><Card><CardHeader><CardTitle>Keep the full picture</CardTitle><CardDescription>Export and interpret your analysis</CardDescription></CardHeader><CardContent className='flex flex-col gap-4'><p className='text-xs leading-6 text-muted-foreground'>Heatmaps summarize class-weighted model evidence. Detection counts include repeated observations; tracking counts help distinguish objects over time.</p>{latest && <Button asChild variant='outline'><a href={latest.cumulativeUrl} download='cumulative-heatmap.jpg'><Download data-icon='inline-start' />Download cumulative overlay</a></Button>}<p className='text-[10px] leading-5 text-muted-foreground'>Supported classes: fire, smoke and flood. Geographic mapping and structural damage require additional data and models. Exported overlays include all classes.</p><Button asChild variant='ghost' size='sm'><Link href='/upload'>Start another analysis<ArrowUpRight data-icon='inline-end' /></Link></Button></CardContent></Card></section>
  </main>;
}
