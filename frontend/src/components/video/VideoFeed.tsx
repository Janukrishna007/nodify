import Image from 'next/image';
import { ScanLine } from 'lucide-react';
import { BoundingBox } from './BoundingBox';
import { HeatmapOverlay } from './HeatmapOverlay';
import type { Filters, FrameData } from '@/lib/state';
import { Badge } from '@/components/ui/badge';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';

export function VideoFeed({ frame, filters, showHeatmap, selected }: {
  frame?: FrameData; filters: Filters; showHeatmap: boolean; selected?: string;
}) {
  return <div className='frame-stage h-[min(420px,50vh)] overflow-hidden'>
    {frame ? <div className='relative w-full' style={{ aspectRatio: `${frame.width}/${frame.height}`, maxWidth: `calc(min(420px, 50vh) * ${frame.width / frame.height})` }}>
      <Image src={frame.imageUrl} alt={`Analyzed video frame ${frame.frameNumber}`} width={frame.width} height={frame.height} unoptimized loading='eager' className='block size-full' />
      {showHeatmap && <HeatmapOverlay cells={frame.cells} filters={filters} selected={selected} />}
      {frame.detections.filter((detection) => filters[detection.type]).map((detection) => <BoundingBox key={detection.id} detection={detection} />)}
    </div> : <Empty><EmptyHeader><EmptyMedia variant='icon'><ScanLine /></EmptyMedia><EmptyTitle>Preparing your perspective</EmptyTitle><EmptyDescription>Analyzed frames appear here as soon as the detection models are ready.</EmptyDescription></EmptyHeader></Empty>}
    {frame && <div className='absolute left-4 top-4'><Badge variant='secondary'>{frame.intensity?.level && frame.intensity.level !== 'none' ? `${frame.intensity.level} intensity` : 'Analyzed frame'}</Badge></div>}
    <span className='pointer-events-none absolute bottom-3 right-3 font-mono text-[9px] tracking-wider text-muted-foreground'>DISASTERVISION / FRAME ANALYSIS</span>
  </div>;
}
