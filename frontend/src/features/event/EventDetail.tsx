import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowLeft, Copy } from 'lucide-react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { toast } from 'sonner';
import { ConfidencePill, DeviceChip, FormatChip, IntegrityBadge, SeverityBadge } from '@/components/badges/badges';
import { Bone, ErrorState, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { api, ApiError } from '@/lib/api';
import { DASH } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { EventDetail as Detail, RecordVerifyResult, Severity } from '@/lib/types';
import { useIntegrityStore } from '@/state';
import { LineageView, type Tamper } from './LineageView';

function titleOf(o: Record<string, unknown>): string {
  const g = (p: string) => p.split('.').reduce<unknown>((x, k) => (x as Record<string, unknown> | undefined)?.[k], o);
  const cls = o.class_uid as number;
  if (cls === 2004) return (g('finding_info.title') as string) ?? DASH;
  if (cls === 3002) return `${o.status === 'Failure' ? 'Login failed' : 'Login succeeded'} · ${(g('user.name') as string) ?? DASH}`;
  if (o.action === 'Denied') return 'Connection refused';
  if (o.activity_name === 'Close') return 'Connection closed';
  if (o.activity_name === 'Traffic') return `Session ${String(o.action ?? '').toLowerCase()}`;
  const dir = (g('connection_info.direction') as string | undefined)?.toLowerCase();
  const proto = (g('connection_info.protocol_name') as string | undefined)?.toUpperCase();
  return ['Connection opened', [dir, proto].filter(Boolean).join(' ')].filter(Boolean).join(' · ');
}

function EventHeader({ ev }: { ev: Detail }) {
  const o = ev.ocsf, a = ev.anvaya;
  const fromIntegrity = (useLocation().state as { from?: string } | null)?.from === 'integrity';
  return (
    <div className="mb-6">
      <Link to={fromIntegrity ? '/integrity' : '/feed'} className="inline-flex h-10 items-center gap-2 text-body font-medium text-seal hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {fromIntegrity ? 'Back to Integrity' : 'Live feed'}
      </Link>
      <h1 className="mt-1 font-display text-h1 font-semibold">{titleOf(o)}</h1>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-body">
        <DeviceChip device={a.device} />
        <FormatChip format={a.format} />
        <span className="text-graphite">{String(o.class_name)} ({String(o.class_uid)})</span>
        <span className="inline-flex items-center gap-2 text-graphite">Severity: <SeverityBadge severity={o.severity as Severity} /></span>
        <span className="inline-flex items-center gap-2 text-graphite">Conf <ConfidencePill value={a.parse_confidence} breakdown={a.confidence_breakdown} /></span>
      </div>
    </div>
  );
}

function HashBlock({ sha }: { sha: string }) {
  const groups = sha.match(/.{1,4}/g) ?? [];
  const short = [...groups.slice(0, 4), '…', ...groups.slice(-3)].join(' ');
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-label font-medium text-graphite">SHA-256</span>
      <span className="font-mono text-mono" title={sha}>{short}</span>
      <Button variant="ghost" size="icon" aria-label="Copy SHA-256"
        onClick={() => navigator.clipboard?.writeText(sha).then(() => toast('SHA-256 copied'), () => {})}>
        <Copy className="size-4" aria-hidden />
      </Button>
    </span>
  );
}

function RoundTripChip({ rt }: { rt: Detail['anvaya']['roundtrip'] }) {
  if (rt.ok) {
    return <span className="rounded-chip bg-int-verified-bg px-2 py-1 text-label font-medium text-int-verified">
      Lossless ✓ {Math.round(rt.coverage * 100)}% of bytes accounted for</span>;
  }
  const reason = !rt.value_check ? 'a value differs from its bytes' : rt.dropped ? `${rt.dropped} values dropped`
    : `${Math.round(rt.coverage * 100)}% of bytes accounted for`;
  return <span className="rounded-chip bg-int-tampered-bg px-2 py-1 text-label font-medium text-int-tampered">
    Round-trip check failed · {reason}</span>;
}

type VerifyView = { state: 'verified' | 'tampered' | 'mismatch' | 'pending'; label: string } | null;

function viewOf(r: RecordVerifyResult): VerifyView {
  if (r.first_diff_offset != null && r.changed) {
    return { state: 'tampered', label: `Altered on disk · byte ${r.first_diff_offset} changed '${r.changed.from}' → '${r.changed.to}' (${r.field ?? DASH})` };
  }
  const agree = r.witnesses.filter((w) => w.agree).length;
  if (r.ok) return { state: 'verified', label: `Verified · sealed in batch ${r.batch_id} · co-signed by ${agree} witness nodes` };
  return { state: 'mismatch', label: `Primary seal intact · witness nodes disagree on batch ${r.batch_id}` };
}

