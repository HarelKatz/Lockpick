/**
 * The live-push WebSocket must actually connect.
 *
 * Every write endpoint calls `broadcast_sync` (Architecture Rule #18), but none
 * of that reaches the UI if the socket never opens — and nothing else in the
 * suite notices, because every other spec reloads the page to see new data.
 * The failure is silent: the header pill just sits on "Connecting…" forever.
 *
 * This runs against the dev server, which is where the gap lived: Vite's proxy
 * forwards `/api` HTTP fine but drops the WebSocket upgrade unless `ws: true`
 * is set, so live push was broken for `make dev-frontend` while production
 * nginx (which sets the Upgrade headers) was fine.
 */
import { test, expect } from '@playwright/test'
import { gotoData, seededOpId } from './helpers'

test('the op WebSocket connects and the header reports Live', async ({ page }) => {
  await gotoData(page, seededOpId())
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })
})

test('the WebSocket upgrade survives the dev proxy', async ({ page }) => {
  await gotoData(page, seededOpId())

  // Same-origin socket, i.e. through whatever proxies /api in this environment.
  const outcome = await page.evaluate(
    (opId) =>
      new Promise<string>((resolve) => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws'
        const ws = new WebSocket(`${proto}://${location.host}/api/ops/${opId}/ws`)
        const timer = setTimeout(() => {
          try { ws.close() } catch { /* already dead */ }
          resolve('timeout')
        }, 8000)
        ws.onopen = () => { clearTimeout(timer); ws.close(); resolve('open') }
        ws.onerror = () => { clearTimeout(timer); resolve('error') }
      }),
    seededOpId(),
  )

  expect(outcome).toBe('open')
})

test('a change made elsewhere arrives without a reload', async ({ page }) => {
  await gotoData(page, seededOpId())
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })

  const nickname = `ws-push-probe-${Date.now()}`
  const resp = await page.request.post(`/api/ops/${seededOpId()}/hosts`, {
    data: { nickname },
  })
  expect(resp.status()).toBe(201)
  const hostId = (await resp.json()).id

  try {
    // No page.reload() anywhere — if this appears, the broadcast reached the UI.
    //
    // Scoped to <main>, and that is load-bearing: Workspace keeps BOTH panels
    // mounted and hides the inactive one with `visibility: hidden` (so
    // ForceGraph's ResizeObserver keeps measuring), so a host also renders in
    // the graph panel's filter list. That copy comes first in DOM order, so an
    // unscoped `.first()` selects a permanently-invisible element and this test
    // can never pass — which is exactly how it fooled me into filing a
    // non-existent live-push bug.
    await expect(page.getByRole('main').getByText(nickname, { exact: true })).toBeVisible({ timeout: 15_000 })
  } finally {
    await page.request.delete(`/api/hosts/${hostId}`)
  }
})
