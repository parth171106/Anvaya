import { useId } from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';

/** A native select works with keyboard, touch, and system appearance changes. */
export function ThemeControl() {
  const { theme, setTheme } = useTheme();
  const id = useId();
  const Icon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor;
  return <div className="inline-flex shrink-0 items-center gap-2 rounded-control border border-rule bg-surface px-2 text-label">
    <Icon aria-hidden className="size-4 text-graphite" />
    <label htmlFor={id} className="sr-only">Appearance</label>
    <select id={id} value={theme ?? 'system'} onChange={e => setTheme(e.target.value)}
      className="h-10 cursor-pointer bg-surface pr-1 text-ink" aria-label="Appearance">
      <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
    </select>
  </div>;
}
