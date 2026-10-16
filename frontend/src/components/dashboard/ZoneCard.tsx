import type { Zone } from '@/lib/state';
import { cn } from '@/lib/utils';

export function ZoneCard({ zone, onSelect, active }: { zone: Zone; onSelect: (id: string) => void; active: boolean }) {
  return <button onClick={() => onSelect(zone.id)} aria-pressed={active}
    className={cn('flex w-full items-center justify-between gap-3 rounded-lg border p-3 text-left transition-colors', active ? 'border-primary/40 bg-primary/5' : 'border-border bg-background/20 hover:bg-accent/40')}>
    <span className='flex min-w-0 items-center gap-3'><span className='flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary/70 font-mono text-[10px] text-muted-foreground'>{zone.row + 1}.{zone.col + 1}</span><span className='min-w-0'><span className='block text-xs font-medium'>Row {zone.row + 1}, column {zone.col + 1}</span><span className='block truncate text-[10px] capitalize text-muted-foreground'>{zone.type}</span></span></span>
    <span className='flex flex-col items-end gap-1'><span className='font-mono text-xs text-primary'>{Math.round(zone.severity * 100)}%</span><span className='text-[9px] text-muted-foreground'>risk index</span></span>
  </button>;
}
