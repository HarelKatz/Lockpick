import { api } from './client'
import type { ImportResponse } from '../types'

/**
 * Trigger export download by navigating to the endpoint URL.
 * The server returns Content-Disposition: attachment which causes the browser
 * to download the file directly.
 */
export function exportOp(opId: string): void {
  const a = document.createElement('a')
  a.href = `/api/ops/${opId}/export`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export function importOp(data: unknown, nameOverride?: string): Promise<ImportResponse> {
  return api.post<ImportResponse>('/ops/import', {
    mode: 'create_new',
    name_override: nameOverride || undefined,
    data,
  })
}
