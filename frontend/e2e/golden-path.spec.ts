// Golden-path smoke test at 40× (IMPLEMENTATION_PLAN.md §8.3). Fails on any console error or warning.
import { expect, test } from '@playwright/test';

test('golden path', async ({ page, request }) => {
  const problems: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') problems.push(`${m.type()}: ${m.text()}`); });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));

  expect((await request.post('/api/demo/reset')).ok()).toBeTruthy();
  await request.post('/api/demo/speed', { data: { speed: 40 } });

  // 1. Start the simulation; the incident toast appears within 20 s.
  await page.goto('/overview');
  await page.getByRole('button', { name: 'Start attack simulation' }).click();
  await expect(page).toHaveURL(/\/feed$/);
  await expect(page.getByText('High-risk incident')).toBeVisible({ timeout: 20_000 });

  // 2. Open the incident: Risk 95.
  await page.getByRole('button', { name: 'Open incident' }).click();
  await expect(page.getByText('Risk 95').first()).toBeVisible();
  await expect(page.getByText('Port sweep of 12 ports on 10.2.4.18; 3 IDS scan alerts')).toBeVisible();

  // 3. Search Q1: 17 rows. The script asks it after the scripted phase (TRD.md §12.5: 10:09–10:14).
  await expect.poll(async () => (await (await request.get('/api/stats')).json()).normalized_total,
    { timeout: 60_000 }).toBeGreaterThanOrEqual(207);
  await page.getByRole('link', { name: 'Search' }).click();
  await page.getByRole('button', { name: 'What did 10.2.4.18 do in the last hour?' }).first().click();
  await expect(page.getByText(/^17 rows/)).toBeVisible();

  // 4. Integrity: verified → tamper → 1 failed at byte 153 → re-seal → witnesses disagree.
  await page.getByRole('link', { name: 'Integrity' }).click();
  await page.getByRole('button', { name: 'Verify ledger' }).click();
  await expect(page.getByRole('status').filter({ hasText: /records verified across .* both witness nodes agree/ })).toBeVisible();
  await page.getByRole('button', { name: 'Simulate tamper' }).click();
  await page.getByRole('button', { name: 'Verify ledger' }).click();
  await expect(page.getByRole('alert').filter({ hasText: '1 record failed verification' })).toBeVisible();
  await expect(page.getByText(/byte 153 changed '8' → '9' \(dst_endpoint\.ip\)/)).toBeVisible();
  await page.getByRole('button', { name: 'Simulate insider re-seal' }).click();
  await page.getByRole('button', { name: 'Verify ledger' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'witness nodes disagree on batch 11 onward' })).toBeVisible();

  // 5. Unknown source → draft → tests → approve → 20 records replayed.
  await page.keyboard.press('2');
  await page.goto('/sources?tab=quarantine');
  await expect(page.getByText('Unrecognised source · 20 records')).toBeVisible();
  await page.getByRole('button', { name: 'Draft parser' }).click();
  await page.getByRole('button', { name: 'Run tests' }).click();
  await expect(page.getByText('6/6')).toBeVisible();
  const approve = page.getByRole('button', { name: 'Approve & replay' });
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect(page.getByText(/20 records replayed/)).toBeVisible();
  await page.keyboard.press('Escape');

  // 6. Silence fw01 once it is monitored (FL-09 precondition); the Silent badge appears within 20 s.
  await page.getByRole('tab', { name: 'Devices' }).click();
  const fw01 = page.getByRole('row').filter({ hasText: 'cisco-asa@1.0.0' });
  await expect(fw01.getByText('Active')).toBeVisible({ timeout: 90_000 });
  await page.keyboard.press('3');
  await expect(fw01.getByText(/Silent · last event \d+ s ago/)).toBeVisible({ timeout: 20_000 });

  // 7. No console errors or warnings anywhere on the path.
  expect(problems, problems.join('\n')).toEqual([]);
});
