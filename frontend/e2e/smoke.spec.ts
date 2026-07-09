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

  // 11 hosts seeded (10 in the topology + 1 isolated); all edges visible; nothing
  // highlighted or anchored yet.
  expect(s.nodeIds.length).toBe(11)
  expect(s.highlightedNodeIds).toEqual([])
  expect(s.pathAnchorId).toBeNull()
  expect(s.visibleEdgeKeys.length).toBeGreaterThan(0)
  // Time slider (Phase 2): the window initializes to the full dated domain.
  expect(s.timeDomain).not.toBeNull()
  expect(s.timeWindow).toEqual({ start: s.timeDomain!.min, end: s.timeDomain!.max })
})
