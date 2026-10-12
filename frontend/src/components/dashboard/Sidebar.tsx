import type { DisasterType, Filters as FilterState, Zone } from '@/lib/state';
import { ZoneCard } from './ZoneCard';
import { Filters } from './Filters';

export function Sidebar({ zones, filters, onToggle, onSelect, selected, hasFrame }: {
  zones: Zone[]; filters: FilterState; onToggle: (key: DisasterType) => void;
  onSelect: (id: string) => void; selected?: string; hasFrame: boolean;
}) {
  return <aside className='glass flex flex-col gap-4 rounded-2xl p-5'>
    <h2 className='text-lg font-semibold'>Ranked risk zones</h2>
    <Filters filters={filters} onToggle={onToggle} />
    <p className='text-xs text-white/50'>6 rows × 8 columns · model-weighted risk</p>
    <div className='max-h-[440px] space-y-2 overflow-y-auto'>
      {!zones.length && <p className='text-sm text-white/60'>{hasFrame ? 'No risk above 1% for the selected classes in this frame.' : 'Waiting for analyzed frames…'}</p>}
      {zones.map((zone) => <ZoneCard key={zone.id} zone={zone} onSelect={onSelect} active={selected === zone.id} />)}
    </div>
  </aside>;
}
