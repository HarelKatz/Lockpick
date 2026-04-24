/**
 * Collection script download + bulk archive import API.
 */
import type { ArchiveImportResult } from '../types'
import { ApiError, BASE_URL } from './client'

/**
 * Trigger a browser download of the static collection script.
 * The backend returns text/x-shellscript with Content-Disposition: attachment.
 */
export function downloadCollectionScript(opId: string): void {
  const a = document.createElement('a')
  a.href = `${BASE_URL}/ops/${opId}/collection-script`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/** Upload a collection-script tarball and dispatch each file through the upload pipeline. */
export async function importArchive(
  opId: string,
  hostId: string,
  file: File,
): Promise<ArchiveImportResult> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${BASE_URL}/ops/${opId}/hosts/${hostId}/import-archive`, {
    method: 'POST',
    body: form,
  })

  if (!res.ok) {
    let errBody: unknown
    try {
      errBody = await res.json()
    } catch {
      errBody = await res.text()
    }
    throw new ApiError(res.status, errBody)
  }

  return res.json() as Promise<ArchiveImportResult>
}
