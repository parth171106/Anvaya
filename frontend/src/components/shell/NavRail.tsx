import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Activity, Menu, Gauge, Network, Play, Search, Send, ShieldCheck, Siren, UserRound, type LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';
import { cn } from '@/lib/utils';
import { useIncidentStore, useIntegrityStore, useReplayStore } from '@/state';

interface Item { to: string; label: string; Icon: LucideIcon; badge?: string | number | null; }

export function NavRail({ mobile = false, onNavigate }: { mobile?: boolean; onNavigate?: () => void }) {
  const openIncidents = useIncidentStore((s) => Object.values(s.byId).filter((i) => i.status === 'open').length);
  const quarantined = useReplayStore((s) => s.quarantineTotal);
  const verdict = useIntegrityStore((s) => s.lastVerify?.verdict);
  const items: Item[] = [
    { to: '/overview', label: 'Overview', Icon: Gauge },
    { to: '/feed', label: 'Live feed', Icon: Activity },
    { to: '/incidents', label: 'Incidents', Icon: Siren, badge: openIncidents || null },
    { to: '/replay', label: 'Attack Replay', Icon: Play },
    { to: '/search', label: 'Search', Icon: Search },
    { to: '/integrity', label: 'Integrity', Icon: ShieldCheck, badge: verdict && verdict !== 'verified' ? '✗' : null },
    { to: '/sources', label: 'Sources & parsers', Icon: Network, badge: quarantined || null },
    { to: '/delivery', label: 'Delivery', Icon: Send },
    { to: '/account', label: 'Account', Icon: UserRound },
  ];
  return (
    <nav aria-label="Main" className={cn('shrink-0 flex-col overflow-y-auto bg-nav py-3', mobile ? 'flex w-full' : 'hidden w-[112px] md:flex')}>
      {items.map(({ to, label, Icon, badge }) => (
        <NavLink key={to} to={to} onClick={onNavigate}
          className={({ isActive }) => cn(
            'relative mx-2 flex items-center rounded-control py-3 text-nav text-on-ink transition-colors duration-fast hover:bg-nav-hover',
            mobile ? 'flex-row gap-4 px-5 text-left' : 'flex-col gap-1 px-1 text-center',
            isActive ? 'opacity-100 before:absolute before:inset-y-2 before:-left-2 before:w-[3px] before:bg-seal' : 'opacity-80')}>
          <span className="relative">
            <Icon className="size-6" aria-hidden />
            {badge != null && (
              <span className="absolute -top-2 -right-3 min-w-5 rounded-pill bg-seal px-1 text-center text-[12px] leading-5 font-semibold text-on-seal">
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

export function MobileNavigation() {
  const [open, setOpen] = useState(false);
  return <Sheet open={open} onOpenChange={setOpen}>
    <SheetTrigger asChild><Button variant="outline" size="icon" className="md:hidden" aria-label="Open navigation"><Menu className="size-5" /></Button></SheetTrigger>
    <SheetContent side="left" className="w-[min(320px,90vw)] gap-0 bg-nav text-on-ink">
      <SheetHeader className="px-6 pt-6">
        <SheetTitle className="text-on-ink">ANVAYA</SheetTitle>
        <SheetDescription className="text-on-ink/80">Your evidence workspace</SheetDescription>
      </SheetHeader>
      <NavRail mobile onNavigate={() => setOpen(false)} />
    </SheetContent>
  </Sheet>;
}
