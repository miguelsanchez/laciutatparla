import { defineConfig, devices } from '@playwright/test';

// The tests run on the site built from the fixture (tests/fixtures/data), never on the real
// data, so they only fail when the web's code changes (arquitectura-agentes.md F4.3–F4.6).
const PORT = 4329;

export default defineConfig({
  testDir: 'tests/e2e',
  snapshotPathTemplate: 'tests/visual/{arg}-{projectName}{ext}',
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
  },
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: 'disabled' },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build:fixture && npx astro preview --outDir dist-fixture --port ${PORT}`,
    url: `http://localhost:${PORT}/cas/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
