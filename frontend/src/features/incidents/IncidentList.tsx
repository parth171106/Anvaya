import { useQuery } from '@tanstack/react-query';
import { Siren } from 'lucide-react';
import { Link } from 'react-router';
import { DeviceChip } from '@/components/badges/badges';
import { Bone, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/common/states';
import { api } from '@/lib/api';
import { int, timeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { IncidentSummary } from '@/lib/types';
import { cn } from '@/lib/utils';
import { WORKFLOW_LABELS } from './Investigation';

export const LEVEL_CLS: Record<IncidentSummary['level'], string> = {
  High: 'bg-sev-high-bg text-sev-high', Medium: 'bg-sev-medium-bg text-sev-medium', Low: 'bg-sev-low-bg text-sev-low',
};

export function IncidentHeaderLine({ i }: { i: IncidentSummary }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-body">
      <span className={cn('rounded-chip px-2 text-label font-semibold', LEVEL_CLS[i.level])}>{i.level}</span>
      <span className="rounded-chip border border-rule px-2 text-label font-medium">{WORKFLOW_LABELS[i.workflow?.state ?? (i.status === 'closed' ? 'resolved' : 'new')]}</span>
      {i.workflow?.controlled_test && <span className="rounded-chip bg-paper-sunk px-2 text-label font-medium">Controlled test</span>}
      <span className="text-body-lg font-semibold tabular">Risk {i.risk}</span>
      <span className="flex min-w-0 max-w-full flex-wrap items-center gap-3">{i.devices.map((d) => <DeviceChip key={d} device={d} product={false} />)}</span>
      <span className="font-mono text-mono text-graphite">{timeIST(i.first_time)}–{timeIST(i.last_time)} IST</span>
      <span className="text-graphite tabular">{int(i.event_count)} events</span>
    </div>
  );
}

function IncidentCard({ incident }: { incident: IncidentSummary }) {
  return (
    <Link to={`/incidents/${incident.incident_id}`}
      className="block rounded-panel border border-rule bg-surface p-5 transition-colors duration-fast hover:bg-paper-sunk">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <h2 className="font-display text-h2 font-semibold">{incident.title}</h2>
        <span className="font-mono text-mono text-graphite">{incident.incident_id}</span>
      </div>
      <IncidentHeaderLine i={incident} />
    </Link>
  );
}

export default function IncidentList() {
  const q = useQuery({ queryKey: qk.incidents, queryFn: api.incidents.list });
  return (
    <div>
      <PageHeader title="Incidents" subtitle="Security findings linked to their original evidence" />
      {q.isPending ? (
        <Skeleton><div className="space-y-3"><Bone className="h-28" /><Bone className="h-28" /></div></Skeleton>
      ) : q.isError ? (
        <ErrorState title="Couldn't load incidents." onRetry={() => q.refetch()} code={(q.error as Error).message} />
      ) : q.data.items.length === 0 ? (
        <div className="rounded-panel border border-rule bg-surface">
          <EmptyState icon={Siren} title="No incidents yet"
            body="ANVAYA flags 10 failed SSH connections from one IP to one device within a 10-minute correlation window, or multiple attack stages from an external IP. A finding is a reason to investigate, not proof of a breach." />
        </div>
      ) : (
        <div className="space-y-3">{q.data.items.map((i) => <IncidentCard key={i.incident_id} incident={i} />)}</div>
      )}
    </div>
  );
}
