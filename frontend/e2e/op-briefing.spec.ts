/**
 * Op summary + briefing fields.
 *
 * These are pure chrome (no canvas), so the `window.__lockpick_graph__` hook is
 * useless here — it is blind to CSS/layout. Everything below asserts DOM
 * visibility and `boundingBox()` geometry, per the pre-flight *Layout /
 * rendering* class.
 *
 * Self-contained: each test creates its own throwaway op through the REST API
 * rather than mutating the shared seeded fixture, so the ops other specs assert
 * on never grow a briefing bar mid-suite.
 */
import { test, expect, type Page } from '@playwright/test'

type Op = { id: string; name: string; summary: string | null; briefing: string | null }

const created: string[] = []

async function createOp(page: Page, fields: Record<string, unknown>): Promise<Op> {
  const resp = await page.request.post('/api/ops', { data: fields })
  expect(resp.status()).toBe(201)
  const op = (await resp.json()) as Op
  created.push(op.id)
  return op
}

/** Land on an op's Workspace, bypassing the OpSelector (same trick as helpers.gotoData). */
async function openOp(page: Page, op: Op) {
  await page.goto('/')
  await page.evaluate((o) => {
    sessionStorage.setItem('lockpick_selected_op', JSON.stringify(o))
    sessionStorage.setItem(`lockpick_tab_${o.id}`, 'data')
  }, op)
  await page.reload()
  await expect(page.getByText(op.name, { exact: true }).first()).toBeVisible({ timeout: 15_000 })
}

const header = (page: Page) => page.locator('header').first()
const briefing = (page: Page) => page.getByTestId('op-briefing')
const summaryChip = (page: Page) => page.getByTestId('op-summary')

test.afterAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL })
  for (const id of created) await ctx.delete(`/api/ops/${id}`)
  await ctx.dispose()
})

test.describe('op summary', () => {
  test('the summary renders in the op header', async ({ page }) => {
    const op = await createOp(page, { name: 'Summary Op', summary: '3 footholds, DC not reached.' })
    await openOp(page, op)
    await expect(summaryChip(page)).toHaveText('3 footholds, DC not reached.')
  })

  test('an op with no summary renders no summary element', async ({ page }) => {
    const op = await createOp(page, { name: 'Bare Op' })
    await openOp(page, op)
    await expect(summaryChip(page)).toHaveCount(0)
  })

  test('the header is the same height with and without a summary', async ({ page }) => {
    const bare = await createOp(page, { name: 'Height Bare', description: 'a description' })
    await openOp(page, bare)
    const bareBox = await header(page).boundingBox()

    const withSummary = await createOp(page, {
      name: 'Height Summary',
      description: 'a description',
      summary: 'a summary that shares the meta row',
    })
    await openOp(page, withSummary)
    const summaryBox = await header(page).boundingBox()

    expect(bareBox).not.toBeNull()
    expect(summaryBox!.height).toBe(bareBox!.height)
  })

  test('a very long summary truncates instead of overflowing the page', async ({ page }) => {
    const long = 'pivoted via jump01 → app02 → db03 '.repeat(80)
    const op = await createOp(page, { name: 'Long Summary', description: 'desc', summary: long })
    await openOp(page, op)

    const box = await summaryChip(page).boundingBox()
    expect(box!.width).toBeLessThanOrEqual(440) // .opSummary max-width 420px + slack

    // Truncated, not wrapped: one line's worth of height.
    expect(box!.height).toBeLessThan(30)

    // And the page itself never scrolls sideways.
    const overflow = await page.evaluate(() => {
      const el = document.documentElement
      return el.scrollWidth - el.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('a multi-line markdown summary still occupies a single header row', async ({ page }) => {
    const op = await createOp(page, {
      name: 'Multiline Summary',
      summary: '- foothold: web01\n- foothold: vpn02\n- blocked: dc01',
    })
    await openOp(page, op)
    const box = await summaryChip(page).boundingBox()
    expect(box!.height).toBeLessThan(30)
  })
})

test.describe('op briefing', () => {
  const BRIEFING = '## Rules of engagement\n\n- No DoS\n- 09:00-17:00 only\n- Report to blue on contact'

  test('an op with no briefing renders no briefing bar', async ({ page }) => {
    const op = await createOp(page, { name: 'No Briefing' })
    await openOp(page, op)
    await expect(briefing(page)).toHaveCount(0)
  })

  test('the briefing is collapsed by default and opens on click', async ({ page }) => {
    const op = await createOp(page, { name: 'Briefed Op', briefing: BRIEFING })
    await openOp(page, op)

    await expect(briefing(page)).toBeVisible()
    await expect(page.getByText('No DoS')).toBeHidden()

    await briefing(page).getByText('Briefing').click()
    await expect(page.getByText('No DoS')).toBeVisible()
  })

  test('the briefing also toggles from the keyboard', async ({ page }) => {
    const op = await createOp(page, { name: 'Keyboard Briefing', briefing: BRIEFING })
    await openOp(page, op)

    await briefing(page).locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByText('No DoS')).toBeVisible()

    await page.keyboard.press('Enter')
    await expect(page.getByText('No DoS')).toBeHidden()
  })

  test('opening the briefing never resizes the header', async ({ page }) => {
    const op = await createOp(page, { name: 'Briefing Reflow', briefing: BRIEFING })
    await openOp(page, op)

    const before = await header(page).boundingBox()
    await briefing(page).getByText('Briefing').click()
    await expect(page.getByText('No DoS')).toBeVisible()
    const after = await header(page).boundingBox()

    expect(after!.height).toBe(before!.height)
  })

  test('a huge briefing scrolls internally and leaves the panel below on screen', async ({ page }) => {
    const huge = Array.from({ length: 400 }, (_, i) => `line ${i}: pivot notes`).join('\n')
    const op = await createOp(page, { name: 'Huge Briefing', briefing: huge })
    await openOp(page, op)

    await briefing(page).getByText('Briefing').click()
    await expect(page.getByText('line 0: pivot notes')).toBeVisible()

    const viewport = page.viewportSize()!
    const box = await briefing(page).boundingBox()
    // max-height: 30vh + the toggle row — the bar must not eat the whole screen.
    expect(box!.height).toBeLessThan(viewport.height * 0.5)

    // The tab content area below still has real height (the graph canvas needs it).
    const panelHeight = await page.evaluate(() => {
      const el = document.querySelector('main')
      return el ? el.getBoundingClientRect().height : 0
    })
    expect(panelHeight).toBeGreaterThan(100)

    // Still no horizontal page overflow, even with long unbroken lines.
    const overflow = await page.evaluate(() => {
      const el = document.documentElement
      return el.scrollWidth - el.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
