import Image from 'next/image';
import { BoundingBox } from './BoundingBox';
import { HeatmapOverlay } from './HeatmapOverlay';
import type { Filters, FrameData } from '@/lib/state';

export function VideoFeed({ frame, filters, showHeatmap, selected }: {
  frame?: FrameData; filters: Filters; showHeatmap: boolean; selected?: string;
}) {
  if (!frame) return <div className='flex aspect-video items-center justify-center rounded-2xl border border-white/10 bg-black/50 p-8 text-center text-white/50'>
    Frames will appear after the models finish loading.
  </div>;
  return <div className='relative mx-auto w-full overflow-hidden rounded-2xl border border-white/10 bg-black'
    style={{ aspectRatio: `${frame.width}/${frame.height}`, maxWidth: `${70 * frame.width / frame.height}vh` }}>
    <Image src={frame.imageUrl} alt={`Analyzed video frame ${frame.frameNumber}`} width={frame.width} height={frame.height} unoptimized className='block h-full w-full' />
    {showHeatmap && <HeatmapOverlay cells={frame.cells} filters={filters} selected={selected} />}
    {frame.detections.filter((detection) => filters[detection.type]).map((detection) => <BoundingBox key={detection.id} detection={detection} />)}
  </div>;
}
