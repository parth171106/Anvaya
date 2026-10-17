// useStreamConnection: one EventSource on /api/stream, dispatched by event type (UI_UX_BRIEF.md §8, APP_FLOW.md FL-12).
import { useEffect } from 'react';
import { QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  resetAllStores, useDemoStore, useFeedStore, useIncidentStore, useIntegrityStore, useReplayStore, useSourcesStore,
  useStatsStore, useStreamStore,
} from '@/state';
import { entryOf } from '@/state/feed';
import { qk } from './queryKeys';
import type { DemoState, EventQuarantined, EventSummary, IncidentSummary, LedgerVerifyResult, Stats } from './types';

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 2000 } },
});

let navigateTo: (to: string) => void = () => {};
export function setNavigator(fn: (to: string) => void) {
  navigateTo = fn;
}

const OFFLINE_AFTER_MS = 10_000;
const ANIMATION_PAUSE_MS = 400;

type Handler = (data: never) => void;
const handlers: Record<string, Handler> = {
  'alert.created': () => { void queryClient.invalidateQueries({ queryKey: qk.alerts }); },
  'event.normalized': (e: EventSummary) => useFeedStore.getState().enqueue(entryOf(e, 'event')),
  'event.quarantined': (q: EventQuarantined) => {
    useFeedStore.getState().enqueue(entryOf(q, 'quarantine'));
    const r = useReplayStore.getState();
    r.setQuarantineTotal(r.quarantineTotal + 1);
    queryClient.invalidateQueries({ queryKey: qk.quarantine });
  },
  'stats.tick': (s: Stats) => {
    useStatsStore.getState().setStats(s);
    useReplayStore.getState().setQuarantineTotal(s.quarantined_total);
  },
  'ledger.sealed': () => {
    useIntegrityStore.getState().incSealed();
    queryClient.invalidateQueries({ queryKey: qk.batches });
  },
  'incident.opened': (i: IncidentSummary) => upsertIncident(i),
  'incident.updated': (i: IncidentSummary) => upsertIncident(i),
  'source.status_changed': (d: { device: string; status: 'learning' | 'active' | 'silent'; silent_for_s: number; expected_gap_s: number | null }) => {
    useSourcesStore.getState().setStatus(d.device, d.status, d.silent_for_s, d.expected_gap_s);
    queryClient.invalidateQueries({ queryKey: qk.sources });
    if (d.status === 'silent') {
      const gap = d.expected_gap_s != null ? Math.max(1, Math.round(d.expected_gap_s)) : null;
      toast(`${d.device} has gone silent — no events for ${d.silent_for_s} s${gap ? ` (usually every ${gap} s)` : ''}`);
      useFeedStore.getState().suspendAnimation(ANIMATION_PAUSE_MS);
    }
  },
  'verify.completed': (r: Pick<LedgerVerifyResult, 'verdict' | 'failed_records' | 'witness_status'>) => {
    const cur = useIntegrityStore.getState().lastVerify;
    if (cur) useIntegrityStore.getState().setVerify({ ...cur, ...r });
  },
  'parser.approved': (d: { name: string; version: string; group_id: string; replay_id: string }) => {
    useReplayStore.getState().setParser(d.replay_id, `${d.name}@${d.version}`);
    queryClient.invalidateQueries({ queryKey: qk.parsers });
    queryClient.invalidateQueries({ queryKey: qk.quarantine });
  },
  'replay.progress': (d: { replay_id: string; done: number; total: number }) =>
    useReplayStore.getState().progress(d.replay_id, d.done, d.total),
  'replay.completed': (d: { replay_id: string; parsed: number; still_quarantined: number }) => {
    const r = useReplayStore.getState();
    r.complete(d.replay_id, d.parsed, d.still_quarantined);
    const parser = r.parserFor[d.replay_id];
    toast(d.still_quarantined > 0
      ? `${d.still_quarantined} records still need attention`
      : parser ? `Parser ${parser} approved · ${d.parsed} records replayed` : `${d.parsed} records replayed`);
    for (const key of [qk.quarantine, qk.parsers, qk.sources, qk.stats]) queryClient.invalidateQueries({ queryKey: key });
  },
  'demo.state': (s: DemoState) => {
    if (s.reset) {
      resetAllStores();
      queryClient.clear();
      navigateTo('/overview');
      toast('Demo reset · ready');
    }
    useDemoStore.getState().hydrate({ ...s, demo_mode: true });
  },
  resync: () => {
    for (const key of [qk.stats, qk.events(), qk.incidents, qk.sources, qk.alerts]) queryClient.invalidateQueries({ queryKey: key });
  },
};

function upsertIncident(i: IncidentSummary) {
  const s = useIncidentStore.getState();
  const wasQueued = s.toastQueue.length;
  s.upsert(i);
  if (useIncidentStore.getState().toastQueue.length > wasQueued) useFeedStore.getState().suspendAnimation(ANIMATION_PAUSE_MS);
  queryClient.invalidateQueries({ queryKey: qk.incidents });
  queryClient.invalidateQueries({ queryKey: qk.incident(i.incident_id) });
}

/** Mount once (in App). Reconnects automatically; the browser sends Last-Event-ID and the server replays. */
export function useStreamConnection() {
  useEffect(() => {
    const es = new EventSource('/api/stream');
    const stream = useStreamStore.getState();
    let offlineTimer: ReturnType<typeof setTimeout> | undefined;
    es.onopen = () => {
      clearTimeout(offlineTimer);
      offlineTimer = undefined;
      stream.setStatus('live');
    };
    es.onerror = () => {
      stream.setStatus('reconnecting');
      offlineTimer ??= setTimeout(() => useStreamStore.getState().setStatus('offline'), OFFLINE_AFTER_MS);
    };
    for (const [type, fn] of Object.entries(handlers)) {
      es.addEventListener(type, (ev) => {
        const m = ev as MessageEvent<string>;
        if (m.lastEventId) stream.setLastId(Number(m.lastEventId));
        fn(JSON.parse(m.data || '{}') as never);
      });
    }
    const flush = setInterval(() => useFeedStore.getState().flush(), 250);
    return () => {
      es.close();
      clearInterval(flush);
      clearTimeout(offlineTimer);
    };
  }, []);
}
