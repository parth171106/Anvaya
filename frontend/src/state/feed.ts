import { create } from 'zustand';
import type { EventQuarantined, EventSummary } from '@/lib/types';

export const MAX_ROWS = 500;
export const FLUSH_MAX = 12;

/** One Live Feed row: a normalized event, or a record held in quarantine. */
export type FeedEntry =
  | { kind: 'event'; id: string; seq: number; time: number; e: EventSummary }
  | { kind: 'quarantine'; id: string; seq: number; time: number; q: EventQuarantined };

export function entryOf(x: EventSummary | EventQuarantined, kind: 'event' | 'quarantine'): FeedEntry {
  return kind === 'event'
    ? { kind, id: (x as EventSummary).event_id, seq: x.seq, time: x.time, e: x as EventSummary }
    : { kind, id: `q:${x.raw_id}`, seq: x.seq, time: x.time, q: x as EventQuarantined };
}

interface FeedState {
  rows: FeedEntry[];               // newest first, ≤ MAX_ROWS
  ids: Set<string>;
  pending: FeedEntry[];            // waiting for the next flush (oldest first)
  paused: boolean;
  suspendAnimUntil: number;
  fresh: Set<string>;              // ids inserted by the latest flush (animated unless suspended)
  enqueue: (e: FeedEntry) => void;
  flush: (now?: number) => void;
  hydrate: (rows: FeedEntry[]) => void;
  setPaused: (p: boolean) => void;
  suspendAnimation: (ms: number) => void;
  reset: () => void;
}

const initial = () => ({ rows: [] as FeedEntry[], ids: new Set<string>(), pending: [] as FeedEntry[], paused: false,
  suspendAnimUntil: 0, fresh: new Set<string>() });

export const useFeedStore = create<FeedState>((set, get) => ({
  ...initial(),
  enqueue: (e) => {
    const s = get();
    if (s.ids.has(e.id) || s.pending.some((p) => p.id === e.id)) return; // SSE replay can resend
    // A record that leaves quarantine replaces its quarantine row when its event arrives.
    set({ pending: [...s.pending, e] });
  },
  flush: (now = Date.now()) => {
    const s = get();
    if (s.paused || s.pending.length === 0) {
      if (s.fresh.size) set({ fresh: new Set() });
      return;
    }
    const batch = s.pending.slice(0, FLUSH_MAX);
    const ids = new Set(s.ids);
    let rows = s.rows;
    const added: FeedEntry[] = [];
    for (const e of batch) {
      if (ids.has(e.id)) continue;  // already shown: the initial page load can race the live stream
      if (e.kind === 'event' && ids.has(`q:${e.e.raw_id}`)) {
        rows = rows.filter((r) => r.id !== `q:${e.e.raw_id}`);
        ids.delete(`q:${e.e.raw_id}`);
      }
      ids.add(e.id);
      added.push(e);
    }
    // Every row id is unique (duplicate React keys leave stale rows stacked on top of each other), newest first.
    rows = [...added, ...rows].sort((a, b) => b.seq - a.seq).slice(0, MAX_ROWS);
    const animate = now >= s.suspendAnimUntil;
    set({ rows, ids: new Set(rows.map((r) => r.id)), pending: s.pending.slice(batch.length),
      fresh: animate ? new Set(added.map((b) => b.id)) : new Set() });
  },
  hydrate: (incoming) => {
    const s = get();
    const merged = [...s.rows];
    const ids = new Set(s.ids);
    for (const r of incoming) if (!ids.has(r.id)) { merged.push(r); ids.add(r.id); }
    const rows = merged.sort((a, b) => b.seq - a.seq).slice(0, MAX_ROWS);
    set({ rows, ids: new Set(rows.map((r) => r.id)), pending: s.pending.filter((p) => !ids.has(p.id)) });
  },
  setPaused: (paused) => set({ paused }),
  suspendAnimation: (ms) => set({ suspendAnimUntil: Date.now() + ms }),
  reset: () => set(initial()),
}));
