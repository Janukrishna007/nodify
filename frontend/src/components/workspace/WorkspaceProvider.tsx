'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { checkBackend, fetchSessions } from '@/services/api';
import type { Session } from '@/lib/state';

type Workspace = {
  sessions: Session[]; connected: boolean; loading: boolean; error: string;
  activeSession: string | null; refresh: () => Promise<void>;
};

const WorkspaceContext = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const [health, history] = await Promise.all([checkBackend(), fetchSessions()]);
      setSessions(history); setActiveSession(health.activeSession); setConnected(true); setError('');
    } catch (failure) {
      setConnected(false);
      setError(failure instanceof Error ? failure.message : 'Could not connect to the analysis service.');
    } finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  return <WorkspaceContext.Provider value={{ sessions, connected, loading, error, activeSession, refresh }}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error('WorkspaceProvider is required.');
  return context;
}
