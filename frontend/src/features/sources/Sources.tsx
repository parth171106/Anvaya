import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AlertTriangle, Inbox, Network } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { DeviceChip, FormatChip, SilenceBadge } from '@/components/badges/badges';
import { Bone, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api, ApiError } from '@/lib/api';
import { DASH, dateTimeIST, int } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { ParserInfo, QuarantineGroup, SourceInfo } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useSourcesStore } from '@/state';
import { ParserDraftDialog } from './ParserDraftDialog';

const TABS = ['devices', 'quarantine', 'parsers'] as const;
type Tab = (typeof TABS)[number];

function RateSpark({ history }: { history: number[] }) {
  if (history.length < 2) return null;
  const max = Math.max(...history, 1);
  const pts = history.map((v, i) => `${(i / (history.length - 1)) * 48},${14 - (v / max) * 12}`).join(' ');
  return <svg aria-hidden width={48} height={16} className="inline-block"><polyline points={pts} fill="none" stroke="var(--graphite)" strokeWidth={1.25} /></svg>;
}

function statusCell(s: SourceInfo) {
  if (s.status === 'silent') return <SilenceBadge seconds={s.silent_for_s} />;
  return <span className={s.status === 'active' ? 'text-int-verified' : 'text-graphite'}>{s.status === 'active' ? 'Active' : 'Learning'}</span>;
}

const PRODUCT_LABEL: Record<string, string> = { Cisco: 'Cisco · ASA', OISF: 'OISF · Suricata', Fortinet: 'Fortinet · FortiGate', Acme: 'Acme · EdgeRouter' };

