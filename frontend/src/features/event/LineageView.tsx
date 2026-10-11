// The signature element (UI_UX_BRIEF.md §5.3): raw bytes ↔ OCSF fields, with a connector curve between them.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { buildFields, byteToCharIndex, spanToPath, type OcsfField } from '@/lib/lineage';
import { lineageColor } from '@/lib/tokens';
import type { LineageEntry } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useLineageStore } from '@/state';

export const WRAP = 64;
const WRAP_COMPACT = 40;
const WRAP_MIN = 32;

/** Characters per line: the brief's 64 when the pane is wide enough, fewer in narrower windows (never below 32). */
function useWrap(ref: React.RefObject<HTMLDivElement | null>, max: number): number {
  const [wrap, setWrap] = useState(max);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const probe = document.createElement('span');
    probe.textContent = '0'.repeat(10);
    Object.assign(probe.style, { position: 'absolute', visibility: 'hidden', whiteSpace: 'pre' });
    el.appendChild(probe);
    const update = () => {
      const ch = probe.getBoundingClientRect().width / 10;
      if (ch > 0) setWrap(Math.max(WRAP_MIN, Math.min(max, Math.floor(el.clientWidth / ch))));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => { ro.disconnect(); probe.remove(); };
  }, [ref, max]);
  return wrap;
}
const MARK = { direct: '●', derived: '◇', unmapped: '○', none: '' } as const;

export interface Tamper { offset: number; from: string; to: string; field: string | null }

function fieldColor(f: OcsfField) {
  return f.kind === 'unmapped' ? lineageColor(-1) : lineageColor(f.colorIndex);
}

/** byte offset → char index, and its inverse, for the raw text (identity for ASCII). */
function useOffsets(text: string) {
  return useMemo(() => {
    const toChar = byteToCharIndex(text);
    const bytes = new TextEncoder().encode(text).length;
    const toByte: number[] = [];
    for (let b = 0; b <= bytes; b++) {
      const c = toChar(b);
      if (toByte[c] === undefined) toByte[c] = b;
    }
    return { toChar, toByte: (c: number) => toByte[c] ?? c };
  }, [text]);
}

interface RawBytesPaneProps {
  text: string; activeSpans: [number, number][]; color: { fg: string; bg: string } | null; tamperChar: number | null;
  onHoverChar: (c: number | null) => void; charRefs: React.MutableRefObject<Map<number, HTMLSpanElement>>; compact?: boolean;
  wrap: number; rootRef: React.RefObject<HTMLDivElement | null>;
}

