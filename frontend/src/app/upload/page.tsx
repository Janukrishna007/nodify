'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { checkBackend, fetchSessions, startAnalysis } from '@/services/api';
import type { Session } from '@/lib/state';

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [frameSkip, setFrameSkip] = useState(3);
  const [confidence, setConfidence] = useState(0.45);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [backend, setBackend] = useState('Checking analysis server…');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const [health, history] = await Promise.all([checkBackend(), fetchSessions()]);
        if (mounted) {
          setBackend('Analysis server connected'); setSessions(history); setActiveSession(health.activeSession);
        }
      } catch {
        if (mounted) setBackend('Analysis server unavailable — start the backend on port 8000.');
      }
    };
    void refresh();
    const interval = setInterval(refresh, 4000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  const selectFile = (selected?: File) => {
    if (!selected) return;
    if (!/\.(mp4|mov|avi|webm|mkv|m4v)$/i.test(selected.name)) { setError('Choose an MP4, MOV, AVI, WebM, MKV or M4V video.'); return; }
    if (selected.size > 500 * 1024 * 1024) { setError('Maximum upload size is 500 MB.'); return; }
    setFile(selected); setError('');
  };

  const start = async () => {
    if (!file || busy) return;
    setBusy(true); setError(''); setProgress(0);
    try {
      const session = await startAnalysis(file, frameSkip, confidence, setProgress);
      router.push(`/dashboard?session=${session.id}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Upload failed.'); setBusy(false);
    }
  };

  return (
    <main className='mx-auto w-full max-w-6xl space-y-8 px-6 py-10'>
      <header>
        <p className='text-xs uppercase tracking-[0.3em] text-white/50'>DisasterVision</p>
        <h1 className='mt-2 text-3xl font-semibold'>Analyze disaster footage</h1>
        <p className='mt-2 text-white/60'>Upload a video to detect fire, smoke and flood, inspect analyzed frames, and generate risk heatmaps.</p>
        <p className='mt-3 text-sm text-white/60' role='status'>{backend}</p>
      </header>
      {activeSession && <div className='rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm'>An analysis is running. <Link className='underline' href={`/dashboard?session=${activeSession}`}>Open it to view progress or stop it.</Link></div>}
      <section className='glass grid gap-8 rounded-3xl p-8 md:grid-cols-[2fr_1fr]'>
        <div onDrop={(event) => { event.preventDefault(); if (!busy) selectFile(event.dataTransfer.files[0]); }} onDragOver={(event) => event.preventDefault()}
          className='flex min-h-72 flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-white/20 bg-white/5 p-8 text-center'>
          <h2 className='text-xl'>Drop your video here</h2>
          <label className='cursor-pointer rounded-xl bg-white px-5 py-3 text-sm font-semibold text-black'>
            Choose video
            <input type='file' accept='.mp4,.mov,.avi,.webm,.mkv,.m4v,video/*' disabled={busy} className='hidden' onChange={(event) => selectFile(event.target.files?.[0])} />
          </label>
          <p className='text-sm text-white/50'>MP4, MOV, AVI, WebM, MKV, M4V · up to 500 MB</p>
          {file && <p className='break-all text-sm'>{file.name} <span className='text-white/50'>({(file.size / 1024 / 1024).toFixed(1)} MB)</span></p>}
        </div>
        <div className='space-y-5'>
          <h2 className='font-semibold'>Analysis settings</h2>
          <label className='block text-sm text-white/70'>Analyze every Nth frame
            <input type='number' min={1} max={60} value={frameSkip} disabled={busy} onChange={(event) => setFrameSkip(Number(event.target.value))} className='mt-2 w-full rounded-xl border border-white/15 bg-black/40 p-3 text-white' />
          </label>
          <label className='block text-sm text-white/70'>Minimum model confidence: {Math.round(confidence * 100)}%
            <input type='range' min={0.1} max={0.95} step={0.05} value={confidence} disabled={busy} onChange={(event) => setConfidence(Number(event.target.value))} className='mt-3 w-full' />
          </label>
          <p className='text-xs leading-5 text-white/50'>Every {frameSkip}th frame is saved and analyzed by the bundled YOLO models. Smaller intervals take longer. Structural damage models are not included.</p>
          <button onClick={start} disabled={!file || busy || !!activeSession || !Number.isInteger(frameSkip) || frameSkip < 1 || frameSkip > 60}
            className='w-full rounded-xl bg-white p-3 font-semibold text-black disabled:cursor-not-allowed disabled:opacity-40'>
            {busy ? progress < 100 ? `Uploading ${progress}%…` : 'Preparing analysis…' : 'Start analysis'}
          </button>
          {busy && <progress className='w-full' value={progress} max={100} aria-label='Upload progress' />}
          {error && <p role='alert' className='text-sm text-red-300'>{error}</p>}
        </div>
      </section>
      <section className='space-y-3'>
        <h2 className='text-lg font-semibold'>Previous analyses</h2>
        {!sessions.length && <p className='text-sm text-white/50'>Your analyzed videos will appear here.</p>}
        {sessions.map((session) => <Link key={session.id} href={`/dashboard?session=${session.id}`} className='flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 p-4 hover:bg-white/10'>
          <span className='min-w-0 break-all'>{session.filename}</span>
          <span className='text-sm text-white/60'>{session.status} · {session.analyzedFrames} analyzed frames · {new Date(session.createdAt).toLocaleString()}</span>
        </Link>)}
      </section>
    </main>
  );
}
