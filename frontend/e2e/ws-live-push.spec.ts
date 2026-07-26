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

// KNOWN GAP — kept as an executable repro, not a gate.
//
// With the proxy fixed the socket connects and reports "Live", but a host
// created from another client does not appear in the Data tab within 15s.
// `Workspace.tsx` handles the event (250ms debounce → `fetchAll(true)` +
// `graphReloadRef`), so the socket opening is evidently not sufficient — the
// event either is not delivered or does not reach that handler. Seen to work
// exactly once out of five runs, so it is not a pure timing margin.
//
// Diagnose with systematic-debugging before flipping this on; see TODO.md
// "Live push connects but the Data tab does not refresh".
test.fixme('a change made elsewhere arrives without a reload', async ({ page }) => {
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
    // .first(): a host renders in both the filter panel and the host grid.
    await expect(page.getByText(nickname, { exact: true }).first()).toBeVisible({ timeout: 15_000 })
  } finally {
    await page.request.delete(`/api/hosts/${hostId}`)
  }
})
