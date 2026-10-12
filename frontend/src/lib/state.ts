import { create } from 'zustand';

export type DisasterType = 'fire' | 'smoke' | 'flood';
export type Filters = Record<DisasterType, boolean>;
export type Detection = {
  id: string; type: DisasterType; confidence: number; weight: number;
  box: [number, number, number, number]; sourceModel: string;
};
export type Cell = {
  row: number; col: number; score: number; risk: number; cumulativeRisk: number;
  byClass: Record<DisasterType, { score: number; mean: number }>;
};
export type FrameData = {
  index: number; frameNumber: number; timestamp: number; width: number; height: number;
  detections: Detection[]; cells: Cell[]; imageUrl: string; heatmapUrl: string;
  cumulativeUrl: string; inferenceMs: number;
};
export type Zone = Cell & { id: string; type: string; severity: number };
export type Session = {
  id: string; filename: string; status: 'queued' | 'loading' | 'processing' | 'completed' | 'cancelled' | 'failed';
  createdAt: string; updatedAt: string; confidence: number; frameSkip: number;
  analyzedFrames: number; latestIndex: number | null; progress: number;
  totalFrames?: number; framesRead?: number; fps?: number; expectedSamples?: number;
  detectionCounts: Partial<Record<DisasterType, number>>; error: string | null;
  elapsedSeconds?: number; grid: { rows: number; cols: number };
  cumulativeCells?: Cell[];
};

export function cellRisk(cell: Cell, filters: Filters, cumulative = false) {
  const raw = (Object.keys(filters) as DisasterType[]).reduce(
    (sum, key) => sum + (filters[key] ? cell.byClass[key][cumulative ? 'mean' : 'score'] : 0), 0);
  return raw / (1 + raw);
}

export const useUIStore = create<{
  filters: Filters; toggleFilter: (key: DisasterType) => void;
}>((set) => ({
  filters: { fire: true, smoke: true, flood: true },
  toggleFilter: (key) => set((state) => ({ filters: { ...state.filters, [key]: !state.filters[key] } })),
}));

