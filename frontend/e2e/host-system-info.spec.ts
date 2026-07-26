/**
 * Host OS / kernel inventory metadata in the host detail sidebar.
 *
 * These are free-text fields an operator can paste anything into (a full
 * `uname -a` line, a distro string with no break opportunities), and the
 * sidebar is a narrow fixed-width panel — so the risk is layout, not data.
 * `window.__lockpick_graph__` is blind to CSS, so everything here measures real
 * geometry.
 *
 * Uses the shared seeded op but always restores the fields to null afterwards,
 * so no other spec sees a host with a System section.
 */
import { test, expect, type Page } from '@playwright/test'
import { clickNode, gotoGraph, hostIdsByNickname, seededOpId, waitForGraphSettled } from './helpers'

const OS = 'Ubuntu 22.04.3 LTS'
const KERNEL = '5.15.0-88-generic'
/**
 * A single unbreakable token — no spaces, hyphens or slashes. Deliberate: with
 * any of those the browser already has a break opportunity and wraps on its
 * own, so a string containing them would pass this test whether or not the CSS
 * is there (verified — it did).
 */
const LONG_KERNEL = 'x'.repeat(120)

const sidebar = (page: Page) => page.getByTestId('host-system')

async function setSystemFields(page: Page, hostId: string, fields: Record<string, string | null>) {
  const resp = await page.request.patch(`/api/hosts/${hostId}`, { data: fields })
  expect(resp.ok()).toBeTruthy()
}

async function openFirstHost(page: Page): Promise<string> {
  const ids = await hostIdsByNickname(page, seededOpId())
  const hostId = Object.values(ids)[0]
  return hostId
}

test.describe('host system info', () => {
  let hostId: string

  test.beforeEach(async ({ page }) => {
    await gotoGraph(page)
    hostId = await openFirstHost(page)
  })

  test.afterEach(async ({ page }) => {
    await setSystemFields(page, hostId, { os_version: null, kernel_version: null })
  })

  test('the System section is absent until OS or kernel is set', async ({ page }) => {
    await waitForGraphSettled(page)
    await clickNode(page, hostId)
    await expect(sidebar(page)).toHaveCount(0)
  })

  test('OS and kernel render in the host sidebar once set', async ({ page }) => {
    await setSystemFields(page, hostId, { os_version: OS, kernel_version: KERNEL })
    await gotoGraph(page)
    await waitForGraphSettled(page)
    await clickNode(page, hostId)

    await expect(sidebar(page)).toBeVisible()
    await expect(sidebar(page)).toContainText(OS)
    await expect(sidebar(page)).toContainText(KERNEL)
  })

  test('only the field that is set renders a row', async ({ page }) => {
    await setSystemFields(page, hostId, { os_version: OS, kernel_version: null })
    await gotoGraph(page)
    await waitForGraphSettled(page)
    await clickNode(page, hostId)

    await expect(sidebar(page)).toBeVisible()
    await expect(sidebar(page)).toContainText(OS)
    await expect(sidebar(page)).not.toContainText('kernel')
  })

  test('a long unbroken value wraps inside the sidebar instead of overflowing it', async ({ page }) => {
    await setSystemFields(page, hostId, { os_version: OS, kernel_version: LONG_KERNEL })
    await gotoGraph(page)
    await waitForGraphSettled(page)
    await clickNode(page, hostId)

    const section = sidebar(page)
    await expect(section).toBeVisible()

    // The value stays within its own section box…
    const chip = section.locator('[class*="sysValue"]').last()
    const chipBox = (await chip.boundingBox())!
    const sectionBox = (await section.boundingBox())!
    expect(chipBox.x + chipBox.width).toBeLessThanOrEqual(sectionBox.x + sectionBox.width + 1)

    // …by wrapping (taller than the single-line OS row), not by running off.
    const osChip = section.locator('[class*="sysValue"]').first()
    const osBox = (await osChip.boundingBox())!
    expect(chipBox.height).toBeGreaterThan(osBox.height)

    // And the page itself still never scrolls sideways.
    const overflow = await page.evaluate(() => {
      const el = document.documentElement
      return el.scrollWidth - el.clientWidth
    })
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
