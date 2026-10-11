import type { LineageEntry } from './types';

export type FieldKind = 'direct' | 'derived' | 'unmapped' | 'none';
export interface OcsfField { path: string; value: string | number | boolean; colorIndex: number; kind: FieldKind; spans: [number, number][]; }

/** The lineage path of the narrowest span containing `offset`, or null. */
export function spanToPath(lineage: LineageEntry[], offset: number): string | null {
  let best: { width: number; path: string } | null = null;
  for (const e of lineage) {
    for (const [s, t] of e.spans) {
      if (s <= offset && offset < t && (best === null || t - s < best.width)) best = { width: t - s, path: e.path };
    }
  }
  return best?.path ?? null;
}

/** Flatten an OCSF object into leaf paths using the lineage notation (dots, [i] for arrays). */
export function flattenOcsf(obj: unknown, prefix = ''): { path: string; value: string | number | boolean }[] {
  const out: { path: string; value: string | number | boolean }[] = [];
  if (Array.isArray(obj)) {
    obj.forEach((v, i) => out.push(...flattenOcsf(v, `${prefix}[${i}]`)));
  } else if (obj !== null && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj)) out.push(...flattenOcsf(v, prefix ? `${prefix}.${k}` : k));
  } else if (obj !== null && obj !== undefined) {
    out.push({ path: prefix, value: obj as string | number | boolean });
  }
  return out;
}

const CLASS = ['class_uid', 'class_name', 'category_uid', 'category_name', 'activity_id', 'activity_name', 'type_uid',
  'type_name', 'severity_id', 'severity', 'action_id', 'action', 'disposition_id', 'disposition', 'status_id', 'status',
  'status_detail', 'message'];

function rank(path: string): number {
  if (path.startsWith('unmapped.')) return 6;
  if (path.startsWith('metadata.')) return 5;
  const i = CLASS.indexOf(path);
  if (i >= 0) return 0;
  if (path === 'time' || path === 'time_dt') return 1;
  if (/(^|\.)(src_endpoint|dst_endpoint|connection_info|device)\b/.test(path) || path.startsWith('evidences[')) return 2;
  return 3;
}

/** OCSF order: class fields, time, endpoint fields, class-specific, metadata.*, then unmapped.* (stable). */
export function fieldOrder(paths: string[]): string[] {
  return paths
    .map((p, i) => ({ p, i }))
    .sort((a, b) => rank(a.p) - rank(b.p) || (rank(a.p) === 0 ? CLASS.indexOf(a.p) - CLASS.indexOf(b.p) : 0) || a.i - b.i)
    .map((x) => x.p);
}

const HIDDEN = new Set(['raw_data']);

/** Fields for the lineage view, ordered, with their lineage kind and rotating colour. */
export function buildFields(ocsf: Record<string, unknown>, lineage: LineageEntry[]): OcsfField[] {
  const byPath = new Map(lineage.map((l) => [l.path, l]));
  const leaves = flattenOcsf(ocsf).filter((f) => !HIDDEN.has(f.path) && !f.path.startsWith('observables'));
  const values = new Map(leaves.map((f) => [f.path, f.value]));
  let color = 0;
  return fieldOrder(leaves.map((f) => f.path)).map((path) => {
    const l = byPath.get(path);
    const unmapped = path.startsWith('unmapped.');
    const kind: FieldKind = unmapped ? 'unmapped' : !l ? 'none' : l.derived ? 'derived' : 'direct';
    return { path, value: values.get(path)!, kind, spans: l?.spans ?? [], colorIndex: unmapped ? -1 : l ? color++ : -1 };
  });
}

/** Byte offset → character index for UTF-8 text (identity for ASCII). */
export function byteToCharIndex(text: string): (byte: number) => number {
  if (/^[\x00-\x7F]*$/.test(text)) return (b) => b;
  const map: number[] = [];
  let b = 0;
  for (let i = 0; i < text.length; i++) {
    const cp = text.codePointAt(i)!;
    const len = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
    for (let k = 0; k < len; k++) map[b + k] = i;
    b += len;
    if (cp > 0xffff) i++;
  }
  map[b] = text.length;
  return (byte) => map[byte] ?? text.length;
}
