import { defineConfig } from '@playwright/test'

/**
 * Runs against a real backend + real Mongo/Azurite, orchestrated by
 * `make test-e2e` (see Makefile) - not Playwright's own `webServer` option,
 * since the API/Vite/infra startup here is shared with `make dev` and needs
 * seed-reset/seed-dev in between, not just "start a server and wait".
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
