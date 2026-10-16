import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useNavigate } from 'react-router';
import { PresenterPanel, usePresenterKeys } from '@/components/presenter/Presenter';
import { IncidentToast } from '@/features/incidents/IncidentToast';
import { api } from '@/lib/api';
import { qk } from '@/lib/queryKeys';
import { setNavigator, useStreamConnection } from '@/lib/stream';
import { useDemoStore, useIncidentStore, useSourcesStore, useStatsStore } from '@/state';
import { NavRail } from './NavRail';
import { TopBar } from './TopBar';

/** Hydrates the live stores once, so badges and toasts are right on any first route. */
function useBootstrap() {
  const demo = useQuery({ queryKey: qk.demo, queryFn: api.demo.state });
  const stats = useQuery({ queryKey: qk.stats, queryFn: api.stats });
  const incidents = useQuery({ queryKey: qk.incidents, queryFn: api.incidents.list });
  const sources = useQuery({ queryKey: qk.sources, queryFn: api.sources });
  useEffect(() => { if (demo.data) useDemoStore.getState().hydrate(demo.data); }, [demo.data]);
  useEffect(() => { if (stats.data) useStatsStore.getState().setStats(stats.data); }, [stats.data]);
  const seeded = useRef(false);
  useEffect(() => {
    if (!incidents.data) return;
    const s = useIncidentStore.getState();
    s.setAll(incidents.data.items);
    if (!seeded.current) {  // incidents that existed before this page loaded aren't toasted again
      seeded.current = true;
      incidents.data.items.forEach((i) => s.markToasted(i.incident_id));
    }
  }, [incidents.data]);
  useEffect(() => { if (sources.data) useSourcesStore.getState().setAll(sources.data.items); }, [sources.data]);
}

export function AppShell() {
  const navigate = useNavigate();
  useEffect(() => setNavigator((to) => navigate(to)), [navigate]);
  useStreamConnection();
  usePresenterKeys();
  useBootstrap();
  return (
    <div className="flex h-dvh flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <NavRail />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1760px] [overflow-wrap:anywhere] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <IncidentToast />
      <PresenterPanel />
    </div>
  );
}
