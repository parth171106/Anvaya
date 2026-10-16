import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ExternalLink, Network, Pause, Play, RefreshCw, RotateCcw, SkipBack, SkipForward } from 'lucide-react';
import { Link, useSearchParams } from 'react-router';
import { Bone, EmptyState, ErrorState, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { qk } from '@/lib/queryKeys';
import { int, timeIST } from '@/lib/format';
import type { EventSummary, IncidentDetail } from '@/lib/types';
import { useDemoStore } from '@/state/demo';
import { deviceKey, eventSignal, eventStage, prepareReplay, replayGraph, sequencePage, sourceKey } from './model';
import './replay.css';

const timestamp = (value: number) => new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
}).format(value) + ' IST';
const yPosition = (index: number, total: number) => total === 1 ? 50 : 24 + index * (52 / (total - 1));

function SignalMap({ events, current, playing, speed, onSelect }: {
  events: EventSummary[]; current: EventSummary; playing: boolean; speed: number; onSelect: (index: number) => void;
}) {
  const graph = useMemo(() => replayGraph(events, current), [events, current]);
  const signal = eventSignal(current);
  return <div className="replay-map-wrap">
    <div className="replay-map-labels"><span>Source addresses</span><span>Reporting devices</span></div>
    <div className={`replay-map replay-tone-${signal.tone}`}>
      <svg className="replay-connections" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {graph.links.map((link) => {
          const y1 = yPosition(graph.sources.shown.indexOf(link.source), graph.sources.shown.length);
          const y2 = yPosition(graph.devices.shown.indexOf(link.device), graph.devices.shown.length);
          const path = `M 32 ${y1} C 48 ${y1}, 52 ${y2}, 68 ${y2}`;
          const active = link.source === sourceKey(current) && link.device === deviceKey(current);
          return <g key={JSON.stringify([link.source, link.device])}>
            <path d={path} className={active ? 'replay-path active' : 'replay-path'} vectorEffect="non-scaling-stroke" />
            {active && playing && <path key={current.event_id} d={path} pathLength="1" className="replay-packet" style={{ animationDuration: `${1000 / speed}ms` }} vectorEffect="non-scaling-stroke" />}
            <path d={path} className="replay-path-target" vectorEffect="non-scaling-stroke" onClick={() => onSelect(link.index)}><title>{link.source} to {link.device}: select first recorded event</title></path>
          </g>;
        })}
      </svg>
      {(['source', 'device'] as const).map((side) => {
        const nodes = side === 'source' ? graph.sources : graph.devices;
        const keyFor = side === 'source' ? sourceKey : deviceKey;
        return nodes.shown.map((name, index) => <button key={`${side}-${name}`} type="button"
          className={`replay-node replay-node-${side}${keyFor(current) === name ? ' selected' : ''}`}
          style={{ top: `${yPosition(index, nodes.shown.length)}%` }}
          onClick={() => onSelect(events.findIndex((e) => keyFor(e) === name))}
          aria-label={`Select first event ${side === 'source' ? 'from' : 'reported by'} ${name}`}>
          <span className="replay-node-symbol" aria-hidden="true">{side === 'source' ? <Network size={19} /> : <span className="replay-device-symbol" />}</span>
          <span className="replay-node-name" title={name}>{name}</span>
          <span className="replay-node-count">{int(events.filter((e) => keyFor(e) === name).length)} events</span>
        </button>);
      })}
      <div className="replay-map-caption"><span className="replay-signal-dot" />{signal.label} <ArrowRight size={13} aria-hidden="true" /> recorded by device</div>
    </div>
    <p className="replay-map-note">Map and node counts cover the full replay snapshot; the highlighted signal is the selected event. Log relationships, not physical network topology.
      {(graph.sources.all.length > graph.sources.shown.length || graph.devices.all.length > graph.devices.shown.length) &&
        ` Showing ${graph.sources.shown.length}/${graph.sources.all.length} sources and ${graph.devices.shown.length}/${graph.devices.all.length} devices; selected endpoints always visible.`}
    </p>
    <details className="replay-relationship-list"><summary>Inspect visible connections ({graph.links.length})</summary><div>{graph.links.map((link) => <button type="button" key={JSON.stringify([link.source, link.device])} onClick={() => onSelect(link.index)}><span>{link.source} → {link.device}</span><span>{link.count} events · first evidence</span></button>)}</div></details>
  </div>;
}

