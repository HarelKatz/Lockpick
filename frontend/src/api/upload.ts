/**
 * File upload API — uses multipart/form-data (not JSON).
 */
import type { UploadFileType, UploadResult } from '../types'
import { ApiError } from './client'

const BASE_URL = '/api'

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
