'use client';

import { useState } from 'react';
import { Bell, BellOff, CircleAlert, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { PageHeading } from './DashboardPrimitives';
import { AlertFeed } from './AlertFeed';
import { useWorkspace } from './WorkspaceProvider';
import { acknowledgeAlert } from '@/services/api';
import { useBrowserAlerts } from '@/lib/browser-alerts';

export function AlertCenter() {
  const { sessions, refresh } = useWorkspace();
  const [filter, setFilter] = useState('open');
  const [error, setError] = useState('');
  const browserAlerts = useBrowserAlerts();
  const alerts = sessions.flatMap((session) => session.alerts ?? []).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const visible = alerts.filter((alert) => filter === 'all' || (filter === 'open' ? !alert.acknowledgedAt : !!alert.acknowledgedAt));
  const acknowledge = async (id: string) => {
    const alert = alerts.find((item) => item.id === id);
    if (!alert) return;
    try { await acknowledgeAlert(alert.sessionId, id); await refresh(); setError(''); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to acknowledge alert.'); }
  };
  const enable = async () => {
    if (browserAlerts.enabled) { browserAlerts.disable(); setError(''); return; }
    try { await browserAlerts.enable(); setError(''); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not enable browser alerts.'); }
  };
  return <main className='fade-in flex flex-col gap-6'>
    <PageHeading eyebrow='Stay aware. Respond with clarity.' title='Disaster alerts' description='Review persistent hazard detections and acknowledge the events you have assessed.' actions={<><Button variant='outline' onClick={() => void refresh()} aria-label='Refresh alerts'><RefreshCw /></Button><Button aria-pressed={browserAlerts.enabled} onClick={() => void enable()}>{browserAlerts.enabled ? <BellOff data-icon='inline-start' /> : <Bell data-icon='inline-start' />}{browserAlerts.enabled ? 'Disable browser alerts' : 'Enable browser alerts'}</Button></>} />
    <p className='text-xs text-muted-foreground'>Desktop notifications are {browserAlerts.enabled ? 'on' : 'off'}. Your preference is saved in this browser; dashboard alerts remain available.</p>
    {error && <Alert variant='destructive'><CircleAlert /><AlertTitle>Notification update</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    <Tabs value={filter} onValueChange={setFilter}><TabsList><TabsTrigger value='open'>Open ({alerts.filter((alert) => !alert.acknowledgedAt).length})</TabsTrigger><TabsTrigger value='acknowledged'>Acknowledged</TabsTrigger><TabsTrigger value='all'>All alerts</TabsTrigger></TabsList></Tabs>
    <Card><CardHeader><CardTitle>Response inbox</CardTitle><CardDescription>{visible.length} alerts in this view · Model confidence and persistence determine the risk signal.</CardDescription></CardHeader><CardContent><AlertFeed alerts={visible} onAcknowledge={(id) => void acknowledge(id)} limit={100} /></CardContent></Card>
  </main>;
}
