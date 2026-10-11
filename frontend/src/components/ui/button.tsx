import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';
import { cn } from '@/lib/utils';

// Buttons: 15 px label, ≥ 40 px targets, the global 2 px seal focus ring (UI_UX_BRIEF.md §2.6, §10).
const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-control text-body font-medium whitespace-nowrap transition-colors duration-fast ease-standard disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: 'bg-seal text-on-ink hover:bg-seal-hover',
        destructive: 'bg-int-tampered text-on-ink hover:bg-int-tampered/90',
        outline: 'border border-rule bg-surface text-ink hover:bg-paper-sunk',
        secondary: 'bg-paper-sunk text-ink hover:bg-rule/60',
        ghost: 'text-ink hover:bg-paper-sunk',
        link: 'text-seal underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 has-[>svg]:px-3',
        sm: 'h-10 gap-1.5 px-3',
        lg: 'h-11 px-6',
        icon: 'size-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

function Button({
  className,
  variant = 'default',
  size = 'default',
  asChild = false,
  ...props
}: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : 'button';
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
