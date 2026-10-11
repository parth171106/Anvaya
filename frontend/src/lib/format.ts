import type { EventSummary } from './types';

export const DASH = '—';
const TZ = 'Asia/Kolkata';

const hms = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const hm = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
const dayMon = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric' });

/** HH:MM:SS in IST, or "—". */
export function timeIST(ms: number | null | undefined): string {
  return ms == null || !Number.isFinite(ms) ? DASH : hms.format(ms);
}

export function hhmmIST(ms: number | null | undefined): string {
  return ms == null ? DASH : hm.format(ms);
}

/** "29 Sep 2026 21:40" */
export function dateTimeIST(ms: number | null | undefined): string {
  return ms == null ? DASH : `${dayMon.format(ms)} ${hm.format(ms)}`;
}

export function dateIST(ms: number | null | undefined): string {
  return ms == null ? DASH : dayMon.format(ms);
}

export function int(n: number | null | undefined): string {
  return n == null || !Number.isFinite(n) ? DASH : Math.round(n).toLocaleString('en-IN');
}

export function dash(v: string | number | null | undefined): string {
  return v == null || v === '' ? DASH : String(v);
}

export function bytesLabel(n: number): string {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`;
}

export function shortHash(h: string, n = 4): string {
  return h.length > 2 * n ? `${h.slice(0, n)}…${h.slice(-n)}` : h;
}

/** The "Event" column text (UI_UX_BRIEF.md §4.4). */
export function formatEventSummary(e: EventSummary): string {
  if (e.class_uid === 2004) return e.title ?? DASH;
  if (e.class_uid === 3002) {
    if (e.status === 'Failure') return `Login failed · ${dash(e.user_name)}`;
    if (e.status === 'Success') return `Login succeeded · ${dash(e.user_name)}`;
    return DASH;
  }
  if (e.activity_name === 'Traffic') return `Session ${(e.action ?? '').toLowerCase() || DASH}`;
  if (e.action === 'Denied') return 'Connection refused';
  if (e.activity_name === 'Close') return 'Connection closed';
  if (e.activity_name === 'Open' && e.action === 'Allowed') {
    const dir = e.direction ? e.direction.toLowerCase() : '';
    const proto = e.protocol ? e.protocol.toUpperCase() : '';
    const tail = [dir, proto].filter(Boolean).join(' ');
    return tail ? `Connection opened · ${tail}` : 'Connection opened';
  }
  return e.activity_name || DASH;
}

/** "198.51.100.9 → 10.2.4.18:443"; authentication shows the device as the destination. */
export function formatSrcDst(e: EventSummary): string {
  const src = e.src_ip ? `${e.src_ip}` : DASH;
  if (e.class_uid === 3002) return `${src} → ${e.device}`;
  const dst = e.dst_ip ? `${e.dst_ip}${e.dst_port != null ? `:${e.dst_port}` : ''}` : DASH;
  return `${src} → ${dst}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
