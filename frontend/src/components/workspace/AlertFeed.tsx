import { Bell, Check, CheckCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { cn } from '@/lib/utils';
import type { DisasterAlert } from '@/lib/state';

export function AlertFeed({ alerts, onAcknowledge, limit = 5 }: { alerts: DisasterAlert[]; onAcknowledge?: (id: string) => void; limit?: number }) {
  if (!alerts.length) return <Empty><EmptyHeader><EmptyMedia variant='icon'><CheckCheck /></EmptyMedia><EmptyTitle>No alerts to review</EmptyTitle><EmptyDescription>Persistent hazard detections will appear here.</EmptyDescription></EmptyHeader></Empty>;
  return <div className='flex flex-col gap-2.5' aria-live='polite'>{alerts.slice().reverse().slice(0, limit).map((alert) => <div key={alert.id} className={cn('flex items-start gap-3 rounded-lg border p-3', alert.acknowledgedAt ? 'border-border bg-background/15' : 'border-warning/15 bg-warning/[.025]')}>
    <span className='mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-warning/10 text-warning'><Bell className='size-3.5' /></span><div className='flex min-w-0 flex-1 flex-col gap-2'><div className='flex flex-wrap items-center justify-between gap-2'><p className='text-xs font-medium capitalize'>{alert.type} detected</p><Badge variant='outline'>{alert.severity}</Badge></div><p className='text-[11px] leading-5 text-muted-foreground'>{alert.message}</p><div className='flex flex-wrap items-center justify-between gap-2'><span className='font-mono text-[9px] text-muted-foreground'>{Math.round(alert.confidence * 100)}% confidence · Frame {alert.frameNumber}</span>{alert.acknowledgedAt ? <span className='flex items-center gap-1 text-[9px] text-success'><Check className='size-3' />Acknowledged</span> : onAcknowledge && <Button size='xs' variant='outline' onClick={() => onAcknowledge(alert.id)}>Acknowledge</Button>}</div></div>
  </div>)}</div>;
}
