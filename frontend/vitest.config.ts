import { defineConfig } from 'vitest/config'

// Unit layer for pure logic extracted from components (src/utils/*.test.ts).
// Node environment — these are pure functions with no DOM. Playwright e2e specs
// (frontend/e2e/*.spec.ts) are a separate suite and are NOT matched here.
export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['src/**/*.test.ts'],
  },
})
