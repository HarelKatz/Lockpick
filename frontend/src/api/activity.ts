import { api } from './client'
import type { ActivityLog } from '../types'

export function getActivityLog(opId: string, limit = 50): Promise<ActivityLog[]> {
  return api.get<ActivityLog[]>(`/ops/${opId}/activity?limit=${limit}`)
}
