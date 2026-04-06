import { api } from './client'
import type { SearchResponse } from '../types'

export function searchOp(opId: string, query: string): Promise<SearchResponse> {
  return api.get<SearchResponse>(`/ops/${opId}/search?q=${encodeURIComponent(query)}`)
}
