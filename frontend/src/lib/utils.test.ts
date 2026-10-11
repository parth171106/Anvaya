import { expect, it } from 'vitest';
import { cn } from './utils';

it('keeps custom font sizes and colours apart', () => {
  expect(cn('text-body text-graphite', 'text-body')).toBe('text-graphite text-body');
  expect(cn('text-body text-on-ink')).toBe('text-body text-on-ink');
  expect(cn('text-label', 'text-body-lg')).toBe('text-body-lg');
});
