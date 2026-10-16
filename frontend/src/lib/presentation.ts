import type { DisasterType, Session } from './state';

export const disasterLabels: Record<DisasterType, string> = { fire: 'Fire', smoke: 'Smoke', flood: 'Flood' };
export const number = (value: number) => new Intl.NumberFormat('en-US').format(value);
export const sessionHref = (id: string) => `/dashboard?session=${encodeURIComponent(id)}`;
export const isRunning = (session: Session) => ['queued', 'loading', 'processing'].includes(session.status);
export const title = (filename: string) => filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
export const date = (value: string) => new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value));
export const time = (value: number) => `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, '0')}`;
export const detectionTotal = (session: Session) => Object.values(session.detectionCounts).reduce((sum, value) => sum + (value ?? 0), 0);
export const statusLabel = (status: Session['status']) => ({ queued: 'Queued', loading: 'Preparing', processing: 'Analyzing', completed: 'Completed', failed: 'Failed', cancelled: 'Stopped' }[status]);
