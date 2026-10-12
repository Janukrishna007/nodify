import type { DisasterType, Filters as FilterState } from '@/lib/state';

export function Filters({ filters, onToggle }: { filters: FilterState; onToggle: (key: DisasterType) => void }) {
  return <div className='flex flex-wrap gap-2'>
    {(['fire', 'smoke', 'flood'] as const).map((key) => <button key={key} onClick={() => onToggle(key)} aria-pressed={filters[key]}
      className={filters[key] ? 'rounded-full border border-white/25 bg-white/15 px-3 py-1 text-xs capitalize' : 'rounded-full border border-white/10 px-3 py-1 text-xs capitalize text-white/40'}>
      {key}
    </button>)}
  </div>;
}
