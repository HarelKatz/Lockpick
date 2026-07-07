import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { expect, type Page } from '@playwright/test'

const HERE = path.dirname(fileURLToPath(import.meta.url))

/** The op id seeded by global-setup. */
export function seededOpId(): string {
  return readFileSync(path.join(HERE, '.op-id'), 'utf8').trim()
}

/**
 * Land directly on the seeded op's Graph tab, bypassing the OpSelector by
 * injecting the same sessionStorage keys App.tsx reads on boot. Returns the op.
 */
export async function gotoGraph(page: Page) {
  const opId = seededOpId()
  await page.goto('/')
  const ops = await (await page.request.get('/api/ops')).json()
  const op = ops.find((o: { id: string }) => o.id === opId) ?? ops[0]
  await page.evaluate((o) => {
    sessionStorage.setItem('lockpick_selected_op', JSON.stringify(o))
    sessionStorage.setItem(`lockpick_tab_${o.id}`, 'graph')
  }, op)
  await page.reload()
  // The force-graph <canvas> mounts once the graph data loads.
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15_000 })
  // Wait until the graph data has actually rendered (the hook reports nodes),
  // not just the empty initial snapshot.
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const g = (window as unknown as { __lockpick_graph__?: { nodeIds: string[] } }).__lockpick_graph__
          return g ? g.nodeIds.length : 0
        }),
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0)
  return op
}

/**
 * Read the dev-only render-state hook the app exposes on window. Available only
 * when the frontend runs in dev mode (import.meta.env.DEV), which the e2e dev
 * server does. See ARCHITECTURE.md (window.__lockpick_graph__ contract).
 */
export async function graphState(page: Page): Promise<{
  nodeIds: string[]
  highlightedNodeIds: string[]
  visibleEdgeKeys: string[]
  pathAnchorId: string | null
  timeWindow: { start: number; end: number } | null
  timeDomain: { min: number; max: number } | null
}> {
  await expect
    .poll(() => page.evaluate(() => Boolean((window as unknown as { __lockpick_graph__?: unknown }).__lockpick_graph__)), {
      timeout: 10_000,
    })
    .toBe(true)
  return page.evaluate(() => (window as unknown as { __lockpick_graph__: unknown }).__lockpick_graph__ as never)
}

/** Current viewport coords of a host's canvas node (via the hook's screenPos). */
export async function nodeScreenPos(page: Page, hostId: string): Promise<{ x: number; y: number }> {
  const pos = await page.evaluate((id) => {
    const g = (window as unknown as {
      __lockpick_graph__?: { screenPos?: (id: string) => { x: number; y: number } | null }
    }).__lockpick_graph__
    return g?.screenPos ? g.screenPos(id) : null
  }, hostId)
  if (!pos) throw new Error(`no screen position for host ${hostId}`)
  return pos
}

/**
 * Move the pointer onto a node and wait until react-force-graph registers the
 * hover (via the hook's live hoveredNodeId). RFG hit-tests clicks against its
 * hovered node, updated on a rAF after a move — so a bundled mouse.click() would
 * press before the hover is recomputed and miss. Deterministic, no fixed delay.
 */
async function hoverNode(page: Page, hostId: string): Promise<void> {
  const pos = await nodeScreenPos(page, hostId)
  await page.mouse.move(pos.x, pos.y)
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const g = (window as unknown as {
            __lockpick_graph__?: { hoveredNodeId?: () => string | null }
          }).__lockpick_graph__
          return g?.hoveredNodeId ? g.hoveredNodeId() : null
        }),
      { timeout: 5000 },
    )
    .toBe(hostId)
}

/** Click a canvas node (plain). */
export async function clickNode(page: Page, hostId: string): Promise<void> {
  await hoverNode(page, hostId)
  await page.mouse.down()
  await page.mouse.up()
}

/** Shift+click a canvas node (drives the BFS path selection). */
export async function shiftClickNode(page: Page, hostId: string): Promise<void> {
  await hoverNode(page, hostId)
  // mouse.click has no `modifiers` option (that's locator.click); hold Shift on
  // the keyboard around the press instead.
  await page.keyboard.down('Shift')
  await page.mouse.down()
  await page.mouse.up()
  await page.keyboard.up('Shift')
}

/**
 * Wait until the graph is stable AND fitted into view. The sim stopping is not
 * enough: zoomToFit fires ~1s later on engine-stop and changes the transform
 * (graph2ScreenCoords maps raw graph coords until then, landing off-canvas), so
 * we also require the probe node to sit inside the canvas bounds.
 */
export async function waitForGraphSettled(page: Page): Promise<void> {
  const { nodeIds } = await graphState(page)
  const probe = nodeIds[0]
  let prev: { x: number; y: number } | null = null
  await expect
    .poll(
      async () => {
        const cur = await nodeScreenPos(page, probe).catch(() => null)
        const rect = await page.evaluate(() => {
          const c = document.querySelector('canvas')
          if (!c) return null
          const r = c.getBoundingClientRect()
          return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }
        })
        const inView =
          !!cur && !!rect &&
          cur.x >= rect.left && cur.x <= rect.right &&
          cur.y >= rect.top && cur.y <= rect.bottom
        const stable = !!prev && !!cur && Math.abs(prev.x - cur.x) < 1 && Math.abs(prev.y - cur.y) < 1
        prev = cur
        return inView && stable
      },
      { timeout: 15_000, intervals: [300, 300, 300] },
    )
    .toBe(true)
}
