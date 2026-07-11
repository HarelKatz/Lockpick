import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// frontend/ (this file's directory) and repo root.
const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '..')

// Dedicated e2e ports + data dir so the suite NEVER collides with a running
// dev/docker stack on 8000/5173 or its DB. Overridable via env.
const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8137'
const FRONTEND_PORT = process.env.E2E_FRONTEND_PORT || '5273'
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const BASE_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const E2E_DATA = path.join(HERE, 'e2e', '.data')

export default defineConfig({
  testDir: path.join(HERE, 'e2e'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 30_000,
  globalSetup: path.join(HERE, 'e2e', 'global-setup.ts'),
  globalTeardown: path.join(HERE, 'e2e', 'global-teardown.ts'),
  // Canvas screenshots settle as the force sim relaxes; allow a small diff.
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      // Fast committed specs — the gate's e2e layer. Includes invariants.spec.ts
      // (normal op); excludes the heavy scale(50) sweep.
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testIgnore: /invariants-scale\.spec\.ts/,
    },
    {
      // Heavy scale(50) graph/layout invariants. Excluded from the fast gate
      // (fast-e2e runs --project=chromium), but still runs in the full `make
      // test-e2e` / `test-full` sweeps and standalone via `make test-scale-e2e`.
      name: 'chromium-invariants',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /invariants-scale\.spec\.ts/,
    },
  ],
  webServer: [
    {
      // Isolated backend: its own port + throwaway DB/uploads. --no-access-log is
      // load-bearing: Playwright pipes the webServer's stdout but does not drain it
      // during globalSetup, so uvicorn's per-request access lines fill the pipe
      // buffer mid-seed and the backend blocks on write (a request appears to hang).
      command: `uv run uvicorn main:app --host 127.0.0.1 --port ${BACKEND_PORT} --no-access-log`,
      cwd: path.join(REPO, 'backend'),
      env: {
        DB_PATH: path.join(E2E_DATA, 'e2e.db'),
        UPLOAD_PATH: path.join(E2E_DATA, 'uploads'),
      },
      url: `${BACKEND_URL}/api/ops`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // Dev frontend on a dedicated port, proxying /api to the e2e backend.
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      cwd: HERE,
      env: { API_PROXY_TARGET: BACKEND_URL },
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
