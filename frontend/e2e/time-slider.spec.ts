import { test, expect, type Page } from '@playwright/test'
import { gotoGraph, graphState, waitForGraphSettled } from './helpers'

// Time slider: filters connection edges by evidence timestamp. Two exemptions
// are never hidden — key-match edges (structural pivots) and undated edges.
// Seeded dated edges (see tests/e2e/seed_e2e.py + the topology fixtures):
//   6 key-match edges           @ 2026-03-15T14:20  (attackbox/jumpbox/… mesh)
//   pentest_vm→citrix           @ 2026-03-15T14:20
//   citrix→fileserver           @ 2026-03-15T14:20
//   monitoring→jumpbox          @ 2026-03-10T09:00  (manual)
//   webserver→dbserver          @ 2026-03-13T11:30  (manual)
//   fileserver→internal         @ 2026-03-17T15:45  (manual)
//   backup→monitoring           @ 2026-03-21T20:15  (manual)

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

  test('narrowing the end keeps key-match edges even when their date is out of window', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)
    expect(m.keyMatchKeys.length).toBe(6)

    // Window → [03-10 09:00, ~03-11 12:00]: excludes the 03-15 key-match dates.
    await setRange(page, 'time-end', T('2026-03-11T12:00:00Z'))

    await expect
      .poll(async () => (await graphState(page)).visibleEdgeKeys.length)
      .toBe(7)

    const visible = new Set((await graphState(page)).visibleEdgeKeys)
    // All 6 key-match edges survive despite being dated 03-15 (outside the window)
    // — proves the exemption, not just an in-window coincidence.
    for (const k of m.keyMatchKeys) expect(visible).toContain(k)
    // The one in-window dated edge stays; later-dated ones drop out.
    expect(visible).toContain(m.key('monitoring', 'jumpbox'))   // 03-10, in window
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

  test('narrowing the start hides early-dated edges', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const m = await edgeModel(page, op.id)

    // Window → [~03-14 12:00, 03-21 20:15]: drops the 03-10 and 03-13 edges.
    await setRange(page, 'time-start', T('2026-03-14T12:00:00Z'))

    await expect
      .poll(async () => (await graphState(page)).visibleEdgeKeys.length)
      .toBe(10)

    const visible = new Set((await graphState(page)).visibleEdgeKeys)
    for (const k of m.keyMatchKeys) expect(visible).toContain(k)
    expect(visible).not.toContain(m.key('monitoring', 'jumpbox'))   // 03-10
    expect(visible).not.toContain(m.key('webserver', 'dbserver'))   // 03-13
    expect(visible).toContain(m.key('pentest_vm', 'citrix'))        // 03-15
    expect(visible).toContain(m.key('fileserver', 'internal'))      // 03-17
    expect(visible).toContain(m.key('backup', 'monitoring'))        // 03-21
  })
})
