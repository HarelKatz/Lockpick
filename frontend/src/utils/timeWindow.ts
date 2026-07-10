/**
 * Pure time-slider math extracted from GraphView. Filters connection edges by
 * evidence timestamp. Kept DOM/React-free so the slider logic is unit-testable
 * (the e2e specs prove the same behavior end-to-end).
 */
import type { GraphEdge, GraphNode } from '../types'

export interface TimeDomain { min: number; max: number }
export interface TimeWindow { start: number; end: number }
export interface TimeSel { a: number; b: number }

const edgeKey = (e: GraphEdge): string => `${e.src_host_id}__${e.dst_host_id}`

/**
 * Per-edge dated timestamps (epoch ms) from evidence. key_match evidence carries
 * no timestamp, so key-match-only edges never appear here. Edges with no dated
 * evidence are omitted entirely.
 */
export function computeEdgeTimes(edges: GraphEdge[]): Map<string, number[]> {
  const map = new Map<string, number[]>()
  for (const e of edges) {
    const times: number[] = []
    for (const ev of e.evidence) {
      if (!ev.timestamp) continue
      const t = Date.parse(ev.timestamp)
      if (!Number.isNaN(t)) times.push(t)
    }
    if (times.length) map.set(edgeKey(e), times)
  }
  return map
}

/**
 * Draggable domain = span of all dated evidence. Null (bar hidden) when there
 * are no dated edges, or when every date is identical (min === max → nothing to
 * drag) — the feature self-disables rather than showing a dead slider.
 */
export function computeTimeDomain(edgeTimes: Map<string, number[]>): TimeDomain | null {
  let min = Infinity, max = -Infinity
  for (const times of edgeTimes.values()) {
    for (const t of times) { if (t < min) min = t; if (t > max) max = t }
  }
  return min === Infinity || min === max ? null : { min, max }
}

/** ~500 draggable increments across the domain, whatever its span. */
export function computeTimeStep(timeDomain: TimeDomain | null): number {
  return timeDomain ? Math.max(1, Math.floor((timeDomain.max - timeDomain.min) / 500)) : 1
}

/** The window the rest of the UI consumes: [earlier handle, later handle]. */
export function deriveWindow(timeSel: TimeSel | null): TimeWindow | null {
  return timeSel ? { start: Math.min(timeSel.a, timeSel.b), end: Math.max(timeSel.a, timeSel.b) } : null
}

/**
 * Edge keys the current window hides. An edge is hidden iff it has dated evidence
 * AND none of its dates fall inside the window. Two exemptions keep a real pivot
 * from ever being concealed: key-match edges (structural, not time-bound) and
 * undated edges (no basis to hide) are always shown.
 */
export function computeHiddenEdgeKeys(
  edges: GraphEdge[],
  edgeTimes: Map<string, number[]>,
  timeWindow: TimeWindow | null,
): Set<string> {
  const hidden = new Set<string>()
  if (!timeWindow) return hidden
  for (const e of edges) {
    if (e.evidence.some(ev => ev.type === 'key_match')) continue   // always shown
    const key = edgeKey(e)
    const times = edgeTimes.get(key)
    if (!times) continue                                           // undated → always shown
    if (!times.some(t => t >= timeWindow.start && t <= timeWindow.end)) hidden.add(key)
  }
  return hidden
}

/**
 * Nodes the time filter hides: hosts the window *disconnected* — they have edges,
 * but all of them are out-of-window. Key-match / undated edges keep their
 * endpoints visible. Genuinely isolated hosts (no edges at all) are never hidden.
 */
export function computeHiddenNodeIds(
  nodes: GraphNode[],
  edges: GraphEdge[],
  hiddenKeys: Set<string>,
): Set<string> {
  const hidden = new Set<string>()
  if (hiddenKeys.size === 0) return hidden
  const hasEdge = new Set<string>()
  const connected = new Set<string>()
  for (const e of edges) {
    hasEdge.add(e.src_host_id)
    hasEdge.add(e.dst_host_id)
    if (!hiddenKeys.has(edgeKey(e))) {
      connected.add(e.src_host_id)
      connected.add(e.dst_host_id)
    }
  }
  for (const n of nodes) {
    if (hasEdge.has(n.host_id) && !connected.has(n.host_id)) hidden.add(n.host_id)
  }
  return hidden
}

/**
 * A drag landing within one step of a domain edge snaps exactly to it, so the
 * earliest/latest-dated edge is always reachable despite range-input step
 * quantization (browsers snap a full-swing drag to a grid point short of the max).
 */
export function snapTimeHandle(v: number, timeDomain: TimeDomain | null, timeStep: number): number {
  if (!timeDomain) return v
  if (v <= timeDomain.min + timeStep) return timeDomain.min
  if (v >= timeDomain.max - timeStep) return timeDomain.max
  return v
}

/**
 * Re-clamp the handles when the domain changes. Fresh domain (no prior selection)
 * → full range. A selection that still overlaps the new domain → clamp each handle
 * into it. A selection now entirely outside the new domain → reset to full, rather
 * than collapsing onto a domain edge (which would strand the graph near-empty).
 */
export function reclampWindow(prev: TimeSel | null, timeDomain: TimeDomain): TimeSel {
  if (!prev) return { a: timeDomain.min, b: timeDomain.max }
  const lo = Math.min(prev.a, prev.b), hi = Math.max(prev.a, prev.b)
  if (hi < timeDomain.min || lo > timeDomain.max) return { a: timeDomain.min, b: timeDomain.max }
  const clamp = (x: number) => Math.min(Math.max(x, timeDomain.min), timeDomain.max)
  return { a: clamp(prev.a), b: clamp(prev.b) }
}
