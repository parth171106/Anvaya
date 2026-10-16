import { Component, useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export function PageHeader({ title, subtitle, display = false, children }: {
  title: string; subtitle?: ReactNode; display?: boolean; children?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        <h1 className={cn('font-display font-semibold text-ink', display ? 'text-display' : 'text-h1')}>{title}</h1>
        {subtitle && <p className="mt-1 text-body-lg text-graphite">{subtitle}</p>}
      </div>
      {children && <div className="flex min-w-0 max-w-full flex-wrap items-center gap-3">{children}</div>}
    </header>
  );
}

export function Panel({ title, children, className, actions }: {
  title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode;
}) {
  return (
    <section className={cn('min-w-0 rounded-panel border border-rule bg-surface p-4 sm:p-5', className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          {title && <h2 className="text-h2 font-semibold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/** Empty state: icon, H3, one explanatory line, at most one action (UI_UX_BRIEF.md §4.1). */
export function EmptyState({ icon: Icon, title, body, action, className }: {
  icon: LucideIcon; title: string; body: string; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-6 py-12 text-center', className)}>
      <Icon className="size-8 text-muted-foreground" aria-hidden />
      <h3 className="mt-1 text-h3 font-semibold text-ink">{title}</h3>
      <p className="max-w-[560px] text-body text-graphite">{body}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/** Error state: --st-down border, plain words, one line of what to do, Retry. The code goes in the icon's tooltip. */
export function ErrorState({ title, body, onRetry, code, retryLabel = 'Retry', className }: {
  title: string; body?: string; onRetry?: () => void; code?: string; retryLabel?: string; className?: string;
}) {
  return (
    <div role="alert" className={cn('flex flex-wrap items-start gap-4 rounded-panel border border-st-down bg-surface p-5', className)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={code ? 0 : -1} className="mt-0.5"><AlertTriangle className="size-6 text-st-down" aria-hidden /></span>
        </TooltipTrigger>
        {code && <TooltipContent>{code}</TooltipContent>}
      </Tooltip>
      <div className="min-w-0 flex-1">
        <h3 className="text-h3 font-semibold text-ink">{title}</h3>
        {body && <p className="mt-1 text-body text-graphite">{body}</p>}
      </div>
      {onRetry && <Button variant="outline" onClick={onRetry}>{retryLabel}</Button>}
    </div>
  );
}

/** True once `ms` has passed: skeletons only appear after 150 ms, so fast loads never flash. */
export function useDelayed(active: boolean, ms = 150): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) { setShown(false); return; }
    const t = setTimeout(() => setShown(true), ms);
    return () => clearTimeout(t);
  }, [active, ms]);
  return shown;
}

export function Bone({ className }: { className?: string }) {
  return <div aria-hidden className={cn('skeleton-shimmer max-w-full rounded-control', className)} />;
}

export function Skeleton({ show = true, children }: { show?: boolean; children: ReactNode }) {
  const visible = useDelayed(show);
  return visible ? <div aria-busy="true" aria-label="Loading">{children}</div> : null;
}

export class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="p-8">
        <ErrorState title="This screen couldn't be shown." body="Reload the page to try again."
          onRetry={() => window.location.reload()} retryLabel="Reload" />
      </div>
    );
  }
}
