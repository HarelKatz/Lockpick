import { test, expect } from '@playwright/test'
import { gotoGraph, waitForGraphSettled, clickNode, hostIdsByNickname } from './helpers'

// Interaction-modes regression: the "Add note" action fires from an onClick
// button AND from Ctrl/Cmd+Enter on the textarea, both calling one shared
// handleAddNote. Guarded only by async React state, rapid same-tick activation
// dispatches concurrent POSTs → duplicate notes. Drives the REAL keyboard input
// (5 synchronous Ctrl+Enter keydowns) and asserts exactly one note is created.
test.describe('host notes double-submit guard', () => {
  test('rapid Ctrl+Enter on the note input creates exactly one note', async ({ page }) => {
    const op = await gotoGraph(page)
    await waitForGraphSettled(page)
    const ids = await hostIdsByNickname(page, op.id)
    const hostId = ids.attackbox

    // Open the host detail sidebar, then the Notes tab.
    await clickNode(page, hostId)
    await page.getByRole('button', { name: 'Notes', exact: true }).click()

    const textarea = page.getByPlaceholder('Add a note…')
    await expect(textarea).toBeVisible()

    // Capture create POSTs BEFORE firing the input.
    const notePosts: string[] = []
    page.on('response', (resp) => {
      const req = resp.request()
      if (req.method() === 'POST' && /\/hosts\/[^/]+\/notes$/.test(req.url())) {
        notePosts.push(req.url())
      }
    })

    await textarea.fill('pivoted via reused key')
    // Fire 5 synchronous Ctrl+Enter keydowns in ONE tick — the real double-submit
    // shape (a controlled setState path can't reproduce it).
    await textarea.evaluate((el) => {
      for (let i = 0; i < 5; i++) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
      }
    })

    // At least one POST fires...
    await expect.poll(() => notePosts.length, { timeout: 5000 }).toBeGreaterThan(0)
    // ...let any late duplicate POST land...
    await page.waitForTimeout(500)
    // ...and exactly one should have.
    expect(notePosts.length).toBe(1)

    const notes = await (await page.request.get(`/api/hosts/${hostId}/notes`)).json()
    expect(notes.length).toBe(1)
  })
})
