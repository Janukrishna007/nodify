import type { LucideIcon } from 'lucide-react';
import { ArrowUpRight, FileVideo, Layers3, Radio } from 'lucide-react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table';
import { date, detectionTotal, number, sessionHref, statusLabel, title } from '@/lib/presentation';
import type { Session } from '@/lib/state';

export function PageHeading({ eyebrow, title: heading, description, actions }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode }) {
  return <div className='flex flex-wrap items-end justify-between gap-5'><div className='flex flex-col gap-2'><p className='eyebrow text-primary'>{eyebrow}</p><h1 className='text-2xl font-semibold tracking-tight md:text-[29px]'>{heading}</h1><p className='max-w-2xl text-xs leading-6 text-muted-foreground md:text-[13px]'>{description}</p></div>{actions && <div className='flex items-center gap-2'>{actions}</div>}</div>;
}

export function StatusBadge({ status }: { status: Session['status'] }) {
  return <Badge variant='outline' data-status={status}><span className='status-dot' />{statusLabel(status)}</Badge>;
}

export function MetricCard({ label, value, detail, icon: Icon, tone = 'primary' }: { label: string; value: string; detail: string; icon: LucideIcon; tone?: 'primary' | 'fire' | 'smoke' | 'flood' | 'warning' }) {
  return <Card><CardHeader className='flex flex-row items-center justify-between gap-2'><CardDescription>{label}</CardDescription><Icon className={`size-4 ${tone === 'fire' ? 'text-fire' : tone === 'smoke' ? 'text-smoke' : tone === 'flood' ? 'text-flood' : tone === 'warning' ? 'text-warning' : 'text-primary'}`} /></CardHeader><CardContent className='flex flex-col gap-2'><p className='font-mono text-[30px] font-medium leading-none tracking-tight'>{value}</p><p className='text-[11px] text-muted-foreground'>{detail}</p></CardContent></Card>;
}

export function SessionTable({ sessions, caption = 'Recent analyses', actions }: { sessions: Session[]; caption?: string; actions?: React.ReactNode }) {
  return <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>{caption}</CardTitle><CardDescription>Saved footage and analysis results</CardDescription></div>{actions}</CardHeader><CardContent>
    {!sessions.length ? <Empty><EmptyHeader><EmptyMedia variant='icon'><Layers3 /></EmptyMedia><EmptyTitle>No analyses yet</EmptyTitle><EmptyDescription>Upload your first video to start building your intelligence workspace.</EmptyDescription></EmptyHeader><Button asChild size='sm'><Link href='/upload'>Upload footage</Link></Button></Empty> : <Table><TableHeader><TableRow><TableHead>Video source</TableHead><TableHead>Status</TableHead><TableHead className='hidden md:table-cell'>Frames</TableHead><TableHead className='hidden xl:table-cell'>Detections</TableHead><TableHead className='hidden sm:table-cell'>Created</TableHead><TableHead className='text-right'>Review</TableHead></TableRow></TableHeader><TableBody>{sessions.map((session) => <TableRow key={session.id}>
      <TableCell><Link href={sessionHref(session.id)} className='flex max-w-[150px] items-center gap-3 sm:max-w-[230px]'><span className='flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-secondary/40 text-muted-foreground'>{session.isLive ? <Radio className='size-4' /> : <FileVideo className='size-4' />}</span><span className='min-w-0'><span className='block truncate text-xs font-medium capitalize'>{session.isLive ? session.filename : title(session.filename)}</span><span className='block text-[10px] text-muted-foreground'>{session.isLive ? 'RTSP' : session.filename.split('.').pop()?.toUpperCase()} · Every {session.frameSkip} frames</span></span></Link></TableCell>
      <TableCell><StatusBadge status={session.status} /></TableCell><TableCell className='hidden font-mono text-xs text-muted-foreground md:table-cell'>{number(session.analyzedFrames)}</TableCell><TableCell className='hidden font-mono text-xs text-muted-foreground xl:table-cell'>{number(detectionTotal(session))}</TableCell><TableCell className='hidden text-[11px] text-muted-foreground sm:table-cell'>{date(session.createdAt)}</TableCell><TableCell className='text-right'><Button asChild variant='ghost' size='icon' aria-label={`Review ${session.filename}`}><Link href={sessionHref(session.id)}><ArrowUpRight /></Link></Button></TableCell>
    </TableRow>)}</TableBody></Table>}
  </CardContent></Card>;
}
