import type { Zone } from '@/lib/state';

export function ZoneCard({ zone, onSelect, active }: { zone: Zone; onSelect: (id: string) => void; active: boolean }) {
  return <button onClick={() => onSelect(zone.id)} className={`flex w-full items-center justify-between rounded-xl border p-3 text-left ${active ? 'border-white/60 bg-white/10' : 'border-white/10 bg-white/5'}`}>
    <span><span className='block text-xs text-white/50'>Row {zone.row + 1}, column {zone.col + 1}</span><span className='text-sm capitalize'>{zone.type}</span></span>
    <span className='text-sm'>{Math.round(zone.severity * 100)}% risk</span>
  </button>;
}
