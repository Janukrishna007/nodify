import { Grid2X2, Info } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cellRisk, type Cell, type Filters } from '@/lib/state';

export function CumulativePanel({ cells, filters }: { cells: Cell[]; filters: Filters }) {
  return <Card><CardHeader className='flex flex-row items-start justify-between'><div className='flex flex-col gap-1'><CardTitle>Cumulative heatmap</CardTitle><CardDescription>Mean detection evidence across analyzed frames</CardDescription></div><Badge variant='outline'><Grid2X2 />8 × 6 grid</Badge></CardHeader><CardContent className='flex flex-col gap-4'>
    <div className='grid grid-cols-8 gap-1.5' aria-label='Cumulative risk grid'>
      {Array.from({ length: 48 }, (_, index) => {
        const cell = cells[index];
        const risk = cell ? cellRisk(cell, filters, true) : 0;
        const color = risk > 0.65 ? 'var(--fire)' : risk > 0.35 ? 'var(--warning)' : risk > 0.15 ? 'var(--primary)' : 'var(--flood)';
        return <div key={index} className='heat-cell' title={`Row ${Math.floor(index / 8) + 1}, column ${index % 8 + 1}: ${Math.round(risk * 100)}% risk index`}
          style={{ background: risk > 0 ? `color-mix(in srgb, ${color} ${Math.round(risk * 65 + 12)}%, transparent)` : 'var(--background)', color: risk > 0 ? 'var(--foreground)' : 'var(--muted-foreground)' }}>
          {risk > 0 ? Math.round(risk * 100) + '%' : '·'}
        </div>;
      })}
    </div>
    <div className='flex items-center gap-3'><span className='text-[9px] text-muted-foreground'>Low risk</span><div className='risk-legend flex-1' /><span className='text-[9px] text-muted-foreground'>High risk</span></div>
    <p className='flex items-start gap-1.5 text-[10px] leading-5 text-muted-foreground'><Info className='mt-1 size-3 shrink-0' />Camera-frame coordinates, not a geographic map. Risk is an evidence index, not measured damage.</p>
  </CardContent></Card>;
}
