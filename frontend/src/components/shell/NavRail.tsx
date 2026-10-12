import { Activity, Gauge, Network, Search, Send, ShieldCheck, Siren, UserRound, type LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';
import { cn } from '@/lib/utils';
import { useIncidentStore, useIntegrityStore, useReplayStore } from '@/state';

interface Item { to: string; label: string; Icon: LucideIcon; badge?: string | number | null; }

export function NavRail() {
  const openIncidents = useIncidentStore((s) => Object.values(s.byId).filter((i) => i.status === 'open').length);
  const quarantined = useReplayStore((s) => s.quarantineTotal);
  const verdict = useIntegrityStore((s) => s.lastVerify?.verdict);
  const items: Item[] = [
    { to: '/overview', label: 'Overview', Icon: Gauge },
    { to: '/feed', label: 'Live feed', Icon: Activity },
    { to: '/incidents', label: 'Incidents', Icon: Siren, badge: openIncidents || null },
    { to: '/search', label: 'Search', Icon: Search },
    { to: '/integrity', label: 'Integrity', Icon: ShieldCheck, badge: verdict && verdict !== 'verified' ? '✗' : null },
    { to: '/sources', label: 'Sources & parsers', Icon: Network, badge: quarantined || null },
    { to: '/delivery', label: 'Delivery', Icon: Send },
    { to: '/account', label: 'Account', Icon: UserRound },
  ];
  return (
    <nav aria-label="Main" className="flex w-[112px] shrink-0 flex-col bg-ink py-3">
      {items.map(({ to, label, Icon, badge }) => (
        <NavLink key={to} to={to}
          className={({ isActive }) => cn(
            'relative mx-2 flex flex-col items-center gap-1 rounded-control px-1 py-3 text-center text-nav text-on-ink transition-colors duration-fast hover:bg-ink-soft',
            isActive ? 'opacity-100 before:absolute before:inset-y-2 before:-left-2 before:w-[3px] before:bg-seal' : 'opacity-80')}>
          <span className="relative">
            <Icon className="size-6" aria-hidden />
            {badge != null && (
              <span className="absolute -top-2 -right-3 min-w-5 rounded-pill bg-seal px-1 text-center text-[12px] leading-5 font-semibold text-on-ink">
                {badge}
              </span>
            )}
          </span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
