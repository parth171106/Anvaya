import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { ErrorState } from '@/components/common/states';
import { LineageView } from '@/features/event/LineageView';
import { api, ApiError } from '@/lib/api';
import { dateTimeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { DraftTestResult, ParserDraft } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useReplayStore } from '@/state';

const CHECKS: { key: keyof Pick<DraftTestResult, 'holdout' | 'all' | 'roundtrip' | 'ocsf_valid'>; label: string; failCheck: string[] }[] = [
  { key: 'holdout', label: 'Held-out lines parsed', failCheck: ['load', 'detect', 'parse'] },
  { key: 'all', label: 'All lines parsed', failCheck: ['load', 'detect', 'parse'] },
  { key: 'roundtrip', label: 'Lossless round-trip', failCheck: ['roundtrip'] },
  { key: 'ocsf_valid', label: 'Valid OCSF', failCheck: ['ocsf'] },
];

export function DraftOriginLabel({ origin, model, generatedAt }: { origin: ParserDraft['origin']; model: string | null; generatedAt: number | null }) {
  const text = origin === 'llm_live' ? `Drafted by local LLM (live) · ${model}`
    : origin === 'llm_cached' ? `Drafted by local LLM (cached run) · ${model} · generated ${dateTimeIST(generatedAt)}`
      : 'Hand-authored parser template · not AI-generated. Run the checks before approving.';
  return <p className="text-body text-graphite">{text}</p>;
}