function VerifyRecordButton({ rawId, onResult }: { rawId: string; onResult: (r: RecordVerifyResult) => void }) {
  const [view, setView] = useState<VerifyView>(null);
  const tries = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const m = useMutation({
    mutationFn: () => api.ledger.verifyRecord(rawId),
    onSuccess: (r) => { tries.current = 0; setView(viewOf(r)); onResult(r); },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409 && tries.current < 6) {  // not sealed yet: retry every 1 s
        tries.current += 1;
        setView({ state: 'pending', label: 'Waiting for seal…' });
        timer.current = setTimeout(() => m.mutate(), 1000);
      } else {
        setView(null);
        toast("Couldn't verify this record. Try again.");
      }
    },
  });
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <div className="flex min-h-11 items-center gap-4">
      <Button variant="outline" onClick={() => { tries.current = 0; m.mutate(); }} disabled={m.isPending}>
        {m.isPending ? 'Verifying…' : 'Verify this record'}
      </Button>
      {view && (
        <motion.span key={view.label} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}>
          <IntegrityBadge state={view.state} label={view.label} className="text-body-lg" />
        </motion.span>
      )}
    </div>
  );
}

function EvidenceFooter({ ev, onVerified }: { ev: Detail; onVerified: (r: RecordVerifyResult) => void }) {
  const r = ev.raw;
  return (
    <div className="mt-6 space-y-3 rounded-panel border border-rule bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-body">
        <HashBlock sha={r.raw_sha256} />
        <span><span className="text-label text-graphite">raw_id</span> <span className="font-mono text-mono">{r.raw_id}</span></span>
        <span><span className="text-label text-graphite">seq</span> <span className="font-mono text-mono">{r.seq}</span></span>
        <span><span className="text-label text-graphite">batch</span> <span className="font-mono text-mono">{r.batch_id ?? 'pending seal'}</span></span>
      </div>
      <div className="flex flex-wrap items-center gap-6">
        <RoundTripChip rt={ev.anvaya.roundtrip} />
        <VerifyRecordButton rawId={r.raw_id} onResult={onVerified} />
      </div>
    </div>
  );
}

export default function EventDetail() {
  const { eventId = '' } = useParams();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: qk.event(eventId), queryFn: () => api.events.get(eventId), staleTime: 0, retry: 0 });
  const lastVerify = useIntegrityStore((s) => s.lastVerify);
  const tamperInfo = useIntegrityStore((s) => s.tamperInfo);
  const [record, setRecord] = useState<RecordVerifyResult | null>(null);

  if (q.isPending) {
    return <Skeleton><Bone className="mb-6 h-20 w-[640px]" /><div className="grid grid-cols-2 gap-6"><Bone className="h-[520px]" /><Bone className="h-[520px]" /></div></Skeleton>;
  }
  if (q.isError) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    return notFound ? (
      <ErrorState title="This event isn't in the store." body="It may have been cleared by a demo reset."
        onRetry={() => navigate('/feed')} retryLabel="Back to Live feed" />
    ) : (
      <ErrorState title="Couldn't load this event." onRetry={() => q.refetch()} code={(q.error as Error).message} />
    );
  }
  const ev = q.data;
  const failed = lastVerify?.failed_records.find((f) => f.raw_id === ev.raw.raw_id);
  const tamper: Tamper | null = record?.first_diff_offset != null && record.changed
    ? { offset: record.first_diff_offset, from: record.changed.from, to: record.changed.to, field: record.field }
    : failed?.first_diff_offset != null && failed.changed
      ? { offset: failed.first_diff_offset, from: failed.changed.from, to: failed.changed.to, field: failed.field }
      : tamperInfo && tamperInfo.raw_id === ev.raw.raw_id
        ? { offset: tamperInfo.offset, from: tamperInfo.from, to: tamperInfo.to, field: tamperInfo.field } : null;
  const version = String((ev.ocsf.metadata as { version?: string } | undefined)?.version ?? '');
  return (
    <div>
      <EventHeader ev={ev} />
      <LineageView rawText={ev.raw.text} rawBytesLength={ev.raw.size} ocsf={ev.ocsf} lineage={ev.anvaya.lineage}
        tamper={tamper} version={version} />
      <EvidenceFooter ev={ev} onVerified={setRecord} />
    </div>
  );
}