export function RawBytesPane({ text, activeSpans, color, tamperChar, onHoverChar, charRefs, compact, wrap, rootRef }: RawBytesPaneProps) {
  const lines = useMemo(() => {
    const out: string[] = [];
    for (let i = 0; i < text.length; i += wrap) out.push(text.slice(i, i + wrap));
    return out.length ? out : [''];
  }, [text, wrap]);
  const inSpan = (c: number) => activeSpans.some(([s, t]) => s <= c && c < t);
  return (
    <div ref={rootRef} className={cn('relative font-mono text-ink', compact ? 'text-mono' : 'text-mono-lg')} onMouseLeave={() => onHoverChar(null)}>
      {!compact && (
        <div aria-hidden className="relative h-4 select-none" style={{ width: `${wrap}ch` }}>
          {[0, 10, 20, 30, 40, 50, 60].filter((n) => n < wrap).map((n) => (
            <span key={n} className="absolute top-0" style={{ left: `${n}ch` }}>
              <span className="text-ruler text-graphite">{n}</span>
            </span>
          ))}
        </div>
      )}
      <div className="whitespace-pre" role="presentation">
        {lines.map((line, li) => (
          <div key={li} className="leading-[26px]">
            {Array.from(line).map((ch, k) => {
              const c = li * wrap + k;
              const on = color !== null && inSpan(c);
              const prevOn = on && inSpan(c - 1) && k > 0;
              const nextOn = on && inSpan(c + 1) && k < line.length - 1;
              const style: CSSProperties | undefined = on ? {
                background: color.bg,
                boxShadow: [`inset 0 1px 0 ${color.fg}`, `inset 0 -1px 0 ${color.fg}`,
                  !prevOn && `inset 1px 0 0 ${color.fg}`, !nextOn && `inset -1px 0 0 ${color.fg}`].filter(Boolean).join(','),
              } : undefined;
              return (
                <span key={k} ref={(el) => { if (el) charRefs.current.set(c, el); else charRefs.current.delete(c); }}
                  onMouseEnter={() => onHoverChar(c)} style={style}
                  className={cn('transition-colors duration-base',
                    c === tamperChar && 'bg-lin-tampered-bg text-lin-tampered underline decoration-2 underline-offset-4')}>
                  {ch}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function OcsfFieldList({ fields, active, pinned, tamper, onHover, onPin, rowRefs, showMeta }: {
  fields: OcsfField[]; active: string | null; pinned: string | null; tamper: Tamper | null;
  onHover: (p: string | null) => void; onPin: (p: string | null) => void;
  rowRefs: React.MutableRefObject<Map<string, HTMLDivElement>>; showMeta: boolean;
}) {
  return (
    <div role="list" aria-label="Normalized OCSF fields" onMouseLeave={() => onHover(null)}>
      {fields.filter((f) => showMeta || !f.path.startsWith('metadata.')).map((f) => {
        const c = fieldColor(f);
        const isActive = active === f.path;
        const traceable = f.spans.length > 0;
        return (
          <div key={f.path} role="listitem" tabIndex={0} ref={(el) => { if (el) rowRefs.current.set(f.path, el); else rowRefs.current.delete(f.path); }}
            aria-label={`${f.path} ${String(f.value)}`}
            onMouseEnter={() => onHover(f.path)} onFocus={() => onHover(f.path)}
            onClick={() => onPin(pinned === f.path ? null : f.path)}
            onKeyDown={(e) => { if (e.key === 'Enter') onPin(pinned === f.path ? null : f.path); }}
            className={cn('grid cursor-pointer grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_20px] items-baseline gap-3 rounded-control px-2 py-0.5 transition-colors duration-base',
              isActive ? 'bg-paper-sunk' : 'hover:bg-paper-sunk/60', pinned === f.path && 'outline outline-1 outline-ink')}>
            <span className="truncate font-mono text-mono" style={{ color: traceable ? c.fg : 'var(--graphite)' }}>{f.path}</span>
            <span className="truncate font-mono text-mono-lg text-ink">
              {String(f.value)}
              {tamper && tamper.field === f.path && (
                <span className="ml-2 rounded-chip bg-int-tampered-bg px-1.5 font-ui text-label font-medium text-int-tampered">
                  Altered on disk: '{tamper.from}' → '{tamper.to}'
                </span>
              )}
            </span>
            <span aria-hidden className="text-center" style={{ color: c.fg }}>{MARK[f.kind]}</span>
          </div>
        );
      })}
    </div>
  );
}

/** A cubic Bézier from the field row's left edge to the span's line box, drawn with stroke-dashoffset. */
function LineageConnector({ from, to, color }: { from: DOMRect | null; to: DOMRect | null; color: string }) {
  if (!from || !to) return null;
  const x1 = from.left, y1 = from.top + from.height / 2, x2 = to.right + 2, y2 = to.top + to.height / 2;
  const dx = Math.max(24, (x1 - x2) / 2);
  const d = `M ${x1} ${y1} C ${x1 - dx} ${y1}, ${x2 + dx} ${y2}, ${x2} ${y2}`;
  return (
    <svg aria-hidden className="pointer-events-none fixed inset-0 z-10 h-full w-full overflow-visible">
      <path key={d} d={d} fill="none" stroke={color} strokeWidth={1.5} pathLength={1} className="lineage-draw" />
      <circle cx={x2} cy={y2} r={3} fill={color} />
    </svg>
  );
}

export interface LineageViewProps {
  rawText: string; rawBytesLength: number; ocsf: Record<string, unknown>; lineage: LineageEntry[];
  tamper?: Tamper | null; version: string; compact?: boolean;
}

export function LineageView({ rawText, rawBytesLength, ocsf, lineage, tamper = null, version, compact = false }: LineageViewProps) {
  const { hoveredPath, pinnedPath, setHover, setPin, clear } = useLineageStore();
  const active = hoveredPath ?? pinnedPath;
  const fields = useMemo(() => buildFields(ocsf, lineage), [ocsf, lineage]);
  const byPath = useMemo(() => new Map(fields.map((f) => [f.path, f])), [fields]);
  const { toChar, toByte } = useOffsets(rawText);
  const charRefs = useRef(new Map<number, HTMLSpanElement>());
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const listRef = useRef<HTMLDivElement>(null);
  const rawRef = useRef<HTMLDivElement>(null);
  const wrap = useWrap(rawRef, compact ? WRAP_COMPACT : WRAP);
  const [showMeta, setShowMeta] = useState(false);
  const [rects, setRects] = useState<{ from: DOMRect | null; to: DOMRect | null }>({ from: null, to: null });

  useEffect(() => clear, [clear]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setPin(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setPin]);

  const activeField = active ? byPath.get(active) : undefined;
  const charSpans = useMemo<[number, number][]>(
    () => (activeField?.spans ?? []).map(([s, t]) => [toChar(s), toChar(t)]), [activeField, toChar]);
  const color = activeField ? fieldColor(activeField) : null;
  const tamperChar = tamper ? toChar(tamper.offset) : null;

  const measure = useCallback(() => {
    if (compact || !active || !charSpans.length) { setRects({ from: null, to: null }); return; }
    const row = rowRefs.current.get(active);
    const [s, t] = charSpans[0];
    const lineEnd = Math.min(t, (Math.floor(s / wrap) + 1) * wrap);  // the span's first line box
    const first = charRefs.current.get(s), last = charRefs.current.get(lineEnd - 1);
    if (!row || !first || !last) { setRects({ from: null, to: null }); return; }
    const a = first.getBoundingClientRect(), b = last.getBoundingClientRect();
    setRects({ from: row.getBoundingClientRect(), to: new DOMRect(a.left, a.top, b.right - a.left, a.height) });
  }, [active, charSpans, compact, wrap]);

  useLayoutEffect(() => { measure(); }, [measure, showMeta]);
  useEffect(() => {
    if (tamper?.field) rowRefs.current.get(tamper.field)?.scrollIntoView({ block: 'nearest' });
  }, [tamper?.field]);
  useEffect(() => {
    const opts = { passive: true, capture: true } as const;
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, opts);
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, opts); };
  }, [measure]);

  const onHoverChar = (c: number | null) => {
    if (c === null) { setHover(null); return; }
    const path = spanToPath(lineage, toByte(c));
    setHover(path);
    if (path) {
      if (path.startsWith('metadata.') && !showMeta) setShowMeta(true);
      rowRefs.current.get(path)?.scrollIntoView({ block: 'nearest' });
    }
  };

  return (
    <div>
      <div className={cn('grid grid-cols-2 gap-6', compact && 'gap-4')}>
        <section className="min-w-0 rounded-panel border border-rule bg-surface p-5">
          {!compact && <h2 className="mb-3 text-h3 font-semibold">Original bytes, as received ({rawBytesLength} bytes)</h2>}
          <div className="rounded-control bg-paper-sunk p-4">
            <RawBytesPane text={rawText} activeSpans={charSpans} color={color} tamperChar={tamperChar}
              onHoverChar={onHoverChar} charRefs={charRefs} compact={compact} wrap={wrap} rootRef={rawRef} />
          </div>
          {tamper && !compact && (
            <p className="mt-3 text-body text-int-tampered">
              Showing bytes currently in the vault. The copy captured at ingest differs at byte {tamper.offset}.
            </p>
          )}
        </section>
        <section className="min-w-0 rounded-panel border border-rule bg-surface p-5">
          {!compact && (
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-h3 font-semibold">Normalized record · OCSF {version}</h2>
              <button type="button" className="text-label font-medium text-seal hover:underline" onClick={() => setShowMeta((v) => !v)}>
                {showMeta ? 'Hide metadata' : 'Show metadata'}
              </button>
            </div>
          )}
          <div ref={listRef} onScroll={measure} className={cn('overflow-y-auto', compact ? 'max-h-[260px]' : 'max-h-[calc(100vh-610px)] min-h-[260px]')}>
            <OcsfFieldList fields={fields} active={active} pinned={pinnedPath} tamper={tamper} onHover={setHover}
              onPin={setPin} rowRefs={rowRefs} showMeta={showMeta || compact} />
          </div>
        </section>
      </div>
      {!compact && (
        <div className="mt-3 flex items-center justify-between text-body text-graphite">
          <span>Hover any field to see the exact bytes it came from. Click to pin.</span>
          <span>● mapped directly · ◇ derived · ○ kept unmapped</span>
        </div>
      )}
      <LineageConnector from={rects.from} to={rects.to} color={color?.fg ?? 'var(--ink)'} />
    </div>
  );
}
