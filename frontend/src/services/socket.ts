import { fetchFrame, fetchSession } from './api';
import type { FrameData, Session } from '@/lib/state';

// Polling survives reconnects and browser refreshes; all data comes from inference.
export function connectAnalysis(id: string, onUpdate: (session: Session, frame?: FrameData) => void, onError: (message: string) => void) {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  let previousIndex: number | null = null;
  const poll = async () => {
    let terminal = false;
    try {
      const session = await fetchSession(id);
      const frame = session.latestIndex !== null && session.latestIndex !== previousIndex
        ? await fetchFrame(id, session.latestIndex) : undefined;
      if (stopped) return;
      previousIndex = session.latestIndex;
      onUpdate(session, frame);
      terminal = ['completed', 'failed', 'cancelled'].includes(session.status);
    } catch (error) {
      if (!stopped) onError(error instanceof Error ? error.message : 'Connection lost. Retrying…');
    }
    if (!stopped && !terminal) timer = setTimeout(poll, 1000);
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); };
}

