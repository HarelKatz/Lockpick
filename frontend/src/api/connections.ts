/**
 * API functions for ConnectionRecords.
 */
import { api } from './client'
import type { ConnectionRecord, CreateConnectionRequest, UpdateConnectionRequest } from '../types'

export async function listConnections(opId: string): Promise<ConnectionRecord[]> {
  return api.get<ConnectionRecord[]>(`/ops/${opId}/connections`)
}

export async function createConnection(
  opId: string,
  data: CreateConnectionRequest,
): Promise<ConnectionRecord> {
  return api.post<ConnectionRecord>(`/ops/${opId}/connections`, data)
}

export async function updateConnection(connectionId: string, data: UpdateConnectionRequest): Promise<ConnectionRecord> {
  return api.patch<ConnectionRecord>(`/connections/${connectionId}`, data)
}

export async function deleteConnection(connectionId: string): Promise<void> {
  return api.delete(`/connections/${connectionId}`)
}
