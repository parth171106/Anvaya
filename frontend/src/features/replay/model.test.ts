import { describe, expect, it } from 'vitest';
import type { EventSummary, IncidentStage } from '@/lib/types';
import { eventSignal, eventStage, prepareReplay, replayGraph, sequencePage } from './model';

const event = (id: string, time = 1, seq = 1, fields: Partial<EventSummary> = {}) => ({
  event_id: id, time, seq, src_ip: '192.0.2.1', device: 'server', ...fields,
} as EventSummary);

describe('stored-event replay', () => {
  it('orders by original time, sequence, then identifier without mutating input', () => {
    const input = [event('b', 20, 2), event('d', 10, 3), event('a', 20, 2), event('c', 10, 2)];
    expect(prepareReplay(input).events.map((e) => e.event_id)).toEqual(['c', 'd', 'a', 'b']);
    expect(input[0].event_id).toBe('b');
  });
  it('counts invalid timestamps separately from capped chronological events', () => {
    const result = prepareReplay([event('a', NaN), event('b', Infinity), event('c', 1e17), event('d', 10), event('e', 20)], 1);
    expect(result.events.map((e) => e.event_id)).toEqual(['d']);
    expect(result.invalid).toBe(3);
    expect(result.omitted).toBe(1);
  });
  it('keeps failures separate from successful access and neutral records', () => {
    expect(eventSignal(event('a', 1, 1, { status: 'Failure' })).label).toBe('Rejected');
    expect(eventSignal(event('a', 1, 1, { action: 'Allowed' })).label).toBe('Accepted');
    expect(eventSignal(event('a', 1, 1, { class_uid: 2004 })).label).toBe('Detection');
    expect(eventSignal(event('a')).label).toBe('Observed');
  });
  it('only draws recorded relationships and keeps selected endpoints in a bounded graph', () => {
    const events = Array.from({ length: 8 }, (_, i) => event(String(i), i, i, { src_ip: `source-${i}`, device: `device-${i}` }));
    const graph = replayGraph(events, events[7]);
    expect(graph.sources.shown).toEqual(['source-0', 'source-1', 'source-7']);
    expect(graph.devices.shown).toEqual(['device-0', 'device-1', 'device-7']);
    expect(graph.links).toHaveLength(3);
    expect(graph.links.some((link) => link.source === 'source-0' && link.device === 'device-1')).toBe(false);
  });
  it('does not invent missing endpoint addresses', () => {
    const e = event('a', 1, 1, { src_ip: null, device: '' });
    expect(replayGraph([e], e).sources.shown).toEqual(['Source not recorded']);
    expect(replayGraph([e], e).devices.shown).toEqual(['Device not recorded']);
  });
  it('pages the sequence at the selected event including the final partial page', () => {
    expect(sequencePage(12, 25)).toEqual({ start: 12, end: 24 });
    expect(sequencePage(24, 25)).toEqual({ start: 24, end: 25 });
  });
  it('uses explicit stage evidence membership instead of inferring from event wording', () => {
    const stages = [{ stage: 'credential', label: 'Credential attempts', event_ids: ['a'] }] as IncidentStage[];
    expect(eventStage(event('a'), stages)?.stage).toBe('credential');
    expect(eventStage(event('b', 1, 1, { title: 'Credential attempts' }), stages)).toBeUndefined();
  });
  it('handles empty and single-event replays without extra records', () => {
    expect(prepareReplay([]).events).toEqual([]);
    const e = event('only');
    expect(prepareReplay([e]).events).toEqual([e]);
    expect(replayGraph([e], e).links).toEqual([{ source: '192.0.2.1', device: 'server', count: 1, index: 0 }]);
    expect(sequencePage(0, 1)).toEqual({ start: 0, end: 1 });
  });
});
