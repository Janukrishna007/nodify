'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { cellRisk, useUIStore, type DisasterType, type FrameData, type Session, type Zone } from '@/lib/state';
import { cancelAnalysis, fetchFrame } from '@/services/api';
import { connectAnalysis } from '@/services/socket';
import { VideoFeed } from '@/components/video/VideoFeed';
import { Sidebar } from './Sidebar';
import { CumulativePanel } from './CumulativePanel';

export function AnalysisDashboard({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<Session>();
  const [latest, setLatest] = useState<FrameData>();
  const [review, setReview] = useState<FrameData>();
  const [error, setError] = useState('');
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [selectedZone, setSelectedZone] = useState<string>();
  const [loadingFrame, setLoadingFrame] = useState(false);
  const [stopping, setStopping] = useState(false);
  const requestIndex = useRef(0);
  const { filters, toggleFilter } = useUIStore();
  const frame = review ?? latest;
  const running = !!session && ['queued', 'loading', 'processing'].includes(session.status);

  useEffect(() => connectAnalysis(sessionId, (updated, result) => {
    setSession(updated); if (result) setLatest(result); setError('');
  }, setError), [sessionId]);

  const zones = useMemo(() => (frame?.cells ?? []).map((cell): Zone => {
    const severity = cellRisk(cell, filters);
    const classes = (Object.keys(filters) as DisasterType[]).filter((key) => filters[key] && cell.byClass[key].score > 0.01);
    return { ...cell, id: `${cell.row}-${cell.col}`, type: classes.join(', '), severity };
  }).filter((zone) => zone.severity >= 0.01).sort((a, b) => b.severity - a.severity), [frame, filters]);

  const inspect = async (index: number) => {
    const token = ++requestIndex.current;
    setLoadingFrame(true);
    try {
      const result = await fetchFrame(sessionId, index);
      if (token === requestIndex.current) { setReview(result); setError(''); }
    } catch (failure) {
      if (token === requestIndex.current) setError(failure instanceof Error ? failure.message : 'Could not load frame.');
    } finally {
      if (token === requestIndex.current) setLoadingFrame(false);
    }
  };

  const stop = async () => {
    setStopping(true);
    try { await cancelAnalysis(sessionId); } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not stop analysis.'); setStopping(false);
    }
  };

  return <main className='mx-auto w-full max-w-[1500px] space-y-6 px-6 py-8'>
    <header className='flex flex-wrap items-start justify-between gap-4'>
      <div>
        <p className='text-xs uppercase tracking-[0.3em] text-white/50'>DisasterVision · Video analysis</p>
        <h1 className='mt-2 break-all text-2xl font-semibold'>{session?.filename ?? 'Loading analysis…'}</h1>
        <p className='mt-2 text-sm text-white/60' role='status'>
          {session?.status === 'loading' ? 'Loading detection models…' : session?.status ?? 'Connecting…'}
          {session && ` · ${session.analyzedFrames} analyzed frames${session.expectedSamples ? ` / ${session.expectedSamples}` : ''} · ${session.progress.toFixed(1)}%`}
        </p>
      </div>
      <div className='flex flex-wrap gap-3 text-sm'>
        <Link className='rounded-xl border border-white/20 px-4 py-2' href='/upload'>Upload / history</Link>
        {running && <button onClick={stop} disabled={stopping} className='rounded-xl border border-red-300/40 px-4 py-2 text-red-200 disabled:opacity-40'>{stopping ? 'Stopping…' : 'Stop analysis'}</button>}
        {!!session?.analyzedFrames && <a href={`/api/sessions/${sessionId}/report`} download={`${session.filename}-analysis.json`} className='rounded-xl bg-white px-4 py-2 text-black'>Download report</a>}
      </div>
    </header>
    {session && <progress value={session.progress} max={100} aria-label='Analysis progress' className='h-2 w-full' />}
    {(error || session?.error) && <p className='rounded-xl border border-red-300/30 bg-red-400/10 p-4 text-sm text-red-200' role='alert'>{error || session?.error}</p>}
    <section className='grid gap-3 sm:grid-cols-4'>
      {(['fire', 'smoke', 'flood'] as const).map((key) => <div key={key} className='rounded-xl border border-white/10 bg-white/5 p-4'>
        <p className='text-xs capitalize text-white/50'>{key} detections</p><p className='mt-1 text-2xl'>{session?.detectionCounts[key] ?? 0}</p>
      </div>)}
      <div className='rounded-xl border border-white/10 bg-white/5 p-4'><p className='text-xs text-white/50'>Frame settings</p><p className='mt-2 text-sm'>Every {session?.frameSkip ?? '—'} frames · confidence {session ? Math.round(session.confidence * 100) + '%' : '—'}</p></div>
    </section>
    <p className='text-xs text-white/50'>Counts are model detections across sampled frames, not unique objects. Risk is a weighted confidence index, not a measured damage percentage.</p>
    <section className='grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(280px,1fr)]'>
      <div className='space-y-4'>
        <div className='flex flex-wrap items-center justify-between gap-3 text-sm'>
          <h2 className='font-semibold'>Analyzed frame {frame ? frame.frameNumber : '—'} {frame && `· ${frame.timestamp.toFixed(2)}s`}</h2>
          <button aria-pressed={showHeatmap} onClick={() => setShowHeatmap(!showHeatmap)} className='rounded-lg border border-white/20 px-3 py-1'>{showHeatmap ? 'Hide heatmap' : 'Show heatmap'}</button>
        </div>
        <VideoFeed frame={frame} filters={filters} showHeatmap={showHeatmap} selected={selectedZone} />
        {frame && <div className='space-y-3 rounded-xl border border-white/10 p-4'>
          <div className='flex flex-wrap items-center justify-between gap-3 text-xs text-white/60'>
            <span>{frame.detections.filter((detection) => filters[detection.type]).length} visible detections · {frame.inferenceMs.toFixed(0)} ms inference</span>
            <span>{loadingFrame ? 'Loading frame…' : review ? 'Reviewing saved frame' : 'Following latest result'}</span>
          </div>
          <label className='block text-xs text-white/50'>Review analyzed frames
            <input type='range' min={0} max={Math.max(0, (session?.analyzedFrames ?? 1) - 1)} value={frame.index}
              onChange={(event) => void inspect(Number(event.target.value))} className='mt-2 w-full' />
          </label>
          <div className='flex flex-wrap gap-2 text-xs'>
            <button disabled={!frame.index || loadingFrame} onClick={() => void inspect(frame.index - 1)} className='rounded-lg border border-white/20 px-3 py-2 disabled:opacity-30'>Previous</button>
            <button disabled={frame.index >= (session?.analyzedFrames ?? 1) - 1 || loadingFrame} onClick={() => void inspect(frame.index + 1)} className='rounded-lg border border-white/20 px-3 py-2 disabled:opacity-30'>Next</button>
            <button onClick={() => { ++requestIndex.current; setReview(undefined); setLoadingFrame(false); }} className='rounded-lg border border-white/20 px-3 py-2'>Follow latest</button>
            <a href={frame.heatmapUrl} download={`frame-${frame.frameNumber}-heatmap.jpg`} className='rounded-lg border border-white/20 px-3 py-2'>Download frame heatmap (all classes)</a>
          </div>
          {!frame.detections.length && <p className='text-sm text-white/60'>No supported disaster detected above the configured confidence in this frame. Earlier evidence may still be visible as it decays.</p>}
          {!!frame.detections.length && <div className='flex flex-wrap gap-2'>
            {frame.detections.filter((detection) => filters[detection.type]).map((detection) => <span key={detection.id} className='rounded bg-white/5 px-2 py-1 text-xs text-white/60'>{detection.type} · {Math.round(detection.confidence * 100)}% confidence</span>)}
          </div>}
        </div>}
      </div>
      <Sidebar zones={zones} filters={filters} onToggle={toggleFilter} onSelect={setSelectedZone} selected={selectedZone} hasFrame={!!frame} />
    </section>
    <CumulativePanel cells={session?.cumulativeCells ?? []} filters={filters} />
    {latest && <a href={latest.cumulativeUrl} download='cumulative-heatmap.jpg' className='inline-block text-sm text-white/70 underline'>Download cumulative overlay (all classes)</a>}
    <p className='text-xs leading-5 text-white/40'>Supported models: fire, smoke, flood. Ordinary water predictions are excluded. Structural damage and collapse detection need additional trained weights.</p>
  </main>;
}
