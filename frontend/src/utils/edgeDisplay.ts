/**
 * Pure edge-display helpers extracted from GraphCanvas.
 * Kept free of DOM/React so they can be unit-tested directly.
 */
import type { GraphEdge } from '../types'
import { CONFIDENCE_CONFIRMED, CONFIDENCE_OBSERVED, CONFIDENCE_MUTED } from '../theme'

export function computeEdgeLabel(e: GraphEdge): string {
  for (const ev of e.evidence) {
    if (ev.type === 'connection_log' && ev.connection_type) return ev.connection_type.toUpperCase()
  }
  if (e.evidence.some(ev => ev.type === 'key_match'))    return 'key match'
  if (e.evidence.some(ev => ev.type === 'bash_history')) return 'bash history'
  if (e.evidence.some(ev => ev.type === 'known_hosts'))  return 'known hosts'
  return 'connection'
}

export function confidenceColor(conf: string): string {
  if (conf === 'confirmed') return CONFIDENCE_CONFIRMED
  if (conf === 'observed')  return CONFIDENCE_OBSERVED
  return CONFIDENCE_MUTED
}