function ReplayPlayer({ incident: initial }: { incident: IncidentDetail }) {
  // Freeze the authenticated response: streaming cache updates must never shift an active replay.
  const [incident] = useState(initial);
  const prepared = useMemo(() => prepareReplay(incident.events), [incident]);
  const events = prepared.events;
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const stageRef = useRef<HTMLDivElement>(null);
  const demoMode = useDemoStore((state) => state.demoMode);
  const current = events[index];
  const select = (next: number) => { setPlaying(false); setIndex(Math.max(0, Math.min(events.length - 1, next))); };

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(() => {
      if (index >= events.length - 1) setPlaying(false);
      else { setIndex(index + 1); if (index + 1 === events.length - 1) setPlaying(false); }
    }, 1000 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, index, events.length, speed]);

  useEffect(() => {
    const pauseWhenHidden = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', pauseWhenHidden);
    const observer = new IntersectionObserver(([entry]) => { if (!entry.isIntersecting) setPlaying(false); });
    if (stageRef.current) observer.observe(stageRef.current);
    return () => { document.removeEventListener('visibilitychange', pauseWhenHidden); observer.disconnect(); };
  }, []);

  if (!current) return <EmptyState icon={Network} title="No replayable events" body="This incident has no linked events with usable original timestamps. Open the incident to inspect its available evidence." />;

  const signal = eventSignal(current);
  const stage = eventStage(current, incident.stages_detail);
  const page = sequencePage(index, events.length);
  const labelledSynthetic = incident.events.some((event) => event.device.startsWith('synthetic-lab-'));
  return <div className="replay-console">
    <div className="replay-case-heading">
      <div className="replay-eyebrow"><span className="replay-mode">Recorded replay · not live</span>
        {incident.workflow?.controlled_test && <span className="replay-provenance">Controlled test · analyst label</span>}
        {demoMode && <span className="replay-provenance">Demo environment</span>}
        {labelledSynthetic && <span className="replay-provenance">Contains synthetic-labelled sources</span>}
      </div>
      <h2>{incident.title}</h2>
      <p>A finding to investigate, not proof of a successful intrusion.</p>
    </div>
    <dl className="replay-metrics">
      <div><dt>Review priority</dt><dd>{incident.level}<span>{incident.risk}/100</span></dd></div>
      <div><dt>Linked evidence</dt><dd>{int(incident.event_count)}<span>events</span></dd></div>
      <div><dt>Reporting devices</dt><dd>{new Set(events.map(deviceKey)).size}<span>in replay</span></dd></div>
      <div><dt>Original time window</dt><dd className="replay-time-window">{timeIST(events[0].time)} — {timeIST(events[events.length - 1].time)}<span>IST · {new Date(events[0].time).toLocaleDateString('en-GB', { timeZone: 'Asia/Kolkata' })}</span></dd></div>
    </dl>
    {(prepared.invalid > 0 || prepared.omitted > 0 || incident.event_count !== incident.events.length) && <p className="replay-limit-notice">
      Replay includes {events.length} of {incident.event_count} linked events.
      {prepared.omitted > 0 && ` Showing the earliest ${events.length}; ${prepared.omitted} later records exceed the replay limit.`}
      {prepared.invalid > 0 && ` ${prepared.invalid} records have unusable timestamps.`}
      {incident.event_count !== incident.events.length && ` The server returned ${incident.events.length} records.`}
    </p>}
    <div className="replay-stage" ref={stageRef}>
      <section className="replay-visual" aria-label="Recorded event relationships">
        <div className="replay-stage-top"><span className="replay-eyebrow">Signal map</span><span className="replay-counter">{String(index + 1).padStart(3, '0')}<span> / {String(events.length).padStart(3, '0')}</span></span></div>
        <SignalMap events={events} current={current} playing={playing} speed={speed} onSelect={select} />
      </section>
      <aside className={`replay-inspector replay-tone-${signal.tone}`} aria-label="Selected event evidence">
        <div className="replay-inspector-heading"><span className="replay-eyebrow">Selected evidence</span><span className="replay-signal-label">{signal.label}</span></div>
        <h3>{current.title || current.activity_name || current.class_name || 'Recorded event'}</h3>
        <p className="replay-original-time">{timestamp(current.time)}</p>
        <dl className="replay-fields">
          <div><dt>Finding stage</dt><dd>{stage?.label || 'Not assigned'}</dd></div>
          <div><dt>Source</dt><dd>{current.src_ip || 'Not recorded'}{current.src_port != null && <span> port {current.src_port}</span>}</dd></div>
          <div><dt>Destination</dt><dd>{current.dst_ip || 'Not recorded'}{current.dst_port != null && <span> port {current.dst_port}</span>}</dd></div>
          <div><dt>Reported by</dt><dd>{deviceKey(current)}</dd></div>
          {current.user_name && <div><dt>User</dt><dd>{current.user_name}</dd></div>}
          <div><dt>Record</dt><dd>{current.event_id}</dd></div>
        </dl>
        <Link to={`/events/${encodeURIComponent(current.event_id)}`} className="replay-evidence-link">Inspect raw evidence <ExternalLink size={16} aria-hidden="true" /></Link>
        <p className="replay-proof-note">Open the record to inspect its bytes and verify its proof. Replay does not run an integrity check.</p>
      </aside>
    </div>
    <section className="replay-transport" aria-label="Playback controls">
      <div className="replay-control-row">
        <Button onClick={() => { if (index === events.length - 1) setIndex(0); setPlaying(!playing); }} disabled={events.length < 2} className="replay-play">
          {playing ? <Pause size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}{playing ? 'Pause' : index === events.length - 1 ? 'Play again' : 'Play replay'}
        </Button>
        <div className="replay-step-buttons">
          <Button variant="outline" size="icon" onClick={() => select(0)} aria-label="Restart replay"><RotateCcw size={17} /></Button>
          <Button variant="outline" size="icon" onClick={() => select(index - 1)} disabled={index === 0} aria-label="Previous event"><SkipBack size={17} /></Button>
          <Button variant="outline" size="icon" onClick={() => select(index + 1)} disabled={index === events.length - 1} aria-label="Next event"><SkipForward size={17} /></Button>
        </div>
        <label className="replay-speed">Speed<select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>{[0.5, 1, 2, 4].map((value) => <option key={value} value={value}>{value}×</option>)}</select></label>
        <span className="replay-playback-state" role="status">{playing ? 'Playing' : index === events.length - 1 ? 'Replay complete' : 'Paused'} · {index + 1} of {events.length}</span>
      </div>
      <label className="replay-scrubber-label" htmlFor="replay-position">Event position <span>Event-step playback · 1 event/second at 1×; original gaps compressed</span></label>
      <input id="replay-position" className="replay-scrubber" type="range" min="0" max={Math.max(0, events.length - 1)} value={index} onChange={(e) => select(Number(e.target.value))} aria-valuetext={`Event ${index + 1} of ${events.length}, ${timestamp(current.time)}`} disabled={events.length < 2} />
      <div className="replay-range-times"><span>{timestamp(events[0].time)}</span><span>{timestamp(events[events.length - 1].time)}</span></div>
    </section>
    <section className="replay-sequence" aria-label="Event sequence">
      <div className="replay-sequence-heading"><h3>Evidence sequence</h3><span>{page.start + 1}–{page.end} of {events.length}</span></div>
      <div className="replay-stages">{incident.stages_detail.map((item) => {
        const first = events.findIndex((event) => item.event_ids.includes(event.event_id));
        return <button key={item.stage} type="button" disabled={first < 0} onClick={() => select(first)} aria-pressed={stage?.stage === item.stage}><span>{item.label}</span><span>{int(item.event_count)} events</span></button>;
      })}</div>
      <ol start={page.start + 1} className="replay-sequence-list">{events.slice(page.start, page.end).map((event, offset) => {
        const signal = eventSignal(event), eventIndex = page.start + offset;
        return <li key={event.event_id}><button type="button" onClick={() => select(eventIndex)} aria-current={eventIndex === index ? 'step' : undefined} className={`replay-sequence-event replay-tone-${signal.tone}`}>
          <span className="replay-sequence-index">{String(eventIndex + 1).padStart(3, '0')}</span><span className="replay-sequence-time">{timeIST(event.time)}</span>
          <span className="replay-sequence-description">{event.title || event.activity_name || event.class_name || 'Recorded event'}<span>{event.device} · {event.event_id}</span></span>
          <span className="replay-sequence-signal">{signal.label}</span>
        </button></li>;
      })}</ol>
      <div className="replay-sequence-footer"><Button variant="outline" disabled={page.start === 0} onClick={() => select(page.start - 12)}>Previous 12</Button><Button variant="outline" disabled={page.end === events.length} onClick={() => select(page.end)}>Next 12</Button></div>
    </section>
    <p className="replay-disclosure">Snapshot of stored events. Reload to include new evidence. {labelledSynthetic ? 'Synthetic labels come from reporting-device names; they are not independent verification.' : 'Source provenance is not independently verified.'} {incident.workflow?.controlled_test && 'The controlled-test label was set by an analyst.'}</p>
  </div>;
}

