import { defineConfig, devices } from '@playwright/test';

// `make e2e` runs against the compose stack (nginx on :8080). Set E2E_BASE_URL=http://localhost:5173 for `npm run dev`.
export default defineConfig({
  testDir: 'e2e',
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    viewport: { width: 1920, height: 1080 },
    trace: 'retain-on-failure',
  },
});
