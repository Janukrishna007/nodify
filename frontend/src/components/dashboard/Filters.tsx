import type { DisasterType, Filters as FilterState } from '@/lib/state';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

export function Filters({ filters, onToggle }: { filters: FilterState; onToggle: (key: DisasterType) => void }) {
  return <ToggleGroup type='multiple' variant='outline' size='sm' aria-label='Filter disaster classes'
    value={(Object.keys(filters) as DisasterType[]).filter((key) => filters[key])}
    onValueChange={(values) => { for (const key of ['fire', 'smoke', 'flood'] as const) if (values.includes(key) !== filters[key]) onToggle(key); }}>
    {(['fire', 'smoke', 'flood'] as const).map((key) => <ToggleGroupItem key={key} value={key} aria-label={key}><span className='capitalize'>{key}</span></ToggleGroupItem>)}
  </ToggleGroup>;
}
