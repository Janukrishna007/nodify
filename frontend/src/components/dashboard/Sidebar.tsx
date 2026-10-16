import type { DisasterType, Filters as FilterState, Zone } from '@/lib/state';
import { Focus, ScanLine } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Empty, EmptyHeader, EmptyMedia, EmptyDescription } from '@/components/ui/empty';
import { ZoneCard } from './ZoneCard';
import { Filters } from './Filters';

export function Sidebar({ zones, filters, onToggle, onSelect, selected, hasFrame }: {
  zones: Zone[]; filters: FilterState; onToggle: (key: DisasterType) => void;
  onSelect: (id: string) => void; selected?: string; hasFrame: boolean;
}) {
  return <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Risk zones</CardTitle><CardDescription>Ranked by current evidence</CardDescription></div><Badge variant='secondary'>{zones.length} active</Badge></CardHeader><CardContent className='flex flex-col gap-4'>
    <Filters filters={filters} onToggle={onToggle} />
    <div className='flex max-h-[260px] flex-col gap-2 overflow-y-auto pr-1'>
      {!zones.length && <Empty><EmptyHeader><EmptyMedia variant='icon'><ScanLine /></EmptyMedia><EmptyDescription>{hasFrame ? 'No risk above 1% for the selected classes.' : 'Risk zones appear as frames are analyzed.'}</EmptyDescription></EmptyHeader></Empty>}
      {zones.map((zone) => <ZoneCard key={zone.id} zone={zone} onSelect={onSelect} active={selected === zone.id} />)}
    </div>
    <p className='flex items-center gap-1.5 text-[9px] text-muted-foreground'><Focus className='size-3' />Select a zone to locate it on the frame.</p>
  </CardContent></Card>;
}
