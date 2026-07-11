import { test, expect } from '@playwright/test'
import {
  gotoGraph, graphState, waitForGraphSettled, setRange, shiftClickNode,
  hostIdsByNickname, allNodesInView, captureConsole, assertNoNeighborResize,
} from './helpers'

// Graph/layout invariants over the seeded normal op — the layer the
// window.__lockpick_graph__ DATA hook can't see: canvas bounds, viewport overflow,
// console cleanliness, neighbor-resize, edge-endpoint closure. Fast (11-host seed),
// so it stays in the committed `chromium` project / the gate. The heavy scale(50)
// sweep lives in invariants-scale.spec.ts (nightly `chromium-invariants` only).

test.describe('graph/layout invariants (normal op)', () => {
  test('every visible node is painted within the canvas bounds', async ({ page }) => {
    await gotoGraph(page)
    await waitForGraphSettled(page)
    expect(await allNodesInView(page)).toEqual([])
  })

  test('the page never overflows horizontally', async ({ page }) => {
    await gotoGraph(page)
    await waitForGraphSettled(page)
    const overflow = await page.evaluate(() => {
      const el = document.scrollingElement || document.documentElement
      return el.scrollWidth - el.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(1)
  })

  test('every visible edge endpoint is a real node', async ({ page }) => {
    await gotoGraph(page)
    await waitForGraphSettled(page)
    const { visibleEdgeKeys, nodeIds } = await graphState(page)
    const ids = new Set(nodeIds)
    for (const k of visibleEdgeKeys) {
      const [a, b] = k.split('__')
      expect(ids.has(a) && ids.has(b), `edge ${k} has an endpoint not in nodeIds`).toBe(true)
    }
  })

  test('a scripted interaction sequence logs no console or page errors', async ({ page }) => {
    const console_ = captureConsole(page) // install before navigation
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const id = await hostIdsByNickname(page, op.id)

    // Canvas interaction while the graph is freshly settled: drive a BFS path
    // selection (opens the path detail panel). Same proven sequence as
    // path-highlight.spec.ts, so no fragile settle timing.
    await shiftClickNode(page, id.attackbox)
    await shiftClickNode(page, id.internal)

    // Then interactions that stay clear of the open path panel: drag the slider via
    // setRange (JS-dispatched, so the right-side overlay panel can't intercept it),
    // and toggle a host that is NOT on the selected path (its checkbox is in the
    // left sidebar, clear of the overlay). No canvas click follows the remount.
    const s = await graphState(page)
    if (s.timeDomain) {
      await setRange(page, 'time-end', Math.round((s.timeDomain.min + s.timeDomain.max) / 2))
      await setRange(page, 'time-start', Math.round((s.timeDomain.min + s.timeDomain.max) / 3))
    }
    const webserver = page.locator('label', { hasText: 'webserver' }).getByRole('checkbox')
    await webserver.uncheck()
    await webserver.check()

    console_.assertClean()
  })

  test('the Reset control appearing never resizes the slider track', async ({ page }) => {
    // Generalized form of the time-slider "Reset never resizes the track" invariant,
    // driven through the reusable assertNoNeighborResize helper. (The canvas is a poor
    // neighbor here — a host toggle remounts it via its key — so this uses the slider
    // track, which stays mounted across the Reset toggle.)
    await gotoGraph(page)
    await waitForGraphSettled(page)
    const s = await graphState(page)
    const mid = Math.round((s.timeDomain!.min + s.timeDomain!.max) / 2)
    await setRange(page, 'time-end', mid)
    await expect.poll(async () => (await graphState(page)).timeWindow!.end).toBeLessThan(s.timeDomain!.max)
    await assertNoNeighborResize(
      page,
      page.getByTestId('time-start'),
      () => page.getByRole('button', { name: 'Reset' }).click(),
    )
  })
})
