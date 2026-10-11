import { beforeEach, describe, expect, it } from 'vitest';
import type { EventQuarantined, EventSummary } from '@/lib/types';
import { entryOf, FLUSH_MAX, MAX_ROWS, useFeedStore } from './feed';

const ev = (seq: number, raw = `r-${seq}`): EventSummary => ({
  event_id: `e-${raw.slice(2)}`, raw_id: raw, seq, time: seq * 1000, device: 'vpn01', vendor: 'Fortinet', format: 'fortigate-kv',
  class_uid: 3002, class_name: 'Authentication', activity_name: 'Logon', src_ip: '198.51.100.9', src_port: null, dst_ip: null,
  dst_port: null, protocol: null, direction: null, user_name: 'admin', action: null, status: 'Failure', severity: 'Medium',
  title: null, parse_confidence: 89, batch_id: null, flags: [],
});
const s = () => useFeedStore.getState();

describe('feed store', () => {
  beforeEach(() => s().reset());

  it('coalesces bursts into flushes of at most 12 rows, newest on top', () => {
    for (let i = 1; i <= 40; i++) s().enqueue(entryOf(ev(i), 'event'));
    s().flush();
    expect(s().rows).toHaveLength(FLUSH_MAX);
    expect(s().rows[0].seq).toBe(12);
    expect(s().pending).toHaveLength(28);
    s().flush(); s().flush(); s().flush();
    expect(s().rows).toHaveLength(40);
    expect(s().rows.map((r) => r.seq).slice(0, 3)).toEqual([40, 39, 38]);
    expect(s().pending).toHaveLength(0);
  });

  it('ignores a duplicate event_id (SSE replay after reconnect)', () => {
    s().enqueue(entryOf(ev(1), 'event'));
    s().enqueue(entryOf(ev(1), 'event'));
    s().flush();
    s().enqueue(entryOf(ev(1), 'event'));
    s().flush();
    expect(s().rows).toHaveLength(1);
  });

  it('never shows a row twice when the initial page load races the live stream', () => {
    for (let i = 1; i <= 5; i++) s().enqueue(entryOf(ev(i), 'event'));   // stream delivers 1–5 first…
    s().hydrate([3, 4, 5, 6, 7].map((i) => entryOf(ev(i), 'event')));  // …then GET /api/events returns 3–7
    for (let k = 0; k < 3; k++) s().flush();
    const ids = s().rows.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(s().rows.map((r) => r.seq)).toEqual([7, 6, 5, 4, 3, 2, 1]);
    s().enqueue(entryOf(ev(8), 'event'));
    s().hydrate([entryOf(ev(8), 'event')]);                             // already queued, then loaded
    s().flush();
    expect(s().rows.filter((r) => r.seq === 8)).toHaveLength(1);
  });

  it('keeps at most 500 rows', () => {
    for (let i = 1; i <= MAX_ROWS + 30; i++) s().enqueue(entryOf(ev(i), 'event'));
    for (let k = 0; k < 50; k++) s().flush();
    expect(s().rows).toHaveLength(MAX_ROWS);
    expect(s().ids.size).toBe(MAX_ROWS);
  });

  it('queues while paused and suspends animation during toasts', () => {
    s().setPaused(true);
    s().enqueue(entryOf(ev(1), 'event'));
    s().flush();
    expect(s().rows).toHaveLength(0);
    s().setPaused(false);
    s().suspendAnimation(400);
    s().flush();
    expect(s().rows).toHaveLength(1);
    expect(s().fresh.size).toBe(0);
    s().enqueue(entryOf(ev(2), 'event'));
    s().flush(Date.now() + 1000);
    expect([...s().fresh]).toEqual(['e-2']);
  });

  it('replaces a quarantine row when its record is replayed into an event', () => {
    const q: EventQuarantined = { raw_id: 'r-9', seq: 9, time: 9000, group_id: 'qg-1', reason: 'no_fingerprint', preview: 'EDGE|' };
    s().enqueue(entryOf(q, 'quarantine'));
    s().flush();
    s().enqueue(entryOf(ev(9, 'r-9'), 'event'));
    s().flush();
    expect(s().rows.map((r) => r.kind)).toEqual(['event']);
  });
});
