import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { animate, useReducedMotion } from 'framer-motion';
import { ArrowRight, Play } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts';
import { Bone, ErrorState, PageHeader, Panel, Skeleton } from '@/components/common/states';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { DASH, dateIST, int } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { DemoPhase, Stats } from '@/lib/types';
import { useDemoStore, useStatsStore } from '@/state';

interface KpiCounterProps { label: string; value: number | null; unit?: string; format: 'int' | 'rate' | 'pct'; hint?: string; }

function fmt(v: number, format: KpiCounterProps['format']) {
  return format === 'int' ? int(v) : format === 'rate' ? v.toFixed(1) : `${v.toFixed(v >= 99.95 || v === 0 ? 0 : 1)}%`;
}

/** Tweens to new values over --m-count; never animates on first paint. */
export function KpiCounter({ label, value, unit, format, hint }: KpiCounterProps) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(value);
  const first = useRef(true);
  const from = useRef(value ?? 0);
  useEffect(() => {
    if (value == null) { setShown(null); return; }
    if (first.current || reduced) {
      first.current = false;
      from.current = value;
      setShown(value);
      return;
    }
    const ctl = animate(from.current, value, { duration: 0.6, ease: [0.2, 0, 0, 1], onUpdate: (v) => setShown(v) });
    from.current = value;
    return () => ctl.stop();
  }, [value, reduced]);
  return (
    <div className="flex min-h-[132px] flex-col justify-between rounded-panel border border-rule bg-surface p-5">
      <div className="text-kpi font-semibold text-ink tabular">
        {shown == null ? DASH : fmt(shown, format)}{unit && shown != null && <span className="ml-1 text-h3 text-graphite">{unit}</span>}
      </div>
      <div>
        <div className="text-body font-medium text-ink">{label}</div>
        {hint && <div className="text-label text-graphite">{hint}</div>}
      </div>
    </div>
  );
}

const LAYERS = [
  { id: 'L1', title: 'Secure ingestion & forensic vault', detail: 'Every original byte stored, hashed and sealed' },
  { id: 'L2', title: 'Detection, parsing & normalization', detail: 'Any format to OCSF, with byte-level lineage' },
  { id: 'L3', title: 'Intelligence, delivery & governance', detail: 'Cross-device incidents, plain-English search, export' },
] as const;

function LayerStrip() {
  return (
    <Panel title="How ANVAYA works">
      <ol className="space-y-3">
        {LAYERS.map((l, i) => (
          <li key={l.id} className="flex items-center gap-4">
            <span className="w-10 shrink-0 font-mono text-mono-lg font-medium text-seal">{l.id}</span>
            <div className="min-w-0 flex-1">
              <div className="text-body-lg text-ink">{l.title}</div>
              <div className="text-body text-graphite">{l.detail}</div>
            </div>
            {i < LAYERS.length - 1 && <ArrowRight className="size-5 shrink-0 text-muted-foreground" aria-hidden />}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function Sparkline({ points, height }: { points: { t: number; eps: number }[]; height: number }) {
  return (
    <div style={{ height }} aria-label="Ingest rate over the last 60 seconds" role="img">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <YAxis hide domain={[0, 'dataMax']} />
          <Area dataKey="eps" type="monotone" stroke="var(--ink)" strokeWidth={1.5} fill="var(--paper-sunk)"
            isAnimationActive={false} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function LiveActivityPanel({ stats }: { stats: Stats | null }) {
  const series = useStatsStore((s) => s.epsSeries);
  return (
    <Panel title="Live activity">
      <div className="text-label text-graphite">Events per second, last 60 s</div>
      <Sparkline points={series} height={88} />
      <dl className="mt-4 grid grid-cols-2 gap-4">
        <div><dt className="text-body text-graphite">Open incidents</dt>
          <dd className="text-h1 font-semibold tabular">{int(stats?.open_incidents ?? 0)}</dd></div>
        <div><dt className="text-body text-graphite">Silent sources</dt>
          <dd className="text-h1 font-semibold tabular">{int(stats?.sources_silent ?? 0)}</dd></div>
      </dl>
    </Panel>
  );
}

function StartSimulationBar({ phase, onStart, pending, speed }: { phase: DemoPhase; onStart: () => void; pending: boolean; speed: number }) {
  const running = phase !== 'idle';
  return (
    <div className="flex items-center gap-6 rounded-panel border border-rule bg-surface p-5">
      <Button size="lg" onClick={onStart} disabled={running || pending} aria-live="polite">
        <Play className="size-5" aria-hidden />
        {running ? `Simulation running · ${speed}×` : 'Start attack simulation'}
      </Button>
      <p className="text-body-lg text-graphite">Lab scenario: scan → VPN brute force → firewall allow · synthetic data</p>
    </div>
  );
}

function BenchLine({ bench }: { bench: Stats['last_bench'] }) {
  if (!bench) return null;
  return (
    <p className="text-body text-graphite">
      Benchmark on this machine: {int(bench.eps)} events/s sustained · {bench.machine} · measured {dateIST(bench.measured_at)}
    </p>
  );
}

export default function Overview() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: qk.stats, queryFn: api.stats, refetchInterval: 1000 });
  const live = useStatsStore((s) => s.stats);
  const stats = live ?? q.data ?? null;  // SSE stats.tick feeds the store; the poll is the fallback
  const { demoMode, phase, speed, startPending, startScenario } = useDemoStore();

  const start = async () => {
    if (await startScenario()) setTimeout(() => navigate('/feed'), 600);
  };

  return (
    <div className="space-y-6">
      <PageHeader display title="Perimeter evidence overview" subtitle="Every perimeter log, one verifiable truth." />
      {q.isError && !stats ? (
        <ErrorState title="Couldn't reach the ANVAYA service." body="Check that the api container is running."
          onRetry={() => q.refetch()} code={(q.error as Error)?.message} />
      ) : !stats ? (
        <Skeleton><div className="grid grid-cols-5 gap-4">{[0, 1, 2, 3, 4].map((i) => <Bone key={i} className="h-[132px]" />)}</div></Skeleton>
      ) : (
        <div className="grid grid-cols-5 gap-4">
          <KpiCounter label="Events ingested" value={stats.raw_total} format="int" />
          <KpiCounter label="Live ingest rate (measured)" value={stats.ingest_rate_eps} unit="/s" format="rate" />
          <KpiCounter label="Formats detected" value={stats.formats_detected} format="int" />
          <KpiCounter label="Parse coverage" value={stats.parse_coverage_pct} format="pct"
            hint={stats.parse_coverage_pct == null ? 'Appears once events arrive' : undefined} />
          <KpiCounter label="Sealed & co-signed records" value={stats.sealed_records} format="int" />
        </div>
      )}
      <div className="grid grid-cols-[2fr_1fr] gap-6">
        <LayerStrip />
        <LiveActivityPanel stats={stats} />
      </div>
      {demoMode && <StartSimulationBar phase={phase} onStart={start} pending={startPending} speed={speed} />}
      <BenchLine bench={stats?.last_bench ?? null} />
    </div>
  );
}
