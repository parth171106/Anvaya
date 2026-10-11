import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// The brief's type scale (globals.css @theme). Without this, tailwind-merge reads `text-body` etc. as colours and drops
// the real colour class (or the size) when both are passed to cn().
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['display', 'h1', 'h2', 'h3', 'body-lg', 'body', 'label', 'mono', 'mono-lg', 'kpi', 'ruler', 'nav', 'chip'] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
