import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Play } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router';
import { DeviceChip, DeviceDot } from '@/components/badges/badges';
import { Bone, ErrorState, Skeleton } from '@/components/common/states';
import { api, ApiError } from '@/lib/api';
import { formatEventSummary, hhmmIST, int, plural, timeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { EventSummary, IncidentDetail as Detail, IncidentStage } from '@/lib/types';
import { cn } from '@/lib/utils';
import { IncidentHeaderLine } from './IncidentList';
import { AIExplanation } from '@/features/search/AIExplanation';
import Investigation from './Investigation';
import IncidentReport from './IncidentReport';
import SSHResponse from './SSHResponse';

const CHIPS_SHOWN = 2;

function RiskBreakdown({ d }: { d: Detail }) {
  const b = d.risk_breakdown;
  if (d.ssh_finding) return <p className="mt-2 text-body text-graphite">SSH rule priority: {d.level} ({d.risk}/100). {d.stages.includes('access') ? 'A successful login followed the failure threshold on an affected device; confirm whether it was authorized.' : 'Repeated distinct failed connections require review.'} This is not a breach probability.</p>;
  if (d.stages.length === 1 && d.stages[0] === 'credential') return <p className="mt-2 text-body text-graphite">Rule severity: Medium (40/100). This score is a review priority, not the probability of a breach.</p>;
  return (
    <p className="mt-2 text-body text-graphite">
      Risk breakdown: {d.stages.length} stages +{b.stages} · {d.devices.length} devices +{b.devices} · in attack order +{b.ordered}
    </p>
  );
}

function EvidenceChip({ e, onOpen }: { e: EventSummary; onOpen: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(e.event_id)}
      className="inline-flex min-w-0 min-h-10 max-w-full sm:max-w-[420px] items-center gap-2 rounded-chip border border-rule bg-surface px-2.5 text-label hover:border-ink">
      <span className="shrink-0 whitespace-nowrap font-mono">{timeIST(e.time)}</span>
      <DeviceDot device={e.device} />
      <span className="min-w-0 max-w-[100px] truncate font-mono" title={e.device}>{e.device}</span>
      <span className="min-w-0 truncate text-graphite">{formatEventSummary(e)}{e.class_uid === 4001 && e.dst_port != null && e.action === 'Denied' ? ` :${e.dst_port}` : ''}</span>
    </button>
  );
}

