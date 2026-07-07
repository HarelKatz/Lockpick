import { test, expect } from '@playwright/test'
import { gotoGraph, graphState, clickNode, shiftClickNode, waitForGraphSettled } from './helpers'

// Exemplar spec for the frontend-verify standard: drives a real canvas
// interaction (shift+click) and asserts graph state via window.__lockpick_graph__,
// never pixels. Path in the seeded topology: attackbox → jumpbox → dbserver → internal.
test.describe('shift+click BFS path highlight', () => {
  async function nickToId(page: import('@playwright/test').Page, opId: string) {
    const graph = await (await page.request.get(`/api/ops/${opId}/graph`)).json()
    const map: Record<string, string> = {}
    for (const n of graph.nodes) map[n.nickname] = n.host_id
    return map
  }

  test('anchors the first host, then highlights the path to the second', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const id = await nickToId(page, op.id)
    const expectedPath = [id.attackbox, id.jumpbox, id.dbserver, id.internal].sort()

    // First shift+click → anchor set, nothing highlighted yet.
    await shiftClickNode(page, id.attackbox)
    await expect.poll(async () => (await graphState(page)).pathAnchorId).toBe(id.attackbox)
    expect((await graphState(page)).highlightedNodeIds).toEqual([])

    // Second shift+click → BFS path highlighted, anchor cleared.
    await shiftClickNode(page, id.internal)
    await expect
      .poll(async () => [...(await graphState(page)).highlightedNodeIds].sort())
      .toEqual(expectedPath)
    expect((await graphState(page)).pathAnchorId).toBeNull()
  })

  test('a plain click clears a pending anchor', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const id = await nickToId(page, op.id)

    await shiftClickNode(page, id.attackbox)
    await expect.poll(async () => (await graphState(page)).pathAnchorId).toBe(id.attackbox)

    // A plain (no-shift) click abandons the pending anchor — no path is highlighted.
    await clickNode(page, id.jumpbox)
    await expect.poll(async () => (await graphState(page)).pathAnchorId).toBeNull()
    expect((await graphState(page)).highlightedNodeIds).toEqual([])
  })
})