/** The four checks resolve one after another, 150 ms apart (UI_UX_BRIEF.md §5.7). */
function CheckList({ result, running }: { result: DraftTestResult | null; running: boolean }) {
  const [revealed, setRevealed] = useState(0);
  useEffect(() => {
    if (!result) { setRevealed(0); return; }
    setRevealed(0);
    const timers = CHECKS.map((_, i) => setTimeout(() => setRevealed(i + 1), 150 * (i + 1)));
    return () => timers.forEach(clearTimeout);
  }, [result]);
  return (
    <ul className="space-y-2">
      {CHECKS.map((c, i) => {
        const r = result?.[c.key];
        const shown = result && revealed > i;
        const ok = r ? r.passed === r.total : false;
        const firstFail = result?.failures.find((f) => c.failCheck.includes(f.check));
        return (
          <li key={c.key} className="flex min-h-11 flex-col justify-center rounded-control border border-rule px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-body">{c.label}</span>
              {!shown ? <span className="text-body text-muted-foreground">{running || result ? 'Checking…' : '—'}</span> : (
                <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.12 }}
                  className={cn('inline-flex items-center gap-1 font-mono text-mono tabular', ok ? 'text-int-verified' : 'text-int-tampered')}>
                  {r!.passed}/{r!.total} {ok ? <Check className="size-4" aria-label="passed" /> : <X className="size-4" aria-label="failed" />}
                </motion.span>
              )}
            </div>
            {shown && !ok && firstFail && (
              <p className="mt-1 truncate font-mono text-label text-int-tampered" title={firstFail.detail}>
                line {firstFail.index}: {firstFail.detail}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ReplayProgress({ done, total, status }: { done: number; total: number; status: 'idle' | 'running' | 'done' }) {
  if (status === 'idle') return <div className="h-6" />;
  const pct = total ? Math.round((100 * done) / total) : 0;
  return (
    <div className="flex h-6 items-center gap-3" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}
      aria-label="Replaying quarantined records">
      <span className="text-body">{status === 'done' ? 'Replayed' : 'Replaying'}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-pill bg-paper-sunk">
        <div className="h-full bg-int-verified transition-[width] duration-base" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-mono tabular">{done}/{total}</span>
    </div>
  );
}

export function ParserDraftDialog({ draftId, shape, open, onOpenChange }: {
  draftId: string | null; shape: string; open: boolean; onOpenChange: (o: boolean) => void;
}) {
  const draft = useQuery({ queryKey: qk.draft(draftId ?? ''), queryFn: () => api.parsers.getDraft(draftId!), enabled: !!draftId });
  const replay = useReplayStore((s) => s.active);
  const completed = useReplayStore((s) => s.completed);
  const [replayId, setReplayId] = useState<string | null>(null);
  const test = useMutation({ mutationFn: () => api.parsers.test(draftId!) });
  const approve = useMutation({ mutationFn: () => api.parsers.approve(draftId!), onSuccess: (r) => setReplayId(r.replay_id) });
  const reject = useMutation({ mutationFn: () => api.parsers.reject(draftId!, 'Rejected by analyst'), onSuccess: () => onOpenChange(false) });
  const result = test.data ?? draft.data?.test ?? null;
  const d = draft.data;
  const mine = replay && replay.replayId === replayId ? replay : null;
  const replayStatus = !replayId ? 'idle' : completed?.replayId === replayId ? 'done' : 'running';
  const sample = result?.samples[0];
  const approved = !!replayId || d?.status === 'approved';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] w-[calc(100vw-2rem)] max-w-[900px] overflow-y-auto rounded-dialog sm:max-w-[900px]">
        <DialogTitle className="text-h2 font-semibold">Parser draft for {shape}</DialogTitle>
        <DialogDescription asChild>
          <div>{d ? <DraftOriginLabel origin={d.origin} model={d.model} generatedAt={d.generated_at} /> : <span className="text-body">Loading draft…</span>}</div>
        </DialogDescription>
        {draft.isError ? (
          <ErrorState title="Couldn't load the draft." onRetry={() => draft.refetch()} />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 min-[900px]:grid-cols-[minmax(0,1fr)_300px] [&>*]:min-w-0">
              <pre aria-label="Draft YAML (read-only)"
                className="h-[300px] overflow-auto rounded-panel border border-rule bg-paper-sunk p-3 font-mono text-mono">{d?.yaml ?? ''}</pre>
              <div>
                <h3 className="mb-2 text-h3 font-semibold">Checks</h3>
                <CheckList result={result} running={test.isPending} />
              </div>
            </div>
            {sample && (
              <div>
                <p className="mb-2 text-label text-graphite">Sample: raw line ↔ OCSF (held-out line {sample.index}, compact lineage view)</p>
                <LineageView compact rawText={sample.raw} rawBytesLength={sample.raw.length} ocsf={sample.ocsf}
                  lineage={sample.lineage} version="" />
              </div>
            )}
            <p className="text-body text-graphite">
              Approving activates {d ? `${(d.yaml.match(/^name:\s*(\S+)/m)?.[1] ?? 'the parser')}@${d.yaml.match(/^version:\s*(\S+)/m)?.[1] ?? '1.0.0'}` : 'the parser'} and
              replays {d ? d.train_count + d.holdout_count : 20} quarantined records. This is recorded in the audit log.
            </p>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button variant="ghost" onClick={() => reject.mutate()} disabled={approved || reject.isPending}>Reject draft</Button>
              <Button variant="outline" onClick={() => test.mutate()} disabled={!draftId || test.isPending || approved}>
                {test.isPending ? 'Running tests…' : 'Run tests'}
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={result?.promotable ? -1 : 0}>
                    <Button onClick={() => approve.mutate()} disabled={!result?.promotable || approve.isPending || approved}>
                      {approve.isPending ? 'Approving…' : 'Approve & replay'}
                    </Button>
                  </span>
                </TooltipTrigger>
                {!result?.promotable && <TooltipContent>All four checks must pass 100% before approval.</TooltipContent>}
              </Tooltip>
            </div>
            {approve.isError && (
              <p className="text-body text-int-tampered">{approve.error instanceof ApiError ? approve.error.message : "Couldn't approve."}</p>
            )}
            <ReplayProgress status={replayStatus} done={mine?.done ?? (replayStatus === 'done' ? completed!.parsed : 0)}
              total={mine?.total ?? (completed?.parsed ?? 0) + (completed?.stillQuarantined ?? 0)} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
