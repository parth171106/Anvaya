import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { api } from '@/lib/api';
import { timeIST } from '@/lib/format';
import { qk } from '@/lib/queryKeys';
import type { ComponentStatus, Health } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useDemoStore, useStatsStore, useStreamStore } from '@/state';
import { ThemeControl } from './ThemeControl';
import { MobileNavigation } from './NavRail';
import { SignOut } from './AuthGate';

type Tone = 'ok' | 'warn' | 'down' | 'neutral';
const DOT: Record<Tone, string> = { ok: 'bg-st-live', warn: 'bg-st-warn', down: 'bg-st-down', neutral: 'bg-int-pending' };

export function HealthChip({ label, tone, detail }: { label: string; tone: Tone; detail?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className={cn('inline-flex h-8 shrink-0 items-center gap-2 whitespace-nowrap rounded-pill border px-3 text-label font-medium',
          tone === 'warn' ? 'border-st-warn bg-st-warn-bg text-ink' : tone === 'down' ? 'border-st-down bg-st-down-bg text-ink'
            : 'border-rule bg-surface text-ink')}>
          <span aria-hidden className={cn('size-1.5 rounded-pill', DOT[tone])} />
          {label}
        </span>
      </TooltipTrigger>
      {detail && <TooltipContent>{detail}</TooltipContent>}
    </Tooltip>
  );
}

function chips(h: Health | undefined, failed: boolean): { label: string; tone: Tone; detail?: string }[] {
  if (failed) return [{ label: 'ANVAYA service unreachable', tone: 'down', detail: 'Check that the api container is running.' }];
  if (!h) return [];
  const c = h.components;
  const okTone = (x?: ComponentStatus): Tone => (!x ? 'neutral' : x.status === 'ok' ? 'ok' : x.status === 'error' ? 'down' : 'warn');
  const w = c.witnesses;
  const net = c.network?.status;
  return [
    { label: c.vault?.status === 'ok' ? 'Vault ✓' : 'Vault ✗', tone: okTone(c.vault), detail: c.vault?.detail },
    { label: c.ledger?.status === 'ok' ? 'Ledger ✓' : 'Ledger ✗', tone: okTone(c.ledger), detail: c.ledger?.detail },
    { label: `Witnesses ${w?.ok_count ?? 0}/${w?.total ?? 2}`, tone: okTone(w), detail: 'Simulated, local witness stores' },
    { label: c.llm?.status === 'ready' ? 'Local LLM ready' : 'Local LLM fallback', tone: c.llm?.status === 'ready' ? 'ok' : 'warn',
      detail: c.llm?.status === 'ready' ? `${c.llm.model} on this machine` : 'Search uses query templates' },
    net === 'external_route'
      ? { label: 'External route detected', tone: 'warn', detail: 'This machine can reach the internet' }
      : net === 'air_gapped' ? { label: 'No external route', tone: 'ok', detail: 'TCP probe to 1.1.1.1 and 9.9.9.9 failed' }
        : { label: 'Network not checked', tone: 'neutral' },
  ];
}

/** Scenario clock, interpolated between stats ticks at the current playback rate. */
export function ScenarioClock() {
  const clock = useStatsStore((s) => s.stats?.clock);
  const phase = useDemoStore((s) => s.phase);
  const speed = useDemoStore((s) => s.speed);
  const base = useRef<{ at: number; ms: number } | null>(null);
  const [, tick] = useState(0);
  useEffect(() => {
    if (clock) base.current = { at: Date.now(), ms: clock.now_ms };
  }, [clock]);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 250);
    return () => clearInterval(t);
  }, []);
  const rate = phase === 'scripted' ? speed : 1;
  const now = base.current ? base.current.ms + (Date.now() - base.current.at) * rate : null;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-2 gap-y-0">
      <span className="text-label text-graphite">{clock?.label ?? 'Scenario clock'}</span>
      <span className="font-mono text-mono-lg text-ink tabular">{timeIST(now)} IST</span>
    </span>
  );
}

const STREAM = {
  connecting: { label: 'Connecting', cls: 'bg-st-warn' }, live: { label: 'Live', cls: 'bg-st-live' },
  reconnecting: { label: 'Reconnecting', cls: 'bg-st-warn' }, offline: { label: 'Offline', cls: 'bg-st-down' },
} as const;

export function StreamDot() {
  const status = useStreamStore((s) => s.status);
  const { label, cls } = STREAM[status];
  return (
    <span className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-label font-medium text-ink" aria-live="polite">
      <span aria-hidden className={cn('size-2.5 rounded-pill', cls)} />
      {label}
    </span>
  );
}

export function SyntheticDataPill() {
  return (
    <span className="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-pill border border-st-warn bg-st-warn-bg px-3 text-label font-medium text-ink">
      Synthetic lab data
    </span>
  );
}

export function TopBar() {
  const demoMode = useDemoStore((s) => s.demoMode);
  const health = useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: 5000, retry: 0 });
  return (
    <header className="z-20 shrink-0 border-b border-rule bg-surface shadow-e1">
      <div className="flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:px-6 lg:px-8">
        <MobileNavigation />
        <div className="flex shrink-0 items-center gap-3">
          <span aria-hidden className="size-3.5 rounded-[2px] bg-seal" />
          <span className="text-[18px] font-semibold tracking-[0.04em] text-ink">ANVAYA</span>
          <span className="hidden text-body text-graphite min-[1800px]:inline">Every perimeter log, one verifiable truth</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <ThemeControl />
          <div className="hidden sm:block"><SignOut /></div>
        </div>
        <div className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-2 xl:w-auto">
          {demoMode ? <SyntheticDataPill /> : health.data && <HealthChip label="Live-log pilot" tone="neutral" />}
          <ScenarioClock />
          <StreamDot />
        </div>
      </div>
      <details className="border-t border-rule px-4 py-2 md:hidden">
        <summary className="cursor-pointer text-label font-medium text-graphite">Service status & session</summary>
        <div className="flex flex-wrap items-center gap-2 pt-3">
          {chips(health.data, health.isError).map((c) => <HealthChip key={c.label} {...c} />)}
          <SignOut />
        </div>
      </details>
      <div className="hidden flex-wrap items-center justify-end gap-2 border-t border-rule px-6 py-2 md:flex lg:px-8">
        {chips(health.data, health.isError).map((c) => <HealthChip key={c.label} {...c} />)}
      </div>
    </header>
  );
}
