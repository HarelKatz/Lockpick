/**
 * API functions for graph endpoints.
 */
import { api } from './client'
import type { GraphResponse, PathFinderRequest, PathFinderResponse } from '../types'

export async function fetchGraph(
  opId: string,
  hostIds?: string[],
): Promise<GraphResponse> {
  const params =
    hostIds && hostIds.length > 0 ? `?host_ids=${hostIds.join(',')}` : ''
  return api.get<GraphResponse>(`/ops/${opId}/graph${params}`)
}

export async function expandHost(
  opId: string,
  hostId: string,
  evidenceType: 'all' | 'key_match' | 'connection_log' | 'indicator' = 'all',
): Promise<GraphResponse> {
  return api.get<GraphResponse>(
    `/ops/${opId}/hosts/${hostId}/expand?evidence_type=${evidenceType}`,
  )
}

export async function findPaths(
  opId: string,
  req: PathFinderRequest,
): Promise<PathFinderResponse> {
  return api.post<PathFinderResponse>(`/ops/${opId}/graph/paths`, req)
}
