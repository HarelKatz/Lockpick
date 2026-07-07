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
