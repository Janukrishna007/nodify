import type { Detection } from '@/lib/state';

const colors = { fire: '#fb923c', smoke: '#d4d4d8', flood: '#38bdf8' };

export function BoundingBox({ detection }: { detection: Detection }) {
  const [x1, y1, x2, y2] = detection.box;
  return <div className='pointer-events-none absolute border-2'
    style={{ left: x1 * 100 + '%', top: y1 * 100 + '%', width: (x2 - x1) * 100 + '%', height: (y2 - y1) * 100 + '%', borderColor: colors[detection.type] }}>
    <span className='absolute left-0 top-0 whitespace-nowrap bg-black/80 px-1 py-0.5 text-[10px] text-white'>
      {detection.type} {Math.round(detection.confidence * 100)}%
    </span>
  </div>;
}
