import { test, expect, type Page } from '@playwright/test'
import { gotoGraph, graphState, waitForGraphSettled } from './helpers'

// Time slider: filters connection edges by evidence timestamp. Two exemptions are
// NEVER hidden — key-match edges (structural pivots) and undated edges. Seeded graph
// (tests/e2e/seed_e2e.py + the topology fixtures) = 13 edges:
//   6 key-match edges           @ 2026-03-15T14:20  (attackbox/jumpbox/… mesh)
//   pentest_vm→citrix           @ 2026-03-15T14:20
//   citrix→fileserver           @ 2026-03-15T14:20
//   monitoring→jumpbox          @ 2026-03-10T09:00  (manual, = domain min)
//   webserver→dbserver          @ 2026-03-13T11:30  (manual)
//   fileserver→internal         @ 2026-03-17T15:45  (manual)
//   backup→monitoring           @ 2026-03-21T20:15  (manual, = domain max)
//   monitoring→webserver        (manual, NO timestamp → the undated exemption)

/** Drive a controlled range input so React's onChange fires (native value setter
 *  defeats React's value tracking; a plain .value = x would be ignored). */
async function setRange(page: Page, testid: string, value: number): Promise<void> {
  await page.getByTestId(testid).evaluate((el, v) => {
    const input = el as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
    setter.call(input, String(v))
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
}

interface Edge { src_host_id: string; dst_host_id: string; evidence: { type: string; timestamp: string | null }[] }

/** Classify the seeded graph: edge keys by nickname, key-match keys, dated span. */
async function edgeModel(page: Page, opId: string) {
  const graph = await (await page.request.get(`/api/ops/${opId}/graph`)).json()
  const idOf: Record<string, string> = {}
  for (const n of graph.nodes) idOf[n.nickname] = n.host_id
  const key = (a: string, b: string) => `${idOf[a]}__${idOf[b]}`
  const keyMatchKeys = (graph.edges as Edge[])
    .filter(e => e.evidence.some(ev => ev.type === 'key_match'))
    .map(e => `${e.src_host_id}__${e.dst_host_id}`)
  const allTimes = (graph.edges as Edge[])
    .flatMap(e => e.evidence.map(ev => ev.timestamp))
    .filter((t): t is string => Boolean(t))
    .map(t => Date.parse(t))
  return {
    key,
    id: (nick: string) => idOf[nick],
    keyMatchKeys,
    edgeCount: graph.edges.length as number,
    domainMin: Math.min(...allTimes),
    domainMax: Math.max(...allTimes),
  }
}

const T = (iso: string) => Date.parse(iso)

test.describe('graph time slider', () => {
  test('exposes the full dated domain with every edge visible', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    const s = await graphState(page)
    expect(s.timeDomain).toEqual({ min: m.domainMin, max: m.domainMax })
    // Window initializes to the full domain — nothing filtered yet.
    expect(s.timeWindow).toEqual({ start: m.domainMin, end: m.domainMax })
    expect(new Set(s.visibleEdgeKeys).size).toBe(m.edgeCount)
  })

  test('narrowing the end keeps key-match + undated edges even when their date is out of window', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)
    expect(m.keyMatchKeys.length).toBe(6)

    // Window → [03-10 09:00, ~03-11 12:00]: excludes the 03-15 key-match dates.
    await setRange(page, 'time-end', T('2026-03-11T12:00:00Z'))

    // 6 key-match + 1 undated (both exempt) + monitoring→jumpbox (03-10, in window) = 8.
    await expect
      .poll(async () => (await graphState(page)).visibleEdgeKeys.length)
      .toBe(8)

    const visible = new Set((await graphState(page)).visibleEdgeKeys)
    // Key-match edges survive despite being dated 03-15 (outside the window) — proves
    // the exemption, not an in-window coincidence.
    for (const k of m.keyMatchKeys) expect(visible).toContain(k)
    // The undated edge is shown regardless of the window (the second exemption).
    expect(visible).toContain(m.key('monitoring', 'webserver'))
    // The one in-window dated edge stays; later-dated ones drop out.
    expect(visible).toContain(m.key('monitoring', 'jumpbox'))       // 03-10, in window
    expect(visible).not.toContain(m.key('webserver', 'dbserver'))   // 03-13
    expect(visible).not.toContain(m.key('pentest_vm', 'citrix'))    // 03-15
    expect(visible).not.toContain(m.key('citrix', 'fileserver'))    // 03-15
    expect(visible).not.toContain(m.key('fileserver', 'internal'))  // 03-17
    expect(visible).not.toContain(m.key('backup', 'monitoring'))    // 03-21

    // Reset restores the full graph.
    await page.getByRole('button', { name: 'Reset' }).click()
    await expect
      .poll(async () => (await graphState(page)).visibleEdgeKeys.length)
      .toBe(m.edgeCount)
  })

  test('narrowing the start hides early-dated edges but keeps exempt edges', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    // Window → [~03-14 12:00, 03-21 20:15]: drops the 03-10 and 03-13 edges.
    await setRange(page, 'time-start', T('2026-03-14T12:00:00Z'))

    // 6 key-match + 1 undated + 4 in-window dated (03-15,03-15,03-17,03-21) = 11.
    await expect
      .poll(async () => (await graphState(page)).visibleEdgeKeys.length)
      .toBe(11)

    const visible = new Set((await graphState(page)).visibleEdgeKeys)
    for (const k of m.keyMatchKeys) expect(visible).toContain(k)
    expect(visible).toContain(m.key('monitoring', 'webserver'))     // undated exemption
    expect(visible).not.toContain(m.key('monitoring', 'jumpbox'))   // 03-10
    expect(visible).not.toContain(m.key('webserver', 'dbserver'))   // 03-13
    expect(visible).toContain(m.key('pentest_vm', 'citrix'))        // 03-15
    expect(visible).toContain(m.key('fileserver', 'internal'))      // 03-17
    expect(visible).toContain(m.key('backup', 'monitoring'))        // 03-21
  })

  test('narrowing hides hosts left with no in-window connection', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    // Full window: every host visible.
    expect((await graphState(page)).visibleNodeIds.length).toBe(10)

    // Window → [03-10 09:00, ~03-11 12:00]: pentest_vm/citrix/fileserver connect only
    // via 03-15/03-17 edges, so they lose every visible edge and must disappear.
    await setRange(page, 'time-end', T('2026-03-11T12:00:00Z'))
    await expect.poll(async () => (await graphState(page)).visibleNodeIds.length).toBe(7)

    const vis = new Set((await graphState(page)).visibleNodeIds)
    expect(vis.has(m.id('pentest_vm'))).toBe(false)
    expect(vis.has(m.id('citrix'))).toBe(false)
    expect(vis.has(m.id('fileserver'))).toBe(false)
    // Key-match-connected hosts stay put.
    expect(vis.has(m.id('jumpbox'))).toBe(true)
    expect(vis.has(m.id('backup'))).toBe(true)

    // Reset brings every host back.
    await page.getByRole('button', { name: 'Reset' }).click()
    await expect.poll(async () => (await graphState(page)).visibleNodeIds.length).toBe(10)
  })

  test('the Reset control never resizes the slider track (no drag jitter)', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)
    const trackWidth = async () => (await page.getByTestId('time-start').boundingBox())!.width

    // At full range the Reset button is hidden but its space is reserved.
    const full = await trackWidth()
    // Narrowing reveals Reset; the track must keep the SAME width, otherwise the
    // dragged thumb's pixel↔value mapping shifts under the cursor and the bar jitters.
    await setRange(page, 'time-end', T('2026-03-13T00:00:00Z'))
    await expect.poll(async () => (await graphState(page)).timeWindow!.end).toBeLessThan(m.domainMax)
    expect(Math.abs((await trackWidth()) - full)).toBeLessThan(1)
  })

  test('a window collapsed onto the top instant can still be widened (no soft-lock)', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    // Drive one handle fully right → window collapses to [max, max] (both handles pile
    // onto the max edge). The reachable (DOM-top) handle must still widen it, not no-op.
    await setRange(page, 'time-start', m.domainMax)
    await expect.poll(async () => (await graphState(page)).timeWindow!.start).toBe(m.domainMax)

    await setRange(page, 'time-end', m.domainMin)
    await expect.poll(async () => (await graphState(page)).timeWindow!.start).toBe(m.domainMin)
    expect(await graphState(page).then(s => s.timeWindow)).toEqual({ start: m.domainMin, end: m.domainMax })
  })

  test('the latest-dated edge stays reachable at the top of the range (step snap)', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    // A drag lands one ms short of max (browsers snap to a grid point below max). The
    // handler must snap up to max so the edge dated exactly at max isn't dropped.
    await setRange(page, 'time-end', m.domainMax - 1)
    await expect.poll(async () => (await graphState(page)).timeWindow!.end).toBe(m.domainMax)
    expect(new Set((await graphState(page)).visibleEdgeKeys)).toContain(m.key('backup', 'monitoring'))
  })

  test('a domain shift disjoint from the window resets to the full new domain', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const s0 = await graphState(page)
    const oldMax = s0.timeDomain!.max

    // Collapse the window onto the latest instant.
    await setRange(page, 'time-start', oldMax)
    await expect.poll(async () => (await graphState(page)).timeWindow!.start).toBe(oldMax)

    // Deselect the host owning the latest-dated edge → the domain shrinks below the
    // window, which is now entirely disjoint from the new domain.
    await page.locator('label', { hasText: 'backup' }).getByRole('checkbox').uncheck()
    await expect
      .poll(async () => (await graphState(page)).timeDomain?.max ?? oldMax, { timeout: 15_000 })
      .toBeLessThan(oldMax)

    // The clamp resets to the full new domain rather than collapsing to a zero-width point.
    const s1 = await graphState(page)
    expect(s1.timeWindow).toEqual({ start: s1.timeDomain!.min, end: s1.timeDomain!.max })
  })
})
