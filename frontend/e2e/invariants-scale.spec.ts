import { test, expect } from '@playwright/test'
import {
  gotoGraph, graphState, waitForGraphSettled, seededScaleOpId,
  allNodesInView, captureConsole,
} from './helpers'

// Heavy graph/layout invariants over a generated scale(50) op — the same layout
// invariants as invariants.spec.ts, but at 50 force-laid-out nodes where floating /
// overflow bugs actually surface. Nightly / on-demand only: this file is the sole
// member of the `chromium-invariants` Playwright project (Phase C splits on the
// `-scale` filename), so it never runs in the fast committed gate.
//
// scale(50) connections are undated → the op has NO time slider, so there are no
// slider-driven steps here.

test.describe('graph/layout invariants (scale 50)', () => {
  test.describe.configure({ timeout: 120_000 })

  test('every visible node is painted within the canvas bounds at scale', async ({ page }) => {
    await gotoGraph(page, seededScaleOpId())
    await waitForGraphSettled(page)
    expect(await allNodesInView(page)).toEqual([])
  })

  test('the page never overflows horizontally at scale', async ({ page }) => {
    await gotoGraph(page, seededScaleOpId())
    await waitForGraphSettled(page)
    const overflow = await page.evaluate(() => {
      const el = document.scrollingElement || document.documentElement
      return el.scrollWidth - el.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(1)
  })

  test('every visible edge endpoint is a real node at scale', async ({ page }) => {
    await gotoGraph(page, seededScaleOpId())
    await waitForGraphSettled(page)
    const { visibleEdgeKeys, nodeIds } = await graphState(page)
    const ids = new Set(nodeIds)
    for (const k of visibleEdgeKeys) {
      const [a, b] = k.split('__')
      expect(ids.has(a) && ids.has(b), `edge ${k} has an endpoint not in nodeIds`).toBe(true)
    }
  })

  test('loading a 50-host graph logs no console or page errors', async ({ page }) => {
    const console_ = captureConsole(page)
    await gotoGraph(page, seededScaleOpId())
    await waitForGraphSettled(page)
    console_.assertClean()
  })
})
