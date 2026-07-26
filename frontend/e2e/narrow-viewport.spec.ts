/**
 * The app must never scroll sideways.
 *
 * A horizontal page scrollbar is the layout failure mode nothing else here
 * catches: `window.__lockpick_graph__` is blind to CSS, and every other spec
 * runs at the default 1280px where the overflow is hidden by sheer width.
 * These run the seeded op at progressively narrower viewports and assert on
 * real geometry, naming the offending elements when they fail.
 */
import { test, expect, type Page } from '@playwright/test'
import { gotoData, gotoGraph, seededOpId, waitForGraphSettled } from './helpers'

/** Widths a laptop/split-screen operator actually hits. */
const WIDTHS = [1024, 800, 700, 500]

/**
 * Page-level horizontal overflow plus the elements responsible — any element
 * whose right edge runs past the document's client width. Reported so a failure
 * says *what* overflowed, not just that something did.
 */
async function overflow(page: Page) {
  return page.evaluate(() => {
    const doc = document.documentElement
    const limit = doc.clientWidth
    const offenders: { tag: string; cls: string; right: number }[] = []
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      // Only report the innermost offenders — a parent is guilty via its child.
      if (r.right > limit + 1 && !Array.from(el.children).some((c) => c.getBoundingClientRect().right > limit + 1)) {
        offenders.push({ tag: el.tagName.toLowerCase(), cls: el.className?.toString().slice(0, 60), right: Math.round(r.right) })
      }
    }
    return { px: doc.scrollWidth - doc.clientWidth, limit, offenders: offenders.slice(0, 8) }
  })
}

test.describe('no horizontal overflow', () => {
  for (const width of WIDTHS) {
    test(`the Data tab never scrolls sideways at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await gotoData(page, seededOpId())
      const o = await overflow(page)
      expect(o.px, `offenders: ${JSON.stringify(o.offenders)}`).toBeLessThanOrEqual(0)
    })

    test(`the Graph tab never scrolls sideways at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await gotoGraph(page)
      await waitForGraphSettled(page)
      const o = await overflow(page)
      expect(o.px, `offenders: ${JSON.stringify(o.offenders)}`).toBeLessThanOrEqual(0)
    })
  }
})
