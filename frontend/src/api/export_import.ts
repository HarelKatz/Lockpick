/**
 * Export and import API for Lockpick operations.
 * Export triggers a browser download; import posts a parsed OpExport object.
 */
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

/**
 * Import a previously exported operation.
 * @param data - Parsed JSON from a Lockpick export file (lockpick_export_version: 1).
 */
export function importOp(data: unknown, nameOverride?: string): Promise<ImportResponse> {
  return api.post<ImportResponse>('/ops/import', {
    mode: 'create_new',
    name_override: nameOverride || undefined,
    data,
  })
}
