import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { expect, type Locator, type Page } from '@playwright/test'

const HERE = path.dirname(fileURLToPath(import.meta.url))

/** The normal op id seeded by global-setup. */
export function seededOpId(): string {
  return readFileSync(path.join(HERE, '.op-id'), 'utf8').trim()
}

/** The generated scale(50) op id seeded by global-setup (for the invariant suite). */
export function seededScaleOpId(): string {
  return readFileSync(path.join(HERE, '.op-id-scale'), 'utf8').trim()
}

/** The one-host `key_options()` op id seeded by global-setup (Workspace credential rows). */
export function seededKeyOptionsOpId(): string {
  return readFileSync(path.join(HERE, '.op-id-keyopts'), 'utf8').trim()
}

/**
 * Land directly on a seeded op's **Data** tab (the Workspace list panels), the
 * same sessionStorage shortcut `gotoGraph` uses but with the tab key set to
 * 'data'. Waits for the Credentials section to render. Returns the op.
 */
export async function gotoData(page: Page, opId: string) {
  await page.goto('/')
  const ops = await (await page.request.get('/api/ops')).json()
  const op = ops.find((o: { id: string }) => o.id === opId) ?? ops[0]
  await page.evaluate((o) => {
    sessionStorage.setItem('lockpick_selected_op', JSON.stringify(o))
    sessionStorage.setItem(`lockpick_tab_${o.id}`, 'data')
  }, op)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Credentials' })).toBeVisible({ timeout: 15_000 })
  return op
}

/**
 * Land directly on a seeded op's Graph tab, bypassing the OpSelector by injecting
 * the same sessionStorage keys App.tsx reads on boot. Defaults to the normal op;
 * pass `seededScaleOpId()` for the scale fixture. Returns the op.
 */
export async function gotoGraph(page: Page, opId: string = seededOpId()) {
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

/** Map of host nickname → host_id for an op's graph (drives canvas clicks by nickname). */
export async function hostIdsByNickname(page: Page, opId: string): Promise<Record<string, string>> {
  const graph = await (await page.request.get(`/api/ops/${opId}/graph`)).json()
  const map: Record<string, string> = {}
  for (const n of graph.nodes) map[n.nickname] = n.host_id
  return map
}

/**
 * Read the dev-only render-state hook the app exposes on window. Available only
 * when the frontend runs in dev mode (import.meta.env.DEV), which the e2e dev
 * server does. See ARCHITECTURE.md (window.__lockpick_graph__ contract).
 */
export async function graphState(page: Page): Promise<{
  nodeIds: string[]
  visibleNodeIds: string[]
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

/**
 * Drive a controlled range input so React's onChange fires. Setting `.value = x`
 * directly is ignored — React's value tracking defeats it — so we go through the
 * native value setter, then dispatch input+change. (Kept in lockstep with the
 * local copy in time-slider.spec.ts.)
 */
export async function setRange(page: Page, testid: string, value: number): Promise<void> {
  await page.getByTestId(testid).evaluate((el, v) => {
    const input = el as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    setter.call(input, String(v))
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
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

/**
 * Return the ids of visible nodes with no usable rendered position. `requireInCanvas`
 * (default true) also flags nodes outside the canvas bounds; set it false to flag ONLY
 * detached nodes (null / NaN / missing position). Empty ⇒ every visible node is
 * positioned (and, by default, painted in-view).
 *
 * SCOPE: the in-canvas check is only an invariant right after the load-time zoomToFit
 * (call waitForGraphSettled first — the fit shifts the transform ~1s after engine-stop).
 * The app does NOT auto-refit after a filter/host-toggle (GraphCanvas only sets
 * fitNeeded on initial load / layout change), so a reflowed node may legitimately sit
 * off-canvas until the user re-fits — use requireInCanvas:false there and assert only
 * that no node became DETACHED. Also note zoomToFit reframes around every FINITE
 * position, so a far-but-finite node is out of scope either way. The `Number.isFinite`
 * guards are load-bearing: a NaN coordinate passes every `<`/`>` comparison.
 */
export async function allNodesInView(page: Page, opts: { requireInCanvas?: boolean } = {}): Promise<string[]> {
  const requireInCanvas = opts.requireInCanvas ?? true
  return page.evaluate((requireInCanvas) => {
    const g = (window as unknown as {
      __lockpick_graph__?: {
        visibleNodeIds: string[]
        screenPos?: (id: string) => { x: number; y: number } | null
      }
    }).__lockpick_graph__
    const c = document.querySelector('canvas')
    if (!g || !g.screenPos || !c) return ['<no-hook-or-canvas>']
    const r = c.getBoundingClientRect()
    const out: string[] = []
    for (const id of g.visibleNodeIds) {
      const p = g.screenPos(id)
      const detached = !p || !Number.isFinite(p.x) || !Number.isFinite(p.y)
      const outOfCanvas = requireInCanvas && !detached && (p.x < r.left || p.x > r.right || p.y < r.top || p.y > r.bottom)
      if (detached || outOfCanvas) out.push(id)
    }
    return out
  }, requireInCanvas)
}

/**
 * Capture console.error and uncaught pageerror events. Install BEFORE navigation so
 * boot-time errors are caught. `assertClean()` fails with the collected messages.
 * Known-benign browser noise is filtered so it can't flake the gate — chiefly
 * Chromium's intermittent "ResizeObserver loop" message, which fires on legitimate
 * layout changes (e.g. a canvas remount) and is not an app error.
 */
export function captureConsole(page: Page): { errors: string[]; assertClean: () => void } {
  const BENIGN = /ResizeObserver loop/i
  const errors: string[] = []
  const record = (msg: string) => { if (!BENIGN.test(msg)) errors.push(msg) }
  page.on('console', (msg) => {
    if (msg.type() === 'error') record(`console.error: ${msg.text()}`)
  })
  page.on('pageerror', (err) => record(`pageerror: ${String(err)}`))
  return {
    errors,
    assertClean: () =>
      expect(errors, `unexpected console/page errors:\n${errors.join('\n')}`).toEqual([]),
  }
}

/**
 * Assert that running `action` (toggling a control) does not resize a neighboring
 * element — its width must stay within `tol` px. Generalizes the time-slider "Reset
 * never resizes the track" test to any control/neighbor pair (most controls have no
 * testid, so the neighbor is a Locator and the toggle is a caller-supplied action).
 */
export async function assertNoNeighborResize(
  page: Page,
  neighbor: Locator,
  action: () => Promise<void>,
  opts: { tol?: number } = {},
): Promise<void> {
  const tol = opts.tol ?? 1
  const before = (await neighbor.boundingBox())?.width
  if (before == null) throw new Error('assertNoNeighborResize: neighbor has no bounding box')
  await action()
  // Flush a frame so any (buggy) reflow triggered by the action has settled.
  await page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => r())))
  const after = (await neighbor.boundingBox())?.width
  if (after == null) throw new Error('assertNoNeighborResize: neighbor vanished after the action')
  expect(
    Math.abs(after - before),
    `neighbor width changed by ≥${tol}px (${before} → ${after})`,
  ).toBeLessThan(tol)
}
