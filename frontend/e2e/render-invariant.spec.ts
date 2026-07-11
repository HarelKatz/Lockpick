import { test, expect, type Page } from '@playwright/test'
import { gotoGraph, graphState, waitForGraphSettled, setRange } from './helpers'

// Render-vs-hook invariant: the canvas must PAINT exactly the set the dev hook
// reports visible (drawn == visible), across time-slider states and a host toggle.
//
// The e2e suite otherwise trusts that the <canvas> paints whatever the data-model
// hook (visibleNodeIds/visibleEdgeKeys) says. Nothing verified that. This locks in
// render↔model fidelity: drawNode/drawLink record what react-force-graph actually
// paints (the lib invokes them only for visibility-passing items, and does not
// viewport-cull), onRenderFramePost publishes the completed frame, and the hook's
// drawnNodeIds()/drawnEdgeKeys() accessors live-read it. Green today; red if a
// future change (autoPauseRedraw flip, a react-force-graph upgrade that caches
// visibility, a draw-path regression) breaks the paint↔model correspondence.

const CONVERGED = { nodesMissing: [], nodesExtra: [], edgesMissing: [], edgesExtra: [] }

/**
 * Poll until the canvas's painted sets set-equal the hook's visible sets. The poll
 * computes, in one in-page eval, the symmetric difference between what the canvas
 * PAINTED last frame (drawnNodeIds/drawnEdgeKeys) and what the model reports visible
 * (visibleNodeIds/visibleEdgeKeys): `*Missing` = visible-but-not-drawn (a stale or
 * broken paint), `*Extra` = drawn-but-not-visible (a visibility change the canvas
 * didn't apply). All four empty ⇒ drawn == visible.
 *
 * Polling absorbs the ≤1-frame paint lag between a model change and the next painted
 * frame; if the canvas never converges (a real render bug) the poll times out and
 * the failure prints the offending ids.
 */
async function expectRenderMatchesHook(page: Page, label: string): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const g = (window as unknown as {
            __lockpick_graph__?: {
              visibleNodeIds: string[]
              visibleEdgeKeys: string[]
              drawnNodeIds?: () => string[]
              drawnEdgeKeys?: () => string[]
            }
          }).__lockpick_graph__
          if (!g || !g.drawnNodeIds || !g.drawnEdgeKeys) return { ready: false }
          const diff = (drawn: string[], visible: string[]) => {
            const ds = new Set(drawn)
            const vs = new Set(visible)
            return {
              missing: visible.filter(x => !ds.has(x)),
              extra: drawn.filter(x => !vs.has(x)),
            }
          }
          const n = diff(g.drawnNodeIds(), g.visibleNodeIds)
          const e = diff(g.drawnEdgeKeys(), g.visibleEdgeKeys)
          return { nodesMissing: n.missing, nodesExtra: n.extra, edgesMissing: e.missing, edgesExtra: e.extra }
        }),
      {
        message: `canvas paint never converged to the hook's visible set at: ${label}`,
        timeout: 10_000,
      },
    )
    .toEqual(CONVERGED)
}

test.describe('render-vs-hook invariant (canvas draws exactly what the hook reports)', () => {
  test('the canvas paints exactly the hook-visible set across time-slider windows', async ({ page }) => {
    await gotoGraph(page)
    await waitForGraphSettled(page)

    // Full window — baseline. Guard against a trivially-empty pass.
    const s0 = await graphState(page)
    expect(s0.visibleNodeIds.length).toBeGreaterThan(0)
    expect(s0.visibleEdgeKeys.length).toBeGreaterThan(0)
    const { min, max } = s0.timeDomain!
    const at = (f: number) => Math.round(min + (max - min) * f)
    await expectRenderMatchesHook(page, 'full window')

    // Right handle narrowed (drop later-dated edges).
    await setRange(page, 'time-end', at(0.5))
    await expect.poll(async () => (await graphState(page)).timeWindow!.end).toBeLessThan(max)
    await expectRenderMatchesHook(page, 'right handle narrowed')

    // Left handle narrowed (also drop earlier-dated edges).
    await setRange(page, 'time-start', at(0.25))
    await expect.poll(async () => (await graphState(page)).timeWindow!.start).toBeGreaterThan(min)
    await expectRenderMatchesHook(page, 'left handle narrowed')

    // A narrow mid-band — the tightest window (set end first so the handles never cross).
    await setRange(page, 'time-end', at(0.6))
    await setRange(page, 'time-start', at(0.4))
    await expect
      .poll(async () => {
        const w = (await graphState(page)).timeWindow!
        return w.start >= at(0.4) - 1 && w.end <= at(0.6) + 1
      })
      .toBe(true)
    const band = await graphState(page)
    expect(band.visibleEdgeKeys.length).toBeGreaterThan(0) // exemptions keep it non-empty
    await expectRenderMatchesHook(page, 'narrow mid-band')

    // Reset restores the full window.
    await page.getByRole('button', { name: 'Reset' }).click()
    await expect
      .poll(async () => {
        const w = (await graphState(page)).timeWindow!
        return w.start === min && w.end === max
      })
      .toBe(true)
    await expectRenderMatchesHook(page, 'after reset')
  })

  test('the canvas paints exactly the hook-visible set when a host is toggled off', async ({ page }) => {
    await gotoGraph(page)
    await waitForGraphSettled(page)

    const fullCount = (await graphState(page)).nodeIds.length
    expect(fullCount).toBeGreaterThan(0)
    await expectRenderMatchesHook(page, 'full host set')

    // Uncheck a connected host in the left list — a non-time visibility driver.
    // The host leaves fgData entirely, shrinking the visible node + edge sets.
    await page.locator('label', { hasText: 'dbserver' }).getByRole('checkbox').uncheck()
    await expect.poll(async () => (await graphState(page)).nodeIds.length).toBeLessThan(fullCount)
    await expectRenderMatchesHook(page, 'host toggled off')
  })
})
