// Chips and badges (UI_UX_BRIEF.md §4.3). Colour always comes with a text label.
import { BellOff, Clock, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { deviceColor, formatChip, PRODUCT, severityTokens } from '@/lib/tokens';
import type { Severity } from '@/lib/types';
import { cn } from '@/lib/utils';

export function DeviceDot({ device, className }: { device: string; className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2 shrink-0 rounded-pill', className)}
    style={{ background: deviceColor(device) }} />;
}

export function DeviceChip({ device, product = true }: { device: string; product?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <DeviceDot device={device} />
      <span className="font-mono text-mono text-ink">{device}</span>
      {product && PRODUCT[device] && <span className="text-label text-graphite">{PRODUCT[device]}</span>}
    </span>
  );
}

export function FormatChip({ format }: { format: string }) {
  const { label, color } = formatChip(format);
  return (
    <span className="inline-flex items-center whitespace-nowrap rounded-chip border bg-surface px-1.5 font-mono text-chip"
      style={{ color, borderColor: color }}>
      {label}
    </span>
  );
}

export function ConfidencePill({ value, breakdown }: {
  value: number; breakdown?: { required: number; typed: number; mapped: number };
}) {
  const tone = value >= 85 ? 'text-int-verified bg-int-verified-bg' : value >= 60 ? 'text-sev-medium bg-sev-medium-bg'
    : 'text-sev-high bg-sev-high-bg';
  const pill = <span className={cn('inline-flex min-w-9 justify-center rounded-chip px-1.5 font-mono text-mono', tone)}>{value}</span>;
  if (!breakdown) return pill;
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  return (
    <Tooltip>
      <TooltipTrigger asChild><span tabIndex={0}>{pill}</span></TooltipTrigger>
      <TooltipContent>
        Required {pct(breakdown.required)} · Typed {pct(breakdown.typed)} · Mapped {pct(breakdown.mapped)}
      </TooltipContent>
    </Tooltip>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { fg, bg } = severityTokens(severity);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chip px-2 text-label font-medium whitespace-nowrap text-ink"
      style={{ background: bg }}>
      <span aria-hidden className="size-1.5 rounded-pill" style={{ background: fg }} />
      {severity}
    </span>
  );
}

export type IntegrityState = 'verified' | 'tampered' | 'mismatch' | 'pending' | 'unknown';
const INTEGRITY = {
  verified: { Icon: ShieldCheck, cls: 'text-int-verified bg-int-verified-bg' },
  tampered: { Icon: ShieldAlert, cls: 'text-int-tampered bg-int-tampered-bg' },
  mismatch: { Icon: ShieldQuestion, cls: 'text-int-mismatch bg-int-mismatch-bg' },
  pending: { Icon: Clock, cls: 'text-int-pending bg-int-pending-bg' },
  unknown: { Icon: ShieldQuestion, cls: 'text-int-pending bg-int-pending-bg' },
} as const;

export function IntegrityBadge({ state, label, className }: { state: IntegrityState; label: string; className?: string }) {
  const { Icon, cls } = INTEGRITY[state];
  return (
    <span className={cn('inline-flex items-center gap-2 rounded-control px-3 py-1.5 text-body font-medium', cls, className)}>
      <Icon className="size-5 shrink-0" aria-hidden />
      {label}
    </span>
  );
}

export function SilenceBadge({ seconds }: { seconds: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chip bg-st-warn-bg px-2 text-label font-medium text-st-warn whitespace-nowrap">
      <BellOff className="size-4" aria-hidden />
      Silent · last event {seconds} s ago
    </span>
  );
}
