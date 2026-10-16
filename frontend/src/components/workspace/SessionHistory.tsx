'use client';

import { useState } from 'react';
import Link from 'next/link';
import { RefreshCw, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { PageHeading, SessionTable } from './DashboardPrimitives';
import { useWorkspace } from './WorkspaceProvider';

export function SessionHistory({ initialQuery = '' }: { initialQuery?: string }) {
  const { sessions, refresh, loading } = useWorkspace();
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState('all');
  const visible = sessions.filter((session) => session.filename.toLowerCase().includes(query.toLowerCase()) &&
    (filter === 'all' || filter === 'active' && ['queued', 'loading', 'processing'].includes(session.status) || session.status === filter));
  return <main className='fade-in flex flex-col gap-6'>
    <PageHeading eyebrow='Your analysis library' title='Session history' description='Every perspective, preserved. Revisit your footage, inspect results and export the evidence.' actions={<><Button variant='outline' onClick={() => void refresh()}><RefreshCw data-icon='inline-start' />Refresh</Button><Button asChild><Link href='/upload'><Upload data-icon='inline-start' />New analysis</Link></Button></>} />
    <div className='flex flex-wrap items-center justify-between gap-4'><Tabs value={filter} onValueChange={setFilter}><TabsList><TabsTrigger value='all'>All sessions</TabsTrigger><TabsTrigger value='completed'>Completed</TabsTrigger><TabsTrigger value='active'>Active</TabsTrigger><TabsTrigger value='failed'>Failed</TabsTrigger></TabsList></Tabs><FieldGroup className='w-full sm:w-72'><Field orientation='horizontal'><FieldLabel htmlFor='history-search' className='sr-only'>Search video filename</FieldLabel><Input id='history-search' value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search video filename...' />{query && <Button variant='ghost' size='icon' aria-label='Clear session search' onClick={() => setQuery('')}><X /></Button>}</Field></FieldGroup></div>
    <p className='text-[11px] text-muted-foreground'>{loading ? 'Loading saved analyses…' : `${visible.length} of ${sessions.length} sessions`}</p>
    <SessionTable sessions={visible} caption={query ? `Results for “${query}”` : 'Analysis sessions'} />
  </main>;
}
