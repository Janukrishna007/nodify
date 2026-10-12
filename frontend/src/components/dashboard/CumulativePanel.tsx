import { cellRisk, type Cell, type Filters } from '@/lib/state';

export function CumulativePanel({ cells, filters }: { cells: Cell[]; filters: Filters }) {
  return <section className='glass grid gap-6 rounded-2xl p-6 md:grid-cols-[1fr_2fr]'>
    <div>
      <h2 className='text-lg font-semibold'>Cumulative heatmap</h2>
      <p className='mt-2 text-sm leading-6 text-white/60'>Mean weighted detection evidence across all analyzed frames. Empty cells have no observed evidence.</p>
      <p className='mt-3 text-xs leading-5 text-white/40'>This grid uses camera-frame coordinates. Moving drone footage is not registered to a geographic map.</p>
      <div className='mt-4 h-2 rounded-full bg-gradient-to-r from-blue-600 via-green-400 via-yellow-400 to-red-500' />
      <div className='mt-1 flex justify-between text-xs text-white/50'><span>0% risk index</span><span>100%</span></div>
    </div>
    <div className='grid grid-cols-8 gap-1' aria-label='Cumulative risk grid'>
      {Array.from({ length: 48 }, (_, index) => {
        const cell = cells[index];
        const risk = cell ? cellRisk(cell, filters, true) : 0;
        return <div key={index} title={`Row ${Math.floor(index / 8) + 1}, column ${index % 8 + 1}: ${Math.round(risk * 100)}%`}
          className='flex min-h-9 items-center justify-center rounded border border-white/10 text-[10px]'
          style={{ background: risk > 0 ? `hsla(${240 * (1 - risk)}, 100%, 45%, 0.7)` : 'rgba(255,255,255,0.02)' }}>
          {risk > 0 ? Math.round(risk * 100) + '%' : '—'}
        </div>;
      })}
    </div>
  </section>;
}
