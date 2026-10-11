import { Fragment, useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Bone, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { int, shortHash, timeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { FailedRecord, LedgerBatch, LedgerVerifyResult, WitnessInfo, WitnessStatus } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useDemoStore, useIntegrityStore } from '@/state';

function firstMismatch(r: LedgerVerifyResult): number | null {
  const all = r.witness_status.flatMap((w) => w.mismatched_batches);
  return all.length ? Math.min(...all) : null;
}

export function verdictText(r: LedgerVerifyResult): string {
  if (r.verdict === 'verified') return `All ${int(r.checked_records)} records verified across ${int(r.checked_batches)} batches · both witness nodes agree`;
  if (r.verdict === 'tampered') {
    const k = r.failed_records.length || r.failed_batches.length;
    return `${k} ${k === 1 ? 'record failed' : 'records failed'} verification`;
  }
  return `Primary ledger consistent · witness nodes disagree on batch ${firstMismatch(r)} onward — tamper suspected`;
}

function VerifySummary({ result, fingerprint }: { result: LedgerVerifyResult | null; fingerprint: string }) {
  const tone = !result ? 'border-rule bg-surface text-ink' : result.verdict === 'verified' ? 'border-int-verified bg-int-verified-bg'
    : result.verdict === 'tampered' ? 'border-int-tampered bg-int-tampered-bg' : 'border-int-mismatch bg-int-mismatch-bg';
  const Icon = !result || result.verdict === 'verified' ? ShieldCheck : result.verdict === 'tampered' ? ShieldAlert : ShieldQuestion;
  const iconCls = !result ? 'text-muted-foreground' : result.verdict === 'verified' ? 'text-int-verified'
    : result.verdict === 'tampered' ? 'text-int-tampered' : 'text-int-mismatch';
  return (
    <div className="relative min-h-[92px]">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div key={result?.verdict ?? "none"}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.32, ease: [0.05, 0.7, 0.1, 1] }}
          role={result && result.verdict !== 'verified' ? 'alert' : 'status'}
          className={cn('flex items-start gap-3 rounded-panel border p-5', tone)}>
          <Icon className={cn('mt-0.5 size-6 shrink-0', iconCls)} aria-hidden />
          <div>
            <p className="text-body-lg font-medium">
              {result ? verdictText(result) : 'Not verified yet. Run Verify ledger to check every record against its sealed hash.'}
            </p>
            {result && <p className="text-body text-graphite">Checked in {result.took_ms} ms · primary key {shortHash(fingerprint)}</p>}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function TamperDiff({ failure, onOpenEvent }: { failure: FailedRecord; onOpenEvent: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 bg-int-tampered-bg px-4 py-3">
      <p className="font-mono text-mono">
        └ {failure.raw_id} · {failure.device ?? '—'} · {timeIST(failure.time)} · byte {failure.first_diff_offset ?? '—'} changed{' '}
        {failure.changed ? `'${failure.changed.from}' → '${failure.changed.to}'` : '—'} ({failure.field ?? '—'})
      </p>
      {failure.event_id && <Button variant="outline" onClick={onOpenEvent}>Open event</Button>}
    </div>
  );
}

const Mark = ({ ok, warn }: { ok: boolean | null; warn?: boolean }) => (
  ok === null ? <span className="text-graphite">—</span>
    : <span className={ok ? 'text-int-verified' : warn ? 'text-int-mismatch' : 'text-int-tampered'}>{ok ? '✓' : '✗'}</span>
);

function LedgerTable({ batches, result, onOpenEvent }: { batches: LedgerBatch[]; result: LedgerVerifyResult | null; onOpenEvent: (id: string) => void }) {
  const failedB = new Set(result?.failed_batches.map((f) => f.batch_id));
  const mism = (name: string) => new Set(result?.witness_status.find((w) => w.name === name)?.mismatched_batches);
  const ntro = mism('witness-ntro'), certin = mism('witness-certin');
  const firstFailing = result ? [...failedB, ...ntro, ...certin].sort((a, b) => a - b)[0] ?? null : null;
  const [expanded, setExpanded] = useState<number | null>(null);
  useEffect(() => setExpanded(firstFailing), [firstFailing, result]);
  return (
    <div tabIndex={0} aria-label="Ledger batches" className="max-h-[calc(100vh-460px)] min-h-[300px] overflow-auto rounded-panel border border-rule bg-surface">
      <table className="w-full border-collapse text-body">
        <thead className="sticky top-0 z-[1] bg-surface shadow-e1">
          <tr className="text-left text-label font-medium text-graphite">
            {['Batch', 'Records', 'Merkle root', 'Signed', 'ntro', 'certin', 'Status'].map((h) => <th key={h} scope="col" className="h-11 px-4">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => {
            const failed = failedB.has(b.batch_id);
            const wm = ntro.has(b.batch_id) || certin.has(b.batch_id);
            const fails = result?.failed_records.filter((f) => f.batch_id === b.batch_id) ?? [];
            const status = result ? !(failed || wm) : null;
            return (
              <Fragment key={b.batch_id}>
                <tr onClick={() => (failed || wm) && setExpanded(expanded === b.batch_id ? null : b.batch_id)}
                  className={cn('h-11 border-t border-rule', failed ? 'bg-int-tampered-bg/50' : wm ? 'bg-int-mismatch-bg/60' : 'hover:bg-paper-sunk',
                    (failed || wm) && 'cursor-pointer')}>
                  <td className="px-4 font-mono text-mono">{b.batch_id}</td>
                  <td className="px-4 font-mono text-mono">{b.first_seq}–{b.last_seq}</td>
                  <td className="px-4 font-mono text-mono">{shortHash(b.merkle_root)}</td>
                  <td className="px-4"><Mark ok={!!b.signature} /></td>
                  <td className="px-4"><Mark ok={ntro.has(b.batch_id) ? false : b.witnesses.find((w) => w.name === 'witness-ntro')?.cosigned ?? false} warn /></td>
                  <td className="px-4"><Mark ok={certin.has(b.batch_id) ? false : b.witnesses.find((w) => w.name === 'witness-certin')?.cosigned ?? false} warn /></td>
                  <td className="px-4"><Mark ok={status} warn={!failed} /></td>
                </tr>
                {expanded === b.batch_id && fails.map((f) => (
                  <tr key={f.raw_id}><td colSpan={7}><TamperDiff failure={f} onOpenEvent={() => f.event_id && onOpenEvent(f.event_id)} /></td></tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function WitnessCard({ w, status }: { w: WitnessInfo; status: WitnessStatus | undefined }) {
  const disagree = status && !status.agree;
  return (
    <div className="rounded-panel border border-rule bg-surface p-4">
      <h3 className="font-mono text-mono font-medium">{w.name}</h3>
      <p className="text-body">{w.label}</p>
      <p className="mt-1 text-label text-graphite">Key <span className="font-mono">{shortHash(w.pubkey_fingerprint)}</span></p>
      <p className="text-label text-graphite">Last co-signed batch {w.last_cosigned_batch}</p>
      <p className={cn('mt-2 text-body font-medium', disagree ? 'text-int-mismatch' : status ? 'text-int-verified' : 'text-graphite')}>
        {!status ? 'Not checked yet' : disagree ? `Disagrees from batch ${Math.min(...status.mismatched_batches)}` : 'Agrees with primary'}
      </p>
    </div>
  );
}

function DemoIntegrityControls() {
  const { demoMode, tampered, resealed, tamper, reseal } = useDemoStore();
  if (!demoMode) return null;
  return (
    <div className="flex items-center gap-3" role="group" aria-label="Demo controls (synthetic)">
      <span className="text-label text-graphite">Demo controls (synthetic)</span>
      <Button variant="outline" onClick={() => void tamper()} disabled={tampered}>Simulate tamper</Button>
      <Button variant="outline" onClick={() => void reseal()} disabled={!tampered || resealed}>Simulate insider re-seal</Button>
    </div>
  );
}

export default function Integrity() {
  const navigate = useNavigate();
  const batches = useQuery({ queryKey: qk.batches, queryFn: () => api.ledger.batches({ limit: 200 }) });
  const witnesses = useQuery({ queryKey: qk.witnesses, queryFn: api.witnesses, refetchInterval: 5000 });
  const { lastVerify, setVerify } = useIntegrityStore();
  const verify = useMutation({
    mutationFn: api.ledger.verify,
    onSuccess: (r) => {
      setVerify(r);
      toast(`Ledger verified · ${verdictText(r)}`);
      batches.refetch();
      witnesses.refetch();
    },
  });
  return (
    <div className="space-y-5">
      <PageHeader title="Evidence integrity" subtitle="Every record is hashed, sealed in a Merkle batch, chained, signed, and co-signed." />
      <div className="flex flex-wrap items-center gap-6">
        <Button onClick={() => verify.mutate()} disabled={verify.isPending}>{verify.isPending ? 'Verifying…' : 'Verify ledger'}</Button>
        <DemoIntegrityControls />
      </div>
      {verify.isError ? (
        <ErrorState title="Verification couldn't run." onRetry={() => verify.mutate()} code={(verify.error as Error).message} />
      ) : (
        <VerifySummary result={lastVerify} fingerprint={batches.data?.primary_key_fingerprint ?? ''} />
      )}
      <div className="grid grid-cols-[1fr_320px] gap-6">
        <section>
          <h2 className="mb-3 text-h2 font-semibold">Ledger batches</h2>
          {batches.isPending ? <Skeleton><div className="space-y-2">{Array.from({ length: 8 }, (_, i) => <Bone key={i} className="h-11" />)}</div></Skeleton>
            : batches.isError ? <ErrorState title="Couldn't load the ledger." onRetry={() => batches.refetch()} />
              : batches.data.items.length === 0 ? (
                <div className="rounded-panel border border-rule bg-surface">
                  <EmptyState icon={ShieldCheck} title="Nothing sealed yet" body="Records are sealed in batches of 16 as they arrive." />
                </div>
              ) : <LedgerTable batches={batches.data.items} result={lastVerify} onOpenEvent={(id) => navigate(`/events/${id}`, { state: { from: 'integrity' } })} />}
        </section>
        <section>
          <h2 className="mb-3 text-h2 font-semibold">Witness nodes</h2>
          <div className="space-y-3">
            {witnesses.data?.items.map((w) => <WitnessCard key={w.name} w={w} status={lastVerify?.witness_status.find((s) => s.name === w.name)} />)
              ?? <Skeleton><Bone className="h-36" /><Bone className="mt-3 h-36" /></Skeleton>}
          </div>
        </section>
      </div>
    </div>
  );
}
