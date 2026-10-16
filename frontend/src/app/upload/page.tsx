'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, ArrowUpRight, Check, CircleAlert, FileVideo, Focus, Layers3, LoaderCircle, LockKeyhole, Radio, ScanLine, Settings2, ShieldCheck, Square, UploadCloud, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useWorkspace } from '@/components/workspace/WorkspaceProvider';
import { PageHeading, SessionTable } from '@/components/workspace/DashboardPrimitives';
import { cancelAnalysis, checkBackend, startAnalysis, startStream } from '@/services/api';
import { sessionHref } from '@/lib/presentation';

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>();
  const [frameSkip, setFrameSkip] = useState(3);
  const [confidence, setConfidence] = useState(0.45);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const [source, setSource] = useState('upload');
  const [streamUrl, setStreamUrl] = useState('');
  const [streamName, setStreamName] = useState('Drone live stream');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [stopping, setStopping] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const { sessions, activeSession, connected, refresh } = useWorkspace();
  const router = useRouter();
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const selectFile = (selected?: File) => {
    setDragging(false);
    if (!selected || busy) return;
    if (!/\.(mp4|mov|avi|webm|mkv|m4v)$/i.test(selected.name)) { setError('Choose an MP4, MOV, AVI, WebM, MKV or M4V video.'); return; }
    if (selected.size > 500 * 1024 * 1024) { setError('Maximum upload size is 500 MB.'); return; }
    setFile(selected); setPreview(URL.createObjectURL(selected)); setError('');
  };
  const validInterval = Number.isInteger(frameSkip) && frameSkip >= 1 && frameSkip <= 60;
  const live = source === 'live';
  const validStream = /^rtsps?:\/\/[^\s/]+/i.test(streamUrl.trim());
  const stopCurrent = async () => {
    if (!activeSession || stopping) return;
    setStopping(true); setError('');
    try {
      await cancelAnalysis(activeSession);
      for (let attempt = 0; attempt < 60; attempt++) {
        if (!(await checkBackend()).activeSession) { await refresh(); return; }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error('The analysis is still stopping. Check its dashboard before starting another.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not stop the current analysis.'); }
    finally { setStopping(false); }
  };
  const start = async () => {
    if (busy || !validInterval || (live ? !validStream : !file)) return;
    setBusy(true); setError(''); setProgress(0);
    try {
      const session = live
        ? await startStream({ url: streamUrl.trim(), name: streamName.trim() || 'Drone live stream', username, password, frame_skip: frameSkip, confidence })
        : await startAnalysis(file!, frameSkip, confidence, setProgress);
      setPassword(''); setStreamUrl('');
      void refresh();
      router.push(sessionHref(session.id));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Upload failed.'); setBusy(false);
    }
  };

  return <main className='fade-in flex flex-col gap-6'>
    <PageHeading eyebrow='New analysis' title='A new perspective on disaster response.' description='Start fresh with a new video or connect your drone’s live RTSP feed.' actions={<Button asChild variant='outline'><Link href='/sessions'>Session history<ArrowUpRight data-icon='inline-end' /></Link></Button>} />
    <div className='flex flex-wrap items-center gap-5 rounded-xl border border-border bg-card/30 px-5 py-3'>
      {[{ label: 'Upload footage', icon: UploadCloud }, { label: 'Detect & analyze', icon: Focus }, { label: 'Explore intelligence', icon: Layers3 }].map((step, index) => <div key={step.label} className='flex items-center gap-2.5 text-xs'><span className={index === 0 ? 'flex size-6 items-center justify-center rounded-full bg-primary/15 text-[10px] text-primary' : 'flex size-6 items-center justify-center rounded-full bg-secondary text-[10px] text-muted-foreground'}>{index + 1}</span><span className={index === 0 ? 'text-foreground' : 'text-muted-foreground'}>{step.label}</span>{index !== 2 && <ArrowRight className='ml-3 hidden size-3 text-muted-foreground/40 sm:block' />}</div>)}
      <span className='ml-auto hidden items-center gap-1.5 text-[10px] text-muted-foreground lg:flex'><LockKeyhole className='size-3' />Your footage stays local</span>
    </div>
    {activeSession && <Alert><LoaderCircle /><AlertTitle>An analysis is already running</AlertTitle><AlertDescription><p>Your current analysis continues in the background. Stop it to start the next video or stream.</p><div className='mt-2 flex flex-wrap gap-2'><Button asChild variant='outline' size='sm'><Link href={sessionHref(activeSession)}>Open running analysis</Link></Button><Button variant='destructive' size='sm' disabled={stopping} onClick={() => void stopCurrent()}><Square data-icon='inline-start' />{stopping ? 'Stopping…' : 'Stop current analysis'}</Button></div></AlertDescription></Alert>}
    <section className='grid gap-5 xl:grid-cols-[1.75fr_1fr]'>
      <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1.5'><CardTitle>Source footage</CardTitle><CardDescription>Choose a new recording or a live drone feed</CardDescription></div><Badge variant='outline'>{live ? <Radio /> : <FileVideo />}{live ? 'RTSP input' : 'Video input'}</Badge></CardHeader><CardContent>
        <Tabs value={source} onValueChange={(value) => { if (!busy) { setSource(value); setError(''); } }}>
          <TabsList className='mb-5'><TabsTrigger value='upload' disabled={busy}><UploadCloud />Upload video</TabsTrigger><TabsTrigger value='live' disabled={busy}><Radio />Drone live stream</TabsTrigger></TabsList>
          <TabsContent value='upload'>
        <div data-dragging={dragging} onDrop={(event) => { event.preventDefault(); selectFile(event.dataTransfer.files[0]); }} onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} className='dropzone flex min-h-[340px] flex-col items-center justify-center gap-5 rounded-xl border border-dashed border-primary/20 p-7 text-center'>
          {preview ? <div className='relative flex w-full flex-col gap-4'><video src={preview} controls preload='metadata' className='max-h-52 w-full rounded-lg bg-background' aria-label='Selected video preview' /><div className='flex items-center gap-3 rounded-lg border border-border bg-background/40 p-3 text-left'><FileVideo className='size-5 shrink-0 text-primary' /><span className='min-w-0 flex-1'><span className='block truncate text-xs font-medium'>{file?.name}</span><span className='text-[10px] text-muted-foreground'>{file && (file.size / 1024 / 1024).toFixed(1)} MB · Ready for analysis</span></span><Button variant='ghost' size='icon' disabled={busy} aria-label='Remove selected video' onClick={() => { setFile(null); setPreview(undefined); if (fileInput.current) fileInput.current.value = ''; }}><X /></Button></div></div> : <>
            <div className='relative flex size-20 items-center justify-center'><span className='absolute inset-0 rounded-2xl border border-primary/10 bg-primary/[.025] rotate-12' /><span className='relative flex size-16 items-center justify-center rounded-2xl border border-primary/20 bg-primary/5 text-primary'><UploadCloud className='size-7' strokeWidth={1.5} /></span></div>
            <div className='flex flex-col gap-2'><h2 className='text-lg font-medium tracking-tight'>Drop your video here</h2><p className='text-xs text-muted-foreground'>or choose a file from your computer</p></div>
            <Button asChild variant='outline'><label htmlFor='video-upload'>Choose video<ArrowUpRight data-icon='inline-end' /></label></Button>
            <div className='flex flex-col gap-1.5'><p className='text-[10px] tracking-wider text-muted-foreground'>MP4 · MOV · AVI · WEBM · MKV · M4V</p><p className='text-[10px] text-muted-foreground/60'>Up to 500 MB per video</p></div>
          </>}
          <input ref={fileInput} id='video-upload' type='file' accept='.mp4,.mov,.avi,.webm,.mkv,.m4v,video/*' disabled={busy} className='sr-only' onChange={(event) => selectFile(event.target.files?.[0])} />
        </div>
          </TabsContent>
          <TabsContent value='live'><FieldGroup>
            <Field><FieldLabel htmlFor='stream-name'>Stream name</FieldLabel><Input id='stream-name' maxLength={80} value={streamName} disabled={busy} onChange={(event) => setStreamName(event.target.value)} placeholder='North sector drone' /></Field>
            <Field><FieldLabel htmlFor='rtsp-url'>RTSP stream address</FieldLabel><Input id='rtsp-url' type='text' inputMode='url' autoComplete='off' spellCheck={false} value={streamUrl} disabled={busy} onChange={(event) => setStreamUrl(event.target.value)} placeholder='rtsp://192.168.1.10:554/live' /><FieldDescription>Use the address from your drone, controller or video receiver. This computer must be able to reach that device.</FieldDescription></Field>
            <div className='grid gap-4 sm:grid-cols-2'><Field><FieldLabel htmlFor='stream-user'>Username (optional)</FieldLabel><Input id='stream-user' autoComplete='off' value={username} disabled={busy} onChange={(event) => setUsername(event.target.value)} /></Field><Field><FieldLabel htmlFor='stream-password'>Password (optional)</FieldLabel><Input id='stream-password' type='password' autoComplete='new-password' value={password} disabled={busy} onChange={(event) => setPassword(event.target.value)} /></Field></div>
            <Alert><Radio /><AlertTitle>Ready for drone footage</AlertTitle><AlertDescription>Enable RTSP output on your receiver and connect to its network. We use TCP, retry dropped connections up to three times, and analyze recent frames as they arrive. The dashboard keeps the latest 300 analyzed frames for review; it does not record the full flight.</AlertDescription></Alert>
            <p className='text-[11px] leading-5 text-muted-foreground'>Credentials stay in memory for this connection. Refresh opens a fresh upload form; a running stream continues until you stop it. Review past results in Session history.</p>
          </FieldGroup></TabsContent>
        </Tabs>
      </CardContent><CardFooter className='gap-2 text-[10px] text-muted-foreground'><ShieldCheck className='size-3.5 text-primary' />Secure local processing. No cloud upload required.</CardFooter></Card>
      <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1.5'><CardTitle>Analysis configuration</CardTitle><CardDescription>Fine-tune how your footage is processed</CardDescription></div><Settings2 className='size-4 text-muted-foreground' /></CardHeader><CardContent className='flex flex-col gap-6'>
        <FieldGroup>
          <Field data-invalid={!validInterval}><FieldLabel htmlFor='frame-interval'>Frame sampling interval</FieldLabel><Input id='frame-interval' type='number' min={1} max={60} value={frameSkip} disabled={busy} aria-invalid={!validInterval} onChange={(event) => setFrameSkip(Number(event.target.value))} /><FieldDescription>Analyze every Nth frame. Lower values capture more detail and take longer.</FieldDescription></Field>
          <Field><div className='flex items-center justify-between'><FieldLabel htmlFor='confidence-threshold'>Confidence threshold</FieldLabel><span className='font-mono text-xs text-primary'>{Math.round(confidence * 100)}%</span></div><Slider id='confidence-threshold' aria-label='Minimum model confidence' value={[confidence]} min={0.1} max={0.95} step={0.05} disabled={busy} onValueChange={(values) => setConfidence(values[0])} /><div className='flex justify-between text-[10px] text-muted-foreground'><span>More sensitive</span><span>More selective</span></div></Field>
        </FieldGroup>
        <Separator />
        <div className='flex flex-col gap-3'><p className='eyebrow'>Detection capabilities</p><div className='flex flex-wrap gap-2'><Badge variant='secondary'>Fire</Badge><Badge variant='secondary'>Smoke</Badge><Badge variant='secondary'>Flood</Badge></div><p className='text-[11px] leading-5 text-muted-foreground'>Includes object tracking, spatial risk scoring and cumulative heatmaps. Structural damage models are not included.</p></div>
        <Button onClick={() => void start()} disabled={(live ? !validStream : !file) || busy || !!activeSession || stopping || !validInterval || !connected} className='w-full'>{busy ? <><LoaderCircle data-icon='inline-start' className='animate-spin' />{live ? 'Starting stream…' : progress < 100 ? `Uploading ${progress}%` : 'Preparing analysis…'}</> : <><ScanLine data-icon='inline-start' />{live ? 'Connect & analyze' : 'Start analysis'}<ArrowRight data-icon='inline-end' /></>}</Button>
        {busy && !live && <Progress value={progress} aria-label='Upload progress' />}
        {error && <Alert variant='destructive'><CircleAlert /><AlertTitle>Analysis could not be started</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
        <span className={connected ? 'flex items-center justify-center gap-2 text-[10px] text-success' : 'flex items-center justify-center gap-2 text-[10px] text-muted-foreground'} role='status'><span className='status-dot' />{connected ? 'Analysis server connected' : 'Waiting for analysis server'}</span>
      </CardContent></Card>
    </section>
    <div className='grid gap-4 md:grid-cols-3'>{[{ icon: Focus, title: 'See the hazards', text: 'Model detections and confidence, anchored to the actual video frame.' }, { icon: Layers3, title: 'Understand the impact', text: 'Explore current and cumulative evidence across a spatial risk grid.' }, { icon: Check, title: 'Keep the full picture', text: 'Revisit saved frames, acknowledge alerts and export your results.' }].map((item) => <div key={item.title} className='flex items-start gap-3 rounded-xl border border-border bg-card/20 p-4'><span className='flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/5 text-primary'><item.icon className='size-4' /></span><div className='flex flex-col gap-1.5'><h3 className='text-xs font-medium'>{item.title}</h3><p className='text-[11px] leading-5 text-muted-foreground'>{item.text}</p></div></div>)}</div>
    <SessionTable sessions={sessions.slice(0, 4)} caption='Previous analyses' actions={<Button asChild variant='ghost' size='sm'><Link href='/sessions'>All sessions<ArrowRight data-icon='inline-end' /></Link></Button>} />
  </main>;
}
