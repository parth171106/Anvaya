import type { DeviceId, FormatId, Severity } from './types';

const DEVICES = new Set(['fw01', 'ids01', 'vpn01', 'br01']);

export function deviceColor(device: DeviceId | string): string {
  return DEVICES.has(device) ? `var(--dev-${device})` : 'var(--muted)';
}

const FORMATS: Record<FormatId, { label: string; color: string }> = {
  'cisco-asa-syslog': { label: 'Syslog · ASA', color: 'var(--fmt-asa)' },
  'suricata-eve-json': { label: 'JSON · EVE', color: 'var(--fmt-eve)' },
  'fortigate-kv': { label: 'key=value', color: 'var(--fmt-fgt)' },
  'acme-edge-pipe': { label: 'pipe-delimited', color: 'var(--fmt-edge)' },
};

export function formatChip(format: FormatId | 'unknown' | string): { label: string; color: string } {
  return FORMATS[format as FormatId] ?? { label: 'unrecognised', color: 'var(--fmt-unknown)' };
}

const SEV: Record<Severity, string> = {
  Informational: 'info', Low: 'low', Medium: 'medium', High: 'high', Critical: 'critical',
};

export function severityTokens(sev: Severity): { fg: string; bg: string } {
  const k = SEV[sev] ?? 'info';
  return { fg: `var(--sev-${k})`, bg: `var(--sev-${k}-bg)` };
}

export function lineageColor(index: number): { fg: string; bg: string } {
  if (index < 0) return { fg: 'var(--lin-unmapped)', bg: 'var(--lin-unmapped-bg)' };
  const n = (index % 6) + 1;
  return { fg: `var(--lin-${n})`, bg: `var(--lin-${n}-bg)` };
}

export const PRODUCT: Record<string, string> = {
  fw01: 'Cisco ASA', ids01: 'Suricata', vpn01: 'FortiGate', br01: 'Acme EdgeRouter',
};