function SourcesTable({ sources, history }: { sources: SourceInfo[]; history: Record<string, number[]> }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-rule bg-surface" tabIndex={0} aria-label="Source details">
      <table className="w-full min-w-[900px] border-collapse text-body">
        <thead><tr className="text-left text-label font-medium text-graphite">
          {['Device', 'Vendor · product', 'Format', 'Parser', 'Events', 'Rate', 'Status'].map((h) => <th key={h} scope="col" className="h-11 px-4">{h}</th>)}
        </tr></thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.device} className="h-12 border-t border-rule">
              <td className="px-4"><DeviceChip device={s.device} product={false} /></td>
              <td className="px-4">{PRODUCT_LABEL[s.vendor] ?? `${s.vendor} · ${s.product}`}</td>
              <td className="px-4"><FormatChip format={s.format} /></td>
              <td className="px-4 font-mono text-mono">{s.parser}</td>
              <td className="px-4 tabular">{int(s.events_total)}</td>
              <td className="px-4 tabular"><span className="inline-flex items-center gap-2">{s.rate_epm > 0 ? `${int(s.rate_epm)} /min` : DASH}<RateSpark history={history[s.device] ?? []} /></span></td>
              <td className="px-4">{statusCell(s)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QuarantineGroupCard({ group, onDraft, draftPending }: { group: QuarantineGroup; onDraft: (id: string) => void; draftPending: boolean }) {
  const shape = group.shape_label.split(' · ').slice(1).join(' · ');
  return (
    <div className="rounded-panel border border-rule bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-h3 font-semibold">
            <AlertTriangle className="size-5 text-st-warn" aria-hidden /> Unrecognised source · {group.count} records
          </h3>
          <p className="mt-1 text-body text-graphite">{shape} · via {group.transport.toUpperCase()} from {group.peer_ip}</p>
        </div>
        <Button onClick={() => onDraft(group.group_id)} disabled={draftPending}>{draftPending ? 'Drafting…' : 'Draft parser'}</Button>
      </div>
      <p className="mt-3 truncate rounded-control bg-paper-sunk px-3 py-2 font-mono text-mono">{group.sample_lines[0]}</p>
      <p className="mt-2 text-body text-graphite">Raw bytes are sealed. Nothing is dropped.</p>
    </div>
  );
}

function ParsersTable({ parsers }: { parsers: ParserInfo[] }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-rule bg-surface" tabIndex={0} aria-label="Source details">
      <table className="w-full min-w-[900px] border-collapse text-body">
        <thead><tr className="text-left text-label font-medium text-graphite">
          {['Parser', 'Status', 'Origin', 'Format', 'Approved', 'Round-trip pass', 'Events parsed'].map((h) => <th key={h} scope="col" className="h-11 px-4">{h}</th>)}
        </tr></thead>
        <tbody>
          {parsers.map((p) => (
            <tr key={`${p.name}@${p.version}`} className="h-12 border-t border-rule">
              <td className="px-4 font-mono text-mono">{p.name}@{p.version}</td>
              <td className="px-4 capitalize">{p.status}</td>
              <td className="px-4">{p.origin === 'builtin' ? 'Built in' : p.origin === 'ai_draft' ? 'AI draft, approved' : 'Hand-authored / user'}</td>
              <td className="px-4"><FormatChip format={p.format} /></td>
              <td className="px-4">{p.approved_by ? `${p.approved_by} · ${dateTimeIST(p.approved_at)}` : DASH}</td>
              <td className="px-4 tabular">{p.roundtrip_pass_rate == null ? DASH : `${Math.round(p.roundtrip_pass_rate * 100)}%`}</td>
              <td className="px-4 tabular">{int(p.events_parsed)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Sources() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.includes(params.get('tab') as Tab) ? params.get('tab') : 'devices') as Tab;
  const sources = useQuery({ queryKey: qk.sources, queryFn: api.sources, refetchInterval: 2000 });
  const quarantine = useQuery({ queryKey: qk.quarantine, queryFn: api.quarantine, refetchInterval: 5000 });
  const parsers = useQuery({ queryKey: qk.parsers, queryFn: api.parsers.list });
  const history = useRef<Record<string, number[]>>({});
  useEffect(() => {
    if (!sources.data) return;
    useSourcesStore.getState().setAll(sources.data.items);
    for (const s of sources.data.items) history.current[s.device] = [...(history.current[s.device] ?? []), s.rate_epm].slice(-12);
  }, [sources.data]);
  const live = useSourcesStore((s) => s.byDevice);
  const devices = Object.values(live).sort((a, b) => a.device.localeCompare(b.device));

  const [dialog, setDialog] = useState<{ draftId: string; shape: string } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [draftError, setDraftError] = useState<string | null>(null);
  const createDraft = useMutation({
    mutationFn: (groupId: string) => api.parsers.draft(groupId),
    onSuccess: (d, groupId) => {
      setDrafts((m) => ({ ...m, [groupId]: d.draft_id }));
      setDialog({ draftId: d.draft_id, shape: shapeOf(groupId) });
    },
    onError: (e) => setDraftError(e instanceof ApiError ? e.message : "Couldn't draft a parser."),
  });
  const shapeOf = (groupId: string) => quarantine.data?.groups.find((g) => g.group_id === groupId)?.shape_signature ?? '';
  const onDraft = (groupId: string) => {
    setDraftError(null);
    if (drafts[groupId]) setDialog({ draftId: drafts[groupId], shape: shapeOf(groupId) });
    else createDraft.mutate(groupId);
  };
  const qTotal = quarantine.data?.total ?? 0;

  return (
    <div>
      <PageHeader title="Sources & parsers" subtitle="Device health, quarantine and parser onboarding" />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList className="mb-4 h-auto max-w-full flex-wrap rounded-control bg-paper-sunk p-1">
          <TabsTrigger value="devices" className="min-h-10 px-3 text-body">Devices</TabsTrigger>
          <TabsTrigger value="quarantine" className="min-h-10 px-3 text-body">Quarantine ({qTotal})</TabsTrigger>
          <TabsTrigger value="parsers" className="min-h-10 px-3 text-body">Parsers</TabsTrigger>
        </TabsList>
        <TabsContent value="devices">
          {sources.isPending ? <Skeleton><div className="space-y-2">{[0, 1, 2, 3].map((i) => <Bone key={i} className="h-12" />)}</div></Skeleton>
            : sources.isError ? <ErrorState title="Couldn't load devices." onRetry={() => sources.refetch()} />
              : devices.length === 0 ? <div className="rounded-panel border border-rule bg-surface"><EmptyState icon={Network} title="No devices yet" body="No devices have sent logs yet." /></div>
                : <SourcesTable sources={devices} history={history.current} />}
        </TabsContent>
        <TabsContent value="quarantine">
          {draftError && <ErrorState className="mb-4" title={draftError} />}
          {quarantine.isPending ? <Skeleton><Bone className="h-40" /></Skeleton>
            : quarantine.isError ? <ErrorState title="Couldn't load the quarantine." onRetry={() => quarantine.refetch()} />
              : quarantine.data.groups.length === 0 ? (
                <div className="rounded-panel border border-rule bg-surface">
                  <EmptyState icon={Inbox} title="Quarantine is empty" body="Logs ANVAYA can't parse yet are sealed and held here — never dropped." />
                </div>
              ) : (
                <div className={cn('space-y-3')}>
                  {quarantine.data.groups.map((g) => (
                    <QuarantineGroupCard key={`${g.group_id}-${g.reason}`} group={g} onDraft={onDraft}
                      draftPending={createDraft.isPending && createDraft.variables === g.group_id} />
                  ))}
                </div>
              )}
        </TabsContent>
        <TabsContent value="parsers">
          {parsers.isPending ? <Skeleton><div className="space-y-2">{[0, 1, 2].map((i) => <Bone key={i} className="h-12" />)}</div></Skeleton>
            : parsers.isError ? <ErrorState title="Couldn't load parsers." onRetry={() => parsers.refetch()} />
              : <ParsersTable parsers={parsers.data.items} />}
        </TabsContent>
      </Tabs>
      <ParserDraftDialog draftId={dialog?.draftId ?? null} shape={dialog?.shape ?? ''} open={!!dialog}
        onOpenChange={(o) => { if (!o) setDialog(null); }} />
    </div>
  );
}
