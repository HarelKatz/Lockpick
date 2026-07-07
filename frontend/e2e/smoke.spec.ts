import { test, expect } from '@playwright/test'
import { gotoGraph, graphState } from './helpers'

// Phase-0 harness smoke test: proves the whole chain works end-to-end —
// isolated backend + seed + proxied dev frontend + navigation + the dev-only
// render-state hook. Graph *state* is asserted via the window hook (deterministic);
// we deliberately do NOT screenshot the force-directed canvas, whose layout
// varies run-to-run. Reserve toHaveScreenshot for stable UI (toolbar, slider).
test('seeded graph loads and exposes render state', async ({ page }) => {
  await gotoGraph(page)
  const s = await graphState(page)

  // 10 hosts seeded; all edges visible; nothing highlighted or anchored yet.
  expect(s.nodeIds.length).toBe(10)
  expect(s.highlightedNodeIds).toEqual([])
  expect(s.pathAnchorId).toBeNull()
  expect(s.visibleEdgeKeys.length).toBeGreaterThan(0)
  // pathAnchorId/timeWindow/timeDomain are placeholders until Phases 1–2 land.
  expect(s.timeWindow).toBeNull()
})
