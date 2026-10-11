// The small Zustand slices of UI_UX_BRIEF.md §7 (the feed lives in feed.ts, the demo in demo.ts).
import { create } from 'zustand';
import type { IncidentSummary, LedgerVerifyResult, SourceInfo, Stats, TamperInfo } from '@/lib/types';

export type StreamStatus = 'connecting' | 'live' | 'reconnecting' | 'offline';

export const useStreamStore = create<{
  status: StreamStatus; lastEventId: number;
  setStatus: (s: StreamStatus) => void; setLastId: (id: number) => void; reset: () => void;
}>((set) => ({
  status: 'connecting', lastEventId: 0,
  setStatus: (status) => set({ status }), setLastId: (lastEventId) => set({ lastEventId }),
  reset: () => set({ lastEventId: 0 }),  // keep the connection status: the stream itself survives a demo reset
}));

export const useStatsStore = create<{
  stats: Stats | null; epsSeries: { t: number; eps: number }[];
  setStats: (s: Stats) => void; reset: () => void;
}>((set, get) => ({
  stats: null, epsSeries: [],
  setStats: (stats) => set({ stats, epsSeries: [...get().epsSeries, { t: Date.now(), eps: stats.ingest_rate_eps }].slice(-60) }),
  reset: () => set({ stats: null, epsSeries: [] }),
}));

export const useIncidentStore = create<{
  byId: Record<string, IncidentSummary>; toasted: Set<string>; toastQueue: string[];
  upsert: (i: IncidentSummary) => void; markToasted: (id: string) => void; setAll: (items: IncidentSummary[]) => void;
  reset: () => void;
}>((set, get) => ({
  byId: {}, toasted: new Set(), toastQueue: [],
  upsert: (i) => {
    const s = get();
    const queue = i.risk >= 90 && !s.toasted.has(i.incident_id) && !s.toastQueue.includes(i.incident_id)
      ? [...s.toastQueue, i.incident_id] : s.toastQueue;
    set({ byId: { ...s.byId, [i.incident_id]: i }, toastQueue: queue });
  },
  markToasted: (id) => set((s) => ({ toasted: new Set([...s.toasted, id]), toastQueue: s.toastQueue.filter((x) => x !== id) })),
  setAll: (items) => set((s) => ({ byId: { ...s.byId, ...Object.fromEntries(items.map((i) => [i.incident_id, i])) } })),
  reset: () => set({ byId: {}, toasted: new Set(), toastQueue: [] }),
}));

export const useSourcesStore = create<{
  byDevice: Record<string, SourceInfo>;
  setAll: (items: SourceInfo[]) => void;
  setStatus: (device: string, status: SourceInfo['status'], silentFor: number, expectedGap?: number | null) => void;
  reset: () => void;
}>((set) => ({
  byDevice: {},
  setAll: (items) => set({ byDevice: Object.fromEntries(items.map((s) => [s.device, s])) }),
  setStatus: (device, status, silentFor, expectedGap) => set((s) => {
    const cur = s.byDevice[device];
    if (!cur) return s;
    return { byDevice: { ...s.byDevice, [device]: { ...cur, status, silent_for_s: silentFor,
      expected_gap_s: expectedGap ?? cur.expected_gap_s } } };
  }),
  reset: () => set({ byDevice: {} }),
}));

export const useIntegrityStore = create<{
  lastVerify: LedgerVerifyResult | null; tamperInfo: TamperInfo | null; sealedBatches: number;
  setVerify: (r: LedgerVerifyResult) => void; setTamper: (t: TamperInfo | null) => void; incSealed: () => void;
  reset: () => void;
}>((set) => ({
  lastVerify: null, tamperInfo: null, sealedBatches: 0,
  setVerify: (lastVerify) => set({ lastVerify }), setTamper: (tamperInfo) => set({ tamperInfo }),
  incSealed: () => set((s) => ({ sealedBatches: s.sealedBatches + 1 })),
  reset: () => set({ lastVerify: null, tamperInfo: null, sealedBatches: 0 }),
}));

export const useReplayStore = create<{
  active: { replayId: string; done: number; total: number } | null; quarantineTotal: number;
  parserFor: Record<string, string>; completed: { replayId: string; parsed: number; stillQuarantined: number } | null;
  progress: (replayId: string, done: number, total: number) => void;
  complete: (replayId: string, parsed: number, stillQuarantined: number) => void;
  setParser: (replayId: string, parser: string) => void;
  setQuarantineTotal: (n: number) => void; reset: () => void;
}>((set) => ({
  active: null, quarantineTotal: 0, parserFor: {}, completed: null,
  progress: (replayId, done, total) => set({ active: { replayId, done, total } }),
  complete: (replayId, parsed, stillQuarantined) => set((s) => ({
    active: s.active ? { ...s.active, done: s.active.total } : null, completed: { replayId, parsed, stillQuarantined } })),
  setParser: (replayId, parser) => set((s) => ({ parserFor: { ...s.parserFor, [replayId]: parser } })),
  setQuarantineTotal: (quarantineTotal) => set({ quarantineTotal }),
  reset: () => set({ active: null, quarantineTotal: 0, parserFor: {}, completed: null }),
}));

export const useLineageStore = create<{
  hoveredPath: string | null; pinnedPath: string | null;
  setHover: (p: string | null) => void; setPin: (p: string | null) => void; clear: () => void;
}>((set) => ({
  hoveredPath: null, pinnedPath: null,
  setHover: (hoveredPath) => set({ hoveredPath }), setPin: (pinnedPath) => set({ pinnedPath }),
  clear: () => set({ hoveredPath: null, pinnedPath: null }),
}));