export default function AttackReplay() {
  const [params, setParams] = useSearchParams();
  const [revision, setRevision] = useState(0);
  const list = useQuery({ queryKey: qk.incidents, queryFn: api.incidents.list });
  const selectedId = params.get('incident') || list.data?.items[0]?.incident_id || '';
  const detail = useQuery({ queryKey: qk.incident(selectedId), queryFn: () => api.incidents.get(selectedId), enabled: !!selectedId, retry: 0 });

  return <div className="attack-replay">
    <header className="replay-page-heading"><div><p className="replay-eyebrow">Investigation / playback</p><h1>Attack Replay</h1><p>Follow the signals. Inspect the evidence. Reconstruct the sequence.</p></div><span className="replay-readonly"><Network size={16} aria-hidden="true" /> Evidence-driven · read only</span></header>
    {list.isPending ? <Skeleton><Bone className="h-16 mb-4" /><Bone className="h-[480px]" /></Skeleton> : list.isError ? <ErrorState title="Couldn't load incidents for replay." onRetry={() => list.refetch()} /> : <>
      <div className="replay-picker"><label htmlFor="replay-incident">Choose incident</label><select id="replay-incident" value={selectedId} onChange={(e) => setParams({ incident: e.target.value })}>
        {selectedId && !list.data.items.some((item) => item.incident_id === selectedId) && <option value={selectedId}>{selectedId}</option>}
        {list.data.items.map((item) => <option key={item.incident_id} value={item.incident_id}>{item.incident_id} · {item.title}</option>)}
      </select>{selectedId && <Link to={`/incidents/${encodeURIComponent(selectedId)}`}>Open incident <ArrowRight size={16} aria-hidden="true" /></Link>}
        {selectedId && <Button variant="outline" aria-label="Reload replay evidence" disabled={detail.isFetching} onClick={async () => { const result = await detail.refetch(); if (result.isSuccess) setRevision((value) => value + 1); }}><RefreshCw size={16} aria-hidden="true" /><span>Reload</span></Button>}
      </div>
      {!selectedId ? <EmptyState icon={Network} title="Your first replay starts with a finding" body="When ANVAYA links events into an incident, select it here to follow its recorded sequence. No events are generated by this page." action={<Button asChild><Link to="/sources">View log sources</Link></Button>} />
        : detail.isPending ? <Skeleton><Bone className="h-[480px]" /></Skeleton>
          : detail.isError ? <ErrorState title="Couldn't load this incident." body="It may no longer exist or may not belong to this workspace. Choose another incident or retry." onRetry={() => detail.refetch()} />
            : <ReplayPlayer key={`${selectedId}:${revision}`} incident={detail.data} />}
    </>}
  </div>;
}