function StageGroup({ stage, isLast, events, onOpenEvent }: {
  stage: IncidentStage; isLast: boolean; events: EventSummary[]; onOpenEvent: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? events : events.slice(0, CHIPS_SHOWN);
  return (
    <li className="relative grid grid-cols-1 gap-2 pb-6 sm:grid-cols-[72px_minmax(0,1fr)] sm:gap-4">
      {!isLast && <span aria-hidden className="absolute top-9 bottom-0 left-[5.5px] sm:top-6 sm:left-[93.5px] w-px bg-rule" />}
      <span className="pt-0.5 font-mono text-mono text-graphite">{hhmmIST(stage.first_time)}</span>
      <div className="relative min-w-0 pl-6">
        <span aria-hidden className={cn('absolute top-1.5 left-0 size-3 rounded-pill border-2 border-ink', isLast ? 'bg-ink' : 'bg-surface')} />
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <h3 className="text-h3 font-semibold">{stage.label}</h3>
          <span className="flex min-w-0 max-w-full flex-wrap items-center gap-4">
            {stage.devices.map((d) => <DeviceChip key={d} device={d} product={false} />)}
            <span className="w-24 text-right text-body text-graphite tabular">{plural(stage.event_count, 'event')}</span>
          </span>
        </div>
        <p className="mt-1 text-body-lg">{stage.headline}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {shown.map((e) => <EvidenceChip key={e.event_id} e={e} onOpen={onOpenEvent} />)}
          {events.length > CHIPS_SHOWN && (
            <button type="button" onClick={() => setExpanded((x) => !x)} aria-expanded={expanded}
              className="h-10 rounded-chip px-2 text-label font-medium text-seal hover:underline">
              {expanded ? 'Show fewer' : `+${events.length - CHIPS_SHOWN}`}
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export default function IncidentDetail() {
  const { incidentId = '' } = useParams();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: qk.incident(incidentId), queryFn: () => api.incidents.get(incidentId), retry: 0 });

  if (q.isPending) return <Skeleton><Bone className="mb-4 h-24" /><Bone className="h-[420px]" /></Skeleton>;
  if (q.isError) {
    return q.error instanceof ApiError && q.error.status === 404
      ? <ErrorState title="This incident isn't in the store." body="It may have been cleared by a demo reset." onRetry={() => navigate('/incidents')} retryLabel="Back to Incidents" />
      : <ErrorState title="Couldn't load incidents." onRetry={() => q.refetch()} />;
  }
  const d = q.data;
  const byId = new Map(d.events.map((e) => [e.event_id, e]));
  return (
    <div>
      <Link to="/incidents" className="inline-flex h-10 items-center gap-2 text-body font-medium text-seal hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Incidents
      </Link>
      <h1 className="mt-1 mb-3 font-display text-h1 font-semibold">{d.title}</h1>
      <IncidentHeaderLine i={d} />
      <RiskBreakdown d={d} />
      <Link to={`/replay?incident=${encodeURIComponent(incidentId)}`} className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-control border border-rule bg-surface px-4 text-body font-medium text-seal hover:bg-paper-sunk"><Play className="size-4" aria-hidden /> Replay incident</Link>
      <Investigation key={incidentId} incident={d} />
      <IncidentReport key={`report-${incidentId}`} incidentId={incidentId} />
      {d.ssh_finding && <SSHResponse key={`response-${incidentId}`} incident={d} />}
      {d.ssh_finding && <section className="mt-4 min-w-0 rounded-panel border border-rule bg-surface p-5">
        <h2 className="text-h3 font-semibold">SSH investigation</h2>
        <p className="mt-2 text-body text-graphite">Check whether you recognize the source IP and user accounts. Confirm successful logins with the server owner before taking action. Shared networks and legitimate retries can resemble attacks. This view does not confirm any firewall action.</p>
        <p className="mt-2 text-body">Related successful logins from the same IP on affected devices: {d.ssh_context?.length ?? 0} of {d.ssh_context_total ?? 0} shown. Window: 10 minutes before the first failure to 15 minutes after the last failure.</p>
        <div className="mt-3 flex flex-wrap gap-2">{d.ssh_context?.map(e => <EvidenceChip key={e.event_id} e={e} onOpen={id => navigate(`/events/${id}`)} />)}</div>
        {!d.ssh_context?.length && <p className="mt-2 text-label text-graphite">No matching successful login is stored in this window. This does not rule out missing logs or other access methods.</p>}
        <Link className="mt-3 inline-block text-body font-medium text-seal underline" to="/alerts">Open alert inbox and Telegram settings</Link>
      </section>}
      {d.explanation && <section className="mt-4 space-y-2 rounded-panel border border-rule bg-surface p-5">
        <h2 className="text-h3 font-semibold">Why this needs attention</h2>
        <p className="text-body">{d.explanation}</p>
        <p className="text-body text-graphite">{d.recommended_action}</p>
      </section>}
      <AIExplanation key={incidentId} kind="incident" target={incidentId} />
      <ol className="mt-6 rounded-panel border border-rule bg-surface p-4 sm:p-6" aria-label="Incident timeline">
        {d.stages_detail.map((s, i) => (
          <StageGroup key={s.stage} stage={s} isLast={i === d.stages_detail.length - 1} onOpenEvent={(id) => navigate(`/events/${id}`)}
            events={s.event_ids.map((id) => byId.get(id)).filter((x): x is EventSummary => !!x)} />
        ))}
      </ol>
      <p className="mt-3 text-label text-graphite">{int(d.event_count)} linked events · {d.incident_id}</p>
    </div>
  );
}
