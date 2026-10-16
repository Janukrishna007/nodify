'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Activity, ArrowUpRight, Bell, ChevronRight, CircleHelp, FolderClock, LayoutDashboard, Menu, Radio, ScanLine, Search, ShieldCheck, Upload, Video } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { WorkspaceProvider, useWorkspace } from './WorkspaceProvider';
import { sessionHref } from '@/lib/presentation';
import { Skeleton } from '@/components/ui/skeleton';

function WorkspaceNavigation({ onNavigate }: { onNavigate: () => void }) {
  const pathname = usePathname();
  const query = useSearchParams();
  const { sessions, activeSession } = useWorkspace();
  const inAnalysis = pathname === '/dashboard' && query.has('session');
  const latest = activeSession ?? sessions.find((session) => session.analyzedFrames > 0)?.id;
  const alerts = sessions.flatMap((session) => session.alerts ?? []).filter((alert) => !alert.acknowledgedAt).length;
  const navigation = [
    { label: 'Overview', href: '/dashboard', icon: LayoutDashboard, active: pathname === '/dashboard' && !inAnalysis },
    { label: 'Video analysis', href: latest ? sessionHref(latest) : '/upload', icon: Video, active: inAnalysis },
    { label: 'Upload footage', href: '/upload', icon: Upload, active: pathname === '/upload' },
    { label: 'Session history', href: '/sessions', icon: FolderClock, active: pathname === '/sessions' },
    { label: 'Disaster alerts', href: '/alerts', icon: Bell, active: pathname === '/alerts' },
  ];
  return <nav aria-label='Main navigation' className='flex flex-col gap-1'>
    {navigation.map((item) => <Link key={item.label} href={item.href} className='nav-item' data-active={item.active} aria-current={item.active ? 'page' : undefined} onClick={onNavigate}>
      <item.icon /><span className='flex-1'>{item.label}</span>{item.label === 'Disaster alerts' && alerts > 0 && <span className='rounded bg-warning/10 px-1.5 text-[10px] text-warning'>{alerts}</span>}
    </Link>)}
  </nav>;
}

function ShellContent({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const checkedNavigation = useRef(false);
  useEffect(() => {
    if (checkedNavigation.current) return;
    checkedNavigation.current = true;
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (navigation?.type === 'reload' && pathname !== '/upload') router.replace('/upload');
  }, [pathname, router]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { connected, loading } = useWorkspace();
  const sidebar = <div className='flex h-full min-h-0 flex-col px-4 py-6'>
    <Link href='/dashboard' className='flex shrink-0 items-center gap-3 px-2' onClick={() => setMobileOpen(false)}>
      <span className='flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground'><ScanLine className='size-6' strokeWidth={1.5} /></span>
      <span><span className='block text-base font-semibold tracking-tight text-foreground'>DisasterVision</span><span className='text-[8px] uppercase tracking-[.13em] text-muted-foreground'>Intelligence workspace</span></span>
    </Link>
    <div className='flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto py-7'>
      <Button asChild className='w-full'><Link href='/upload' onClick={() => setMobileOpen(false)}><Upload data-icon='inline-start' />New analysis<ArrowUpRight data-icon='inline-end' /></Link></Button>
      <p className='eyebrow px-3'>Workspace</p>
      <Suspense fallback={<Skeleton className='h-52 w-full' />}><WorkspaceNavigation onNavigate={() => setMobileOpen(false)} /></Suspense>
    </div>
    <div className='flex shrink-0 flex-col gap-3'>
      <div className='flex items-center gap-3 rounded-xl border border-border bg-primary/[.025] p-3'>
        <ShieldCheck className='size-4 shrink-0 text-primary' />
        <div><p className='text-xs font-medium'>Local processing</p><p className='mt-1 text-[10px] text-muted-foreground'>Your data stays on this device</p></div>
      </div>
      <a href='http://127.0.0.1:8000/docs' target='_blank' rel='noreferrer' className='nav-item'><CircleHelp /><span className='flex-1'>Help & API</span><ArrowUpRight /></a>
      <Separator />
      <div className='flex items-center gap-3 px-2 pt-1'><div className='flex size-8 items-center justify-center rounded-full border border-border bg-secondary text-xs font-medium text-primary'>DV</div><div><p className='text-xs font-medium'>Local workspace</p><p className='text-[10px] text-muted-foreground'>Private processing</p></div></div>
    </div>
  </div>;
  return <div className='workspace-background'>
    <aside className='fixed inset-y-0 left-0 z-30 hidden w-[248px] border-r border-sidebar-border bg-sidebar backdrop-blur-2xl lg:block'>{sidebar}</aside>
    <div className='relative min-h-screen lg:pl-[248px]'>
      <header className='flex h-[76px] items-center justify-between gap-4 border-b border-border bg-background/50 px-5 backdrop-blur-xl md:px-8'>
        <div className='flex min-w-0 items-center gap-3'>
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild><Button variant='ghost' size='icon' className='lg:hidden' aria-label='Open navigation'><Menu /></Button></SheetTrigger>
            <SheetContent side='left' className='w-[270px] p-0'><SheetTitle className='sr-only'>Workspace navigation</SheetTitle>{sidebar}</SheetContent>
          </Sheet>
          <span className='hidden text-xs text-muted-foreground sm:inline'>Workspace</span><ChevronRight className='hidden size-3 text-muted-foreground sm:block' /><span className='truncate text-xs font-medium'>{pathname === '/upload' ? 'New analysis' : pathname === '/sessions' ? 'Session history' : pathname === '/alerts' ? 'Disaster alerts' : 'Intelligence overview'}</span>
        </div>
        <div className='flex items-center gap-3 md:gap-5'>
          <form action='/sessions' role='search' className='hidden w-64 shrink-0 md:block'><FieldGroup><Field orientation='horizontal'><FieldLabel htmlFor='workspace-search' className='sr-only'>Search sessions</FieldLabel><Input id='workspace-search' name='q' placeholder='Search sessions...' className='w-full' /><Button variant='ghost' size='icon' aria-label='Search sessions'><Search /></Button></Field></FieldGroup></form>
          <span className={connected ? 'flex items-center gap-2 text-[11px] text-success' : 'flex items-center gap-2 text-[11px] text-muted-foreground'} role='status'><span className='status-dot' /><span className='hidden sm:inline'>{loading ? 'Connecting' : connected ? 'Systems operational' : 'Service offline'}</span></span>
          <Separator orientation='vertical' className='h-5' />
          <Button asChild variant='ghost' size='icon' aria-label='Open disaster alerts'><Link href='/alerts'><Bell /></Link></Button>
        </div>
      </header>
      <div className='mx-auto max-w-[1600px] px-5 py-7 md:px-8 md:py-8'>{children}</div>
      <footer className='mx-5 mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border py-5 text-[10px] text-muted-foreground md:mx-8'><span className='flex items-center gap-2'><Activity className='size-3' />DisasterVision · Intelligence for faster response</span><span className='flex items-center gap-2'><Radio className='size-3' />Local inference · Camera-frame analysis</span></footer>
    </div>
  </div>;
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  return <WorkspaceProvider><ShellContent>{children}</ShellContent></WorkspaceProvider>;
}
