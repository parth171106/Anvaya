import { Toaster as Sonner, type ToasterProps } from 'sonner';

/** Toasts: bottom-right, 420 px, --e-2, --r-panel, 5 s (UI_UX_BRIEF.md §4.2). Light only; there is no dark mode. */
export function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="light"
      position="bottom-right"
      duration={5000}
      visibleToasts={3}
      toastOptions={{
        classNames: {
          toast:
            'w-[420px] rounded-panel border border-rule bg-surface text-ink shadow-e2 font-ui gap-3 p-4 items-start',
          title: 'text-body-lg font-normal text-ink',
          description: 'text-body text-graphite',
          actionButton: 'bg-seal text-on-ink',
        },
      }}
      style={{ '--width': '420px' } as React.CSSProperties}
      {...props}
    />
  );
}
