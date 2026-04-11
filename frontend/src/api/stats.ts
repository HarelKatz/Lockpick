/**
 * Operation stats API — used for polling to detect new records added by teammates.
 */
import { api } from './client'
import type { OpStats } from '../types'

export function getOpStats(opId: string): Promise<OpStats> {
  return api.get<OpStats>(`/ops/${opId}/stats`)
}
