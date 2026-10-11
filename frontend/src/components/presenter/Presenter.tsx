import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { timeIST } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useDemoStore, useStatsStore, useStreamStore } from '@/state';

const START_NAV_DELAY_MS = 600;

/** Presenter keys (UI_UX_BRIEF.md §9). Ignored in inputs and with Ctrl/Alt/Meta held. */
export function usePresenterKeys() {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      if (e.ctrlKey || e.altKey || e.metaKey || e.repeat) return;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
      const d = useDemoStore.getState();
      if (!d.demoMode) return;
      const actions: Record<string, () => void> = {
        '`': d.togglePanel,
        '1': () => { void d.startScenario().then((ok) => ok && setTimeout(() => navigate('/feed'), START_NAV_DELAY_MS)); },
        '2': () => void d.injectUnknown(),
        '3': () => void d.toggleSilence('fw01'),
        '4': () => void d.tamper(),
        '5': () => void d.reseal(),
        '6': () => void d.cycleSpeed(),
        '0': () => void d.armOrReset(),
      };
      const act = actions[e.key];
      if (act) {
        e.preventDefault();
        act();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate]);
}

const KEYS: [string, string][] = [
  ['`', 'Toggle this panel'], ['1', 'Start attack simulation'], ['2', 'Inject unknown source (br01)'],
  ['3', 'Silence / resume fw01'], ['4', 'Simulate tamper'], ['5', 'Simulate insider re-seal'],
  ['6', 'Cycle speed 10 → 20 → 40'], ['0 0', 'Reset the demo'],
];

export function PresenterPanel() {
  const d = useDemoStore();
  const stream = useStreamStore((s) => s.status);
  const clock = useStatsStore((s) => s.stats?.clock.now_ms);
  const [viewport, setViewport] = useState(() => `${window.innerWidth}×${window.innerHeight}`);
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const onResize = () => setViewport(`${window.innerWidth}×${window.innerHeight}`);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setArmed(Date.now() < useDemoStore.getState().resetArmedUntil), 200);
    return () => clearInterval(t);
  }, []);
  if (!d.demoMode || !d.panelOpen) return null;
  const row = (k: string, v: string) => (
    <div className="flex justify-between gap-4"><dt className="text-graphite">{k}</dt><dd className="font-mono text-mono">{v}</dd></div>
  );
  return (
    <aside aria-label="Presenter controls"
      className="fixed bottom-4 left-4 z-40 w-[320px] rounded-dialog border border-rule bg-surface p-4 text-label shadow-e2">
      <h2 className="mb-2 text-h3 font-semibold">Presenter</h2>
      {armed && <p role="status" className="mb-2 rounded-control bg-seal-tint px-2 py-1 font-medium text-seal">Press 0 again to reset</p>}
      <dl className="space-y-1">
        {row('Phase', d.phase)}
        {row('Speed', `${d.speed}×`)}
        {row('Scenario clock', timeIST(clock))}
        {row('Stream', stream)}
        {row('send_errors', String(d.sendErrors))}
        {row('Viewport', `Viewport ${viewport}`)}
        {row('Tampered', d.tampered ? 'yes' : 'no')}
        {row('Re-sealed', d.resealed ? 'yes' : 'no')}
        {row('Silenced', d.silenced.length ? d.silenced.map((x) => `${x}: silenced`).join(', ') : 'none')}
        {row('Unknown injected', d.unknownInjected ? 'yes' : 'no')}
      </dl>
      <ul className="mt-3 space-y-0.5 border-t border-rule pt-2">
        {KEYS.map(([k, v]) => (
          <li key={k} className="flex gap-3">
            <kbd className={cn('min-w-8 rounded-chip border border-rule bg-paper-sunk px-1 text-center font-mono')}>{k}</kbd>
            <span className="text-graphite">{v}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
