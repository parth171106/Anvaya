import { lazy, Suspense, type ComponentType, type LazyExoticComponent, type ReactNode } from 'react';
import { createBrowserRouter, Link, Navigate } from 'react-router';
import { Bone, EmptyState, RouteErrorBoundary, Skeleton } from '@/components/common/states';
import { AppShell } from '@/components/shell/AppShell';
import { Button } from '@/components/ui/button';
import { MapPinOff } from 'lucide-react';

const Overview = lazy(() => import('@/features/overview/Overview'));
const Feed = lazy(() => import('@/features/feed/Feed'));
const EventDetail = lazy(() => import('@/features/event/EventDetail'));
const IncidentList = lazy(() => import('@/features/incidents/IncidentList'));
const IncidentDetail = lazy(() => import('@/features/incidents/IncidentDetail'));
const AttackReplay = lazy(() => import('@/features/replay/AttackReplay'));
const Search = lazy(() => import('@/features/search/Search'));
const Integrity = lazy(() => import('@/features/integrity/Integrity'));
const Sources = lazy(() => import('@/features/sources/Sources'));
const Delivery = lazy(() => import('@/features/delivery/Delivery'));
const Account = lazy(() => import('@/features/account/Account'));

/** Route-level fallbacks are skeletons shaped like the screen, never spinners (UI_UX_BRIEF.md §3.1). */
const skeletons = {
  title: <Bone className="mb-6 h-9 w-[420px]" />,
  counters: <div className="grid grid-cols-1 gap-4 min-[480px]:grid-cols-2 xl:grid-cols-3 min-[1600px]:grid-cols-5">{[0, 1, 2, 3, 4].map((i) => <Bone key={i} className="h-[120px]" />)}</div>,
  rows: <div className="space-y-2">{Array.from({ length: 10 }, (_, i) => <Bone key={i} className="h-12" />)}</div>,
  panes: <div className="grid grid-cols-1 gap-6 xl:grid-cols-2"><Bone className="h-[520px]" /><Bone className="h-[520px]" /></div>,
};

function page(C: LazyExoticComponent<ComponentType>, body: ReactNode) {
  return (
    <RouteErrorBoundary>
      <Suspense fallback={<Skeleton>{skeletons.title}{body}</Skeleton>}><C /></Suspense>
    </RouteErrorBoundary>
  );
}

function NotFound() {
  return (
    <EmptyState icon={MapPinOff} title="There's nothing at this address." body="The page may have moved."
      action={<Button asChild><Link to="/overview">Go to Overview</Link></Button>} />
  );
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <Navigate to="/overview" replace /> },
      { path: '/overview', element: page(Overview, skeletons.counters) },
      { path: '/feed', element: page(Feed, skeletons.rows) },
      { path: '/events/:eventId', element: page(EventDetail, skeletons.panes) },
      { path: '/incidents', element: page(IncidentList, skeletons.rows) },
      { path: '/incidents/:incidentId', element: page(IncidentDetail, skeletons.rows) },
      { path: '/replay', element: page(AttackReplay, skeletons.panes) },
      { path: '/search', element: page(Search, skeletons.rows) },
      { path: '/integrity', element: page(Integrity, skeletons.rows) },
      { path: '/sources', element: page(Sources, skeletons.rows) },
      { path: '/delivery', element: page(Delivery, skeletons.counters) },
      { path: '/account', element: page(Account, skeletons.rows) },
      { path: '*', element: <NotFound /> },
    ],
  },
]);
