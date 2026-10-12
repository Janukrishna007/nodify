import { cellRisk, type Cell, type Filters } from '@/lib/state';

export function HeatmapOverlay({ cells, filters, cumulative = false, selected }: {
  cells: Cell[]; filters: Filters; cumulative?: boolean; selected?: string;
}) {
  return <div className='pointer-events-none absolute inset-0 grid grid-cols-8 grid-rows-6'>
    {Array.from({ length: 48 }, (_, index) => {
      const cell = cells[index];
      const risk = cell ? cellRisk(cell, filters, cumulative) : 0;
      return <div key={index} className='border border-white/10'
        style={{ backgroundColor: risk > 0 ? `hsla(${240 * (1 - risk)}, 100%, 50%, ${risk * 0.6})` : 'transparent',
          outline: cell && selected === `${cell.row}-${cell.col}` ? '2px solid white' : undefined }} />;
    })}
  </div>;
}
