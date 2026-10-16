import type { EventSummary, IncidentStage } from '@/lib/types';

export const REPLAY_LIMIT = 500;
export const SEQUENCE_PAGE_SIZE = 12;

/** Keep source timestamps and stable ordering. A replay never manufactures events. */
export function prepareReplay(events: EventSummary[], limit = REPLAY_LIMIT) {
  const usable = events.filter((e) => Number.isFinite(e.time) && Math.abs(e.time) <= 8.64e15);
  const ordered = [...usable].sort((a, b) => a.time - b.time || a.seq - b.seq || a.event_id.localeCompare(b.event_id));
  const cap = Math.max(0, Math.floor(limit));
  return { events: ordered.slice(0, cap), invalid: events.length - usable.length, omitted: Math.max(0, ordered.length - cap) };
}

export function eventSignal(event: EventSummary) {
  if (event.status === 'Failure' || event.action === 'Denied') return { label: 'Rejected', tone: 'rejected' } as const;
  if (event.class_uid === 2004) return { label: 'Detection', tone: 'detection' } as const;
  if (event.status === 'Success' || event.action === 'Allowed') return { label: 'Accepted', tone: 'accepted' } as const;
  return { label: 'Observed', tone: 'observed' } as const;
}

export function eventStage(event: EventSummary, stages: IncidentStage[]) {
  return stages.find((stage) => stage.event_ids.includes(event.event_id));
}

export const sourceKey = (event: EventSummary) => event.src_ip || 'Source not recorded';
export const deviceKey = (event: EventSummary) => event.device || 'Device not recorded';

/** Bound graph density, but always include both endpoints of the selected event. */
export function replayGraph(events: EventSummary[], selected: EventSummary, cap = 3) {
  const bounded = (keys: string[], active: string) => {
    const all = [...new Set(keys)];
    const shown = all.slice(0, Math.max(1, cap));
    if (!shown.includes(active)) shown[shown.length - 1] = active;
    return { all, shown };
  };
  const sources = bounded(events.map(sourceKey), sourceKey(selected));
  const devices = bounded(events.map(deviceKey), deviceKey(selected));
  const links = new Map<string, { source: string; device: string; count: number; index: number }>();
  events.forEach((e, index) => {
    const source = sourceKey(e), device = deviceKey(e);
    if (!sources.shown.includes(source) || !devices.shown.includes(device)) return;
    const key = JSON.stringify([source, device]);
    const existing = links.get(key);
    if (existing) existing.count += 1;
    else links.set(key, { source, device, count: 1, index });
  });
  return { sources, devices, links: [...links.values()] };
}

export function sequencePage(index: number, total: number) {
  const start = Math.floor(Math.max(0, index) / SEQUENCE_PAGE_SIZE) * SEQUENCE_PAGE_SIZE;
  return { start, end: Math.min(total, start + SEQUENCE_PAGE_SIZE) };
}
