import { test, expect, type Locator, type Page } from '@playwright/test'
import { gotoData, seededKeyOptionsOpId } from './helpers'

/**
 * Workspace credential-link rows — the `key_options` chip.
 *
 * A CredentialLink parsed from an `authorized_keys` line carries the verbatim
 * option prefix (`command="…",no-pty`, the long AWS/EKS `no-port-forwarding,…`
 * banner, …). Workspace renders it as a `.linkOptions` chip that must CLAMP:
 * one line, ellipsised, full text only in the `title`.
 *
 * This is a pure layout/CSS contract, so `window.__lockpick_graph__` is blind to
 * it (it reports the graph data model, not geometry) — every assertion below
 * measures real geometry: boundingBox, scrollWidth vs clientWidth, and an actual
 * click on the row's action buttons.
 *
 * Substrate: the one-host `profiles.key_options()` op seeded by global-setup from
 * `tests/fixtures/authorized_keys_options`, whose three lines give exactly the
 * three shapes this file needs — no options (the baseline row), a short prefix,
 * and a very long one.
 */

const SHORT_OPTS = 'command="/usr/local/bin/backup",no-pty'
const LONG_OPTS_PREFIX = 'no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command='
/** Must stay in lockstep with `max-width` on `.linkOptions` in Workspace.module.css. */
const CHIP_MAX_WIDTH = 260

const linkRows = (page: Page): Locator => page.locator('[class*="linkRow"]')
const rowWithOpts = (page: Page, titlePrefix: string): Locator =>
  linkRows(page).filter({ has: page.locator(`[class*="linkOptions"][title^="${titlePrefix}"]`) })
const rowWithoutOpts = (page: Page): Locator =>
  linkRows(page).filter({ hasNot: page.locator('[class*="linkOptions"]') })
const chip = (row: Locator): Locator => row.locator('[class*="linkOptions"]')

async function box(l: Locator) {
  const b = await l.boundingBox()
  if (!b) throw new Error('element has no bounding box')
  return b
}

test.describe('Workspace credential-link rows', () => {
  test.beforeEach(async ({ page }) => {
    await gotoData(page, seededKeyOptionsOpId())
    // All three seeded links land on one host, so the rows are siblings.
    await expect(linkRows(page)).toHaveCount(3)
  })

  test('the key_options chip clamps to one ellipsised line instead of wrapping', async ({ page }) => {
    const shortChip = chip(rowWithOpts(page, 'command='))
    const longChip = chip(rowWithOpts(page, LONG_OPTS_PREFIX))

    // The full value lives in the title, verbatim — the chip text is the lossy view.
    await expect(shortChip).toHaveAttribute('title', SHORT_OPTS)
    expect(await longChip.getAttribute('title')).toContain('sleep 10')

    const [sb, lb] = [await box(shortChip), await box(longChip)]

    // 1. Clamped: the long prefix is ~950px of text but the chip never exceeds max-width.
    expect(lb.width).toBeLessThanOrEqual(CHIP_MAX_WIDTH + 1)

    // 2. Truncated, not wrapped: the content genuinely overflows its box horizontally
    //    (so an ellipsis is doing the work) while the box stays exactly one line tall —
    //    identical to the short chip, which fits on one line by construction.
    const { scrollW, clientW } = await longChip.evaluate((el) => ({
      scrollW: el.scrollWidth,
      clientW: el.clientWidth,
    }))
    expect(scrollW).toBeGreaterThan(clientW)
    expect(lb.height).toBeCloseTo(sb.height, 0)

    // 3. Rendered text is a prefix of the full value (the browser paints the ellipsis).
    const painted = (await longChip.innerText()).replace(/…$/, '')
    expect(await longChip.getAttribute('title')).toContain(painted.slice(0, 20))
  })

  test('a link row is the same height with and without the chip', async ({ page }) => {
    const plain = await box(rowWithoutOpts(page))
    const short = await box(rowWithOpts(page, 'command='))
    const long = await box(rowWithOpts(page, LONG_OPTS_PREFIX))

    expect(short.height).toBeCloseTo(plain.height, 0)
    expect(long.height).toBeCloseTo(plain.height, 0)
  })

  test('a link with no key_options renders no chip at all', async ({ page }) => {
    await expect(rowWithoutOpts(page)).toHaveCount(1)
    await expect(page.locator('[class*="linkOptions"]')).toHaveCount(2)
  })

  test('the chip never pushes the row actions out of reach', async ({ page }) => {
    // Narrow window included: the chip must absorb the squeeze (it is the only
    // shrinkable item in the row) rather than shoving the buttons off the edge.
    for (const width of [1280, 900]) {
      await page.setViewportSize({ width, height: 720 })
      // Flush a frame so the reflow has settled before measuring.
      await page.evaluate(() => new Promise<void>((r) => requestAnimationFrame(() => r())))

      const rows = linkRows(page)
      for (let i = 0; i < (await rows.count()); i++) {
        const row = rows.nth(i)
        const rb = await box(row)
        for (const name of ['Edit link', 'Remove link']) {
          const btn = row.getByRole('button', { name })
          const bb = await box(btn)
          expect(bb.x, `${name} @${width}px starts left of the viewport`).toBeGreaterThanOrEqual(0)
          expect(bb.x + bb.width, `${name} @${width}px runs past the viewport`).toBeLessThanOrEqual(width)
          expect(bb.x + bb.width, `${name} @${width}px runs past its own row`).toBeLessThanOrEqual(rb.x + rb.width + 1)
          // Reachable means hit-testable, not merely positioned: nothing (a chip
          // overflowing its clip, a stretched row) may sit on top of the button.
          const onTop = await page.evaluate(
            ([x, y]) => document.elementFromPoint(x, y)?.getAttribute('aria-label') ?? null,
            [bb.x + bb.width / 2, bb.y + bb.height / 2],
          )
          expect(onTop, `${name} @${width}px is covered by another element`).toBe(name)
        }
      }
    }

    // And it really is clickable on the worst row (longest options prefix).
    await page.setViewportSize({ width: 900, height: 720 })
    await rowWithOpts(page, LONG_OPTS_PREFIX).getByRole('button', { name: 'Edit link' }).click()
    await expect(page.getByRole('heading', { name: 'Edit Credential Link' })).toBeVisible()
  })

  test('the chip never overflows its row, the list panel, or the page', async ({ page }) => {
    const rows = linkRows(page)
    for (let i = 0; i < (await rows.count()); i++) {
      const over = await rows.nth(i).evaluate((el) => el.scrollWidth - el.clientWidth)
      expect(over, `link row ${i} scrolls horizontally`).toBeLessThanOrEqual(1)
    }

    const panelOverflow = await rows
      .first()
      .evaluate((el) => {
        const panel = el.closest('[class*="listPanel"]') as HTMLElement
        return panel.scrollWidth - panel.clientWidth
      })
    expect(panelOverflow, 'the credentials list panel scrolls horizontally').toBeLessThanOrEqual(1)

    // Page-level guard at the default desktop width. The chip is the subject here,
    // but the check is deliberately whole-document: a clamp that leaks is only a bug
    // because it makes the PAGE scroll sideways.
    const pageOverflow = await page.evaluate(() => {
      const d = document.scrollingElement!
      return d.scrollWidth - d.clientWidth
    })
    expect(pageOverflow, 'the Data tab scrolls horizontally at 1280px').toBeLessThanOrEqual(1)
  })
})
