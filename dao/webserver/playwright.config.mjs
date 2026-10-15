import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  testDir: './tests/browser',
  outputDir: '../../.local/frontend-test-results',
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    cwd: fileURLToPath(new URL('../..', import.meta.url)),
    command: '.venv/bin/python tests/frontend_fixture.py',
    url: 'http://127.0.0.1:8765/v2/tasks',
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
