import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Activity, Pause, Play } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { ConfidencePill, DeviceChip, FormatChip, SeverityBadge, SilenceBadge } from '@/components/badges/badges';
import { Bone, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { api } from '@/lib/api';
import { DASH, formatEventSummary, formatSrcDst, int, timeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import { deviceColor } from '@/lib/tokens';
import type { DeviceId, SourceInfo } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useFeedStore, useSourcesStore, useStatsStore, useStreamStore } from '@/state';
import { entryOf, type FeedEntry } from '@/state/feed';

const ROW_H = 48;
// The brief's widths at 1920 (120/150/160/≥360/360/110/80 px); they shrink to fit a 1280 px window without scrolling.
const COLS = 'grid grid-cols-[minmax(96px,120px)_minmax(110px,150px)_minmax(140px,160px)_minmax(200px,1fr)_minmax(250px,360px)_minmax(90px,110px)_minmax(56px,80px)] items-center gap-3 px-4';

const FeedRow = memo(function FeedRow({ r, isNew, onSelect }: { r: FeedEntry; isNew: boolean; onSelect: (id: string) => void }) {
  const isEvent = r.kind === 'event';
  const e = isEvent ? r.e : null;
  const device = e?.device ?? null;
  const open = () => isEvent && onSelect(r.id);
  return (
    <div role="row" tabIndex={isEvent ? 0 : -1} aria-label={isEvent ? `Open event ${r.id}` : 'Record held in quarantine'}
      onClick={open} onKeyDown={(ev) => { if (ev.key === 'Enter') open(); }}
      className={cn('relative h-12 border-b border-rule text-body', COLS, isEvent && 'cursor-pointer hover:bg-paper-sunk',
        isNew && 'feed-row-new')}>
      <span aria-hidden className="feed-rule absolute inset-y-0 left-0 w-1"
        style={{ background: device ? deviceColor(device) : 'var(--fmt-unknown)' }} />
      <span role="cell" className="font-mono text-mono">{timeIST(r.time)}</span>
      <span role="cell">{device ? <DeviceChip device={device} product={false} /> : DASH}</span>
      <span role="cell"><FormatChip format={e?.format ?? 'unknown'} /></span>
      <span role="cell" className="truncate">{e ? formatEventSummary(e) : 'Held in quarantine · no matching parser'}</span>
      <span role="cell" className="truncate font-mono text-mono">{e ? formatSrcDst(e) : r.kind === 'quarantine' ? r.q.preview.slice(0, 44) : DASH}</span>
      <span role="cell">
        {e?.class_uid === 2004 ? <SeverityBadge severity={e.severity} /> : e?.class_uid === 4001 ? (e.action ?? DASH) : DASH}
      </span>
      <span role="cell">{e ? <ConfidencePill value={e.parse_confidence} /> : null}</span>
    </div>
  );
});

function LiveFeedTable({ rows, fresh, onSelect }: { rows: FeedEntry[]; fresh: Set<string>; onSelect: (id: string) => void }) {
  const scroller = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => scroller.current, estimateSize: () => ROW_H,
    overscan: 12, getItemKey: (i) => rows[i].id });
  return (
    <div role="table" aria-label="Live feed" aria-live="off" className="rounded-panel border border-rule bg-surface">
      <div role="row" className={cn(COLS, 'h-11 border-b border-rule text-label font-medium text-graphite')}>
        <span role="columnheader">Time IST</span><span role="columnheader">Device</span>
        <span role="columnheader">Format</span><span role="columnheader">Event</span>
        <span role="columnheader">Source → Destination</span><span role="columnheader">Action</span>
        <Tooltip>
          <TooltipTrigger asChild><span role="columnheader" tabIndex={0}>Conf.</span></TooltipTrigger>
          <TooltipContent>Parse confidence (0–100)</TooltipContent>
        </Tooltip>
      </div>
      <div ref={scroller} className="h-[calc(100vh-330px)] min-h-[420px] overflow-y-auto" role="rowgroup">
        <div style={{ height: v.getTotalSize(), position: 'relative' }}>
          {v.getVirtualItems().map((it) => (
            <div key={it.key} style={{ position: 'absolute', top: 0, left: 0, right: 0, transform: `translateY(${it.start}px)` }}>
              <FeedRow r={rows[it.index]} isNew={fresh.has(rows[it.index].id)} onSelect={onSelect} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DeviceFilterChips({ sources, selected, onToggle }: { sources: SourceInfo[]; selected: DeviceId | null; onToggle: (d: DeviceId) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by device">
      {sources.map((s) => (
        <span key={s.device} className="inline-flex items-center gap-2">
          <button type="button" aria-pressed={selected === s.device} onClick={() => onToggle(s.device)}
            className={cn('inline-flex h-10 items-center gap-2 rounded-pill border px-3 transition-colors duration-fast',
              selected === s.device ? 'border-ink bg-paper-sunk' : 'border-rule bg-surface hover:border-ink')}>
            <DeviceChip device={s.device} />
          </button>
          {s.status === 'silent' && <SilenceBadge seconds={s.silent_for_s} />}
        </span>
      ))}
    </div>
  );
}

/** One polite announcement every 10 s instead of a live table (UI_UX_BRIEF.md §11). */
function NewEventsAnnouncer() {
  const [msg, setMsg] = useState('');
  const last = useRef(useFeedStore.getState().ids.size);
  useEffect(() => {
    const t = setInterval(() => {
      const n = useFeedStore.getState().ids.size;
      setMsg(n > last.current ? `${n - last.current} new events` : '');
      last.current = n;
    }, 10_000);
    return () => clearInterval(t);
  }, []);
  return <div aria-live="polite" className="sr-only">{msg}</div>;
}

export default function Feed() {
  const navigate = useNavigate();
  const { rows, fresh, paused, pending, setPaused, hydrate } = useFeedStore();
  const stats = useStatsStore((s) => s.stats);
  const sources = Object.values(useSourcesStore((s) => s.byDevice)).sort((a, b) => a.device.localeCompare(b.device));
  const stream = useStreamStore((s) => s.status);
  const [filter, setFilter] = useState<DeviceId | null>(null);
  const initial = useQuery({ queryKey: qk.events({ limit: 50 }), queryFn: () => api.events.list({ limit: 50 }) });
  const sourcesQ = useQuery({ queryKey: qk.sources, queryFn: api.sources, refetchInterval: 3000 });
  useEffect(() => { if (sourcesQ.data) useSourcesStore.getState().setAll(sourcesQ.data.items); }, [sourcesQ.data]);
  useEffect(() => {
    if (initial.data) hydrate(initial.data.items.map((e) => entryOf(e, 'event')));
  }, [initial.data, hydrate]);
  const [offlineLong, setOfflineLong] = useState(false);
  useEffect(() => {
    if (stream === 'live' || stream === 'connecting') { setOfflineLong(false); return; }
    const t = setTimeout(() => setOfflineLong(true), 3000);
    return () => clearTimeout(t);
  }, [stream]);

  const shown = useMemo(() => (filter ? rows.filter((r) => r.kind === 'event' && r.e.device === filter) : rows), [rows, filter]);
  const subtitle = `${int(stats?.normalized_total ?? 0)} events · ${int(stats?.sources_total ?? 0)} sources · ${int(stats?.formats_detected ?? 0)} formats`;

  return (
    <div>
      <PageHeader title="Live feed" subtitle={subtitle}>
        <DeviceFilterChips sources={sources} selected={filter} onToggle={(d) => setFilter((f) => (f === d ? null : d))} />
        {paused && pending.length > 0 ? (
          <Button onClick={() => setPaused(false)}><Play className="size-4" aria-hidden />{pending.length} new events</Button>
        ) : (
          <Button variant="outline" onClick={() => setPaused(!paused)}>
            {paused ? <Play className="size-4" aria-hidden /> : <Pause className="size-4" aria-hidden />}
            {paused ? 'Resume feed' : 'Pause feed'}
          </Button>
        )}
      </PageHeader>
      <NewEventsAnnouncer />
      {offlineLong && (
        <ErrorState className="mb-4" title="The live stream is disconnected. Reconnecting automatically…"
          onRetry={() => window.location.reload()} retryLabel="Retry now" />
      )}
      {rows.length === 0 && initial.isPending ? (
        <Skeleton><div className="space-y-2">{Array.from({ length: 10 }, (_, i) => <Bone key={i} className="h-12" />)}</div></Skeleton>
      ) : rows.length === 0 ? (
        <div className="rounded-panel border border-rule bg-surface">
          <EmptyState icon={Activity} title="Waiting for the first log"
            body="Start the attack simulation on Overview, or send syslog to UDP port 5514."
            action={<Button asChild variant="outline"><Link to="/overview">Go to Overview</Link></Button>} />
        </div>
      ) : (
        <LiveFeedTable rows={shown} fresh={fresh} onSelect={(id) => navigate(`/events/${id}`)} />
      )}
    </div>
  );
}
