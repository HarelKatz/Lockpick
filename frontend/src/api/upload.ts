/**
 * File upload, listing, and serving API.
 */
import type { UploadFile, UploadFileType, UploadResult } from '../types'
import { ApiError, BASE_URL } from './client'

/** List all uploaded files for an operation. */
export async function listUploads(opId: string): Promise<UploadFile[]> {
  const res = await fetch(`${BASE_URL}/ops/${opId}/uploads`)
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => res.statusText))
  return res.json()
}

/**
 * Returns the URL to view or download a specific uploaded file.
 * Pass download=true for Content-Disposition: attachment (browser save dialog).
 * Default (false) streams inline — useful for fetching text into a viewer modal.
 */
export function uploadFileUrl(opId: string, safeName: string, download = false): string {
  const params = download ? '?download=true' : ''
  return `${BASE_URL}/ops/${opId}/uploads/${encodeURIComponent(safeName)}${params}`
}

export async function uploadFile(
  opId: string,
  file: File,
  fileType: UploadFileType,
  hostId: string,
  username?: string,
): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('file_type', fileType)
  form.append('host_id', hostId)
  if (username) form.append('username', username)

  const res = await fetch(`${BASE_URL}/ops/${opId}/upload`, {
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

  return res.json() as Promise<UploadResult>
}
