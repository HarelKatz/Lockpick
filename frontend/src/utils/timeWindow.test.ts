import type { EvidenceItem, GraphEdge, GraphNode } from '../types'
import {
  computeEdgeTimes,
  computeTimeDomain,
  computeTimeStep,
  deriveWindow,
  computeHiddenEdgeKeys,
  computeHiddenNodeIds,
  snapTimeHandle,
  reclampWindow,
} from './timeWindow'

// ── fixtures ────────────────────────────────────────────────────────────────

function ev(partial: Partial<EvidenceItem>): EvidenceItem {
  return {
    type: 'connection_log', detail: '', credential_id: null, credential_fingerprint: null,
    credential_name: null, connection_type: null, src_user: null, dst_user: null,
    auth_method: null, timestamp: null, source_file: null, confidence: 'observed',
    ...partial,
  }
}

function edge(src: string, dst: string, evidence: EvidenceItem[] = []): GraphEdge {
  return { src_host_id: src, dst_host_id: dst, confidence: 'observed', evidence, pivotable_users: [] }
}

function node(host_id: string): GraphNode {
  return { host_id, nickname: host_id, ips: [], user_count: 0, credential_count: 0, status: null }
}

const T = (iso: string) => Date.parse(iso)

// ── computeEdgeTimes ──────────────────────────────────────────────────────────

describe('computeEdgeTimes', () => {
  it('collects parsed timestamps per edge key', () => {
    const times = computeEdgeTimes([
      edge('a', 'b', [ev({ timestamp: '2026-03-10T00:00:00Z' }), ev({ timestamp: '2026-03-12T00:00:00Z' })]),
    ])
    expect(times.get('a__b')).toEqual([T('2026-03-10T00:00:00Z'), T('2026-03-12T00:00:00Z')])
  })

  it('omits edges with no dated evidence (undated → not in the map)', () => {
    const times = computeEdgeTimes([edge('a', 'b', [ev({ timestamp: null }), ev({ type: 'key_match' })])])
    expect(times.has('a__b')).toBe(false)
  })

  it('skips unparseable timestamps', () => {
    const times = computeEdgeTimes([edge('a', 'b', [ev({ timestamp: 'not-a-date' }), ev({ timestamp: '2026-03-10T00:00:00Z' })])])
    expect(times.get('a__b')).toEqual([T('2026-03-10T00:00:00Z')])
  })
})

// ── computeTimeDomain ─────────────────────────────────────────────────────────

describe('computeTimeDomain', () => {
  it('returns null when there are no dated edges', () => {
    expect(computeTimeDomain(new Map())).toBeNull()
  })

  it('self-disables (null) when every date is identical (min === max)', () => {
    expect(computeTimeDomain(new Map([['a__b', [1000, 1000]]]))).toBeNull()
  })

  it('spans the global min/max across all edges', () => {
    const domain = computeTimeDomain(new Map([['a__b', [30, 10]], ['c__d', [50, 20]]]))
    expect(domain).toEqual({ min: 10, max: 50 })
  })
})

// ── computeTimeStep ───────────────────────────────────────────────────────────

describe('computeTimeStep', () => {
  it('is 1 when the domain is null', () => {
    expect(computeTimeStep(null)).toBe(1)
  })

  it('is ~1/500 of the span, floored, but never below 1', () => {
    expect(computeTimeStep({ min: 0, max: 1000 })).toBe(2)   // floor(1000/500)
    expect(computeTimeStep({ min: 0, max: 100 })).toBe(1)    // floor(100/500)=0 → 1
    expect(computeTimeStep({ min: 0, max: 500000 })).toBe(1000)
  })
})

// ── deriveWindow ──────────────────────────────────────────────────────────────

describe('deriveWindow', () => {
  it('returns null when there is no selection', () => {
    expect(deriveWindow(null)).toBeNull()
  })

  it('orders the two independent handles into [start,end] regardless of which is larger', () => {
    expect(deriveWindow({ a: 5, b: 2 })).toEqual({ start: 2, end: 5 })
    expect(deriveWindow({ a: 2, b: 5 })).toEqual({ start: 2, end: 5 })
  })
})

// ── computeHiddenEdgeKeys ─────────────────────────────────────────────────────

describe('computeHiddenEdgeKeys', () => {
  const win = { start: 100, end: 200 }

  it('hides nothing when there is no window', () => {
    const edges = [edge('a', 'b', [ev({ timestamp: '2026-01-01T00:00:00Z' })])]
    expect(computeHiddenEdgeKeys(edges, new Map([['a__b', [0]]]), null).size).toBe(0)
  })

  it('hides a dated edge whose dates all fall outside the window', () => {
    const edges = [edge('a', 'b')]
    const hidden = computeHiddenEdgeKeys(edges, new Map([['a__b', [50, 300]]]), win)
    expect(hidden.has('a__b')).toBe(true)
  })

  it('keeps a dated edge with at least one date inside the window (inclusive bounds)', () => {
    const edges = [edge('a', 'b'), edge('c', 'd')]
    const times = new Map([['a__b', [100]], ['c__d', [200]]])  // exactly on each boundary
    expect(computeHiddenEdgeKeys(edges, times, win).size).toBe(0)
  })

  it('never hides a key_match edge, even when its dates are out of window', () => {
    const edges = [edge('a', 'b', [ev({ type: 'key_match' })])]
    const hidden = computeHiddenEdgeKeys(edges, new Map([['a__b', [50]]]), win)
    expect(hidden.has('a__b')).toBe(false)
  })

  it('never hides an undated edge (not present in edgeTimes)', () => {
    const edges = [edge('a', 'b')]
    expect(computeHiddenEdgeKeys(edges, new Map(), win).size).toBe(0)
  })
})

// ── computeHiddenNodeIds ──────────────────────────────────────────────────────

describe('computeHiddenNodeIds', () => {
  it('hides nothing when no edges are hidden', () => {
    const nodes = [node('a'), node('b')]
    const edges = [edge('a', 'b')]
    expect(computeHiddenNodeIds(nodes, edges, new Set()).size).toBe(0)
  })

  it('hides a host whose only edge is hidden (disconnected by the window)', () => {
    const nodes = [node('a'), node('b')]
    const edges = [edge('a', 'b')]
    const hidden = computeHiddenNodeIds(nodes, edges, new Set(['a__b']))
    expect(hidden).toEqual(new Set(['a', 'b']))
  })

  it('keeps a host that still has one visible edge', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges = [edge('a', 'b'), edge('a', 'c')]   // a__b hidden, a__c visible
    const hidden = computeHiddenNodeIds(nodes, edges, new Set(['a__b']))
    expect(hidden.has('a')).toBe(false)  // a is still connected via a__c
    expect(hidden.has('c')).toBe(false)
    expect(hidden.has('b')).toBe(true)   // b's only edge is hidden
  })

  it('never hides a genuinely isolated host (no edges at all)', () => {
    const nodes = [node('a'), node('b'), node('lonely')]
    const edges = [edge('a', 'b')]
    const hidden = computeHiddenNodeIds(nodes, edges, new Set(['a__b']))
    expect(hidden.has('lonely')).toBe(false)
  })
})

// ── snapTimeHandle ────────────────────────────────────────────────────────────

describe('snapTimeHandle', () => {
  const domain = { min: 0, max: 1000 }
  const step = 10

  it('returns the value unchanged when the domain is null', () => {
    expect(snapTimeHandle(42, null, step)).toBe(42)
  })

  it('snaps to min within one step of the low edge (inclusive)', () => {
    expect(snapTimeHandle(5, domain, step)).toBe(0)
    expect(snapTimeHandle(10, domain, step)).toBe(0)   // exactly min+step
  })

  it('snaps to max within one step of the high edge (inclusive) — latest edge stays reachable', () => {
    expect(snapTimeHandle(995, domain, step)).toBe(1000)
    expect(snapTimeHandle(990, domain, step)).toBe(1000)  // exactly max-step
  })

  it('leaves an interior value untouched', () => {
    expect(snapTimeHandle(500, domain, step)).toBe(500)
  })
})

// ── reclampWindow ─────────────────────────────────────────────────────────────

describe('reclampWindow', () => {
  const domain = { min: 100, max: 200 }

  it('resets to the full range when there is no previous selection', () => {
    expect(reclampWindow(null, domain)).toEqual({ a: 100, b: 200 })
  })

  it('resets to the full range when the previous selection is disjoint from the new domain', () => {
    expect(reclampWindow({ a: 0, b: 50 }, domain)).toEqual({ a: 100, b: 200 })    // entirely below
    expect(reclampWindow({ a: 300, b: 400 }, domain)).toEqual({ a: 100, b: 200 }) // entirely above
  })

  it('clamps each handle into the domain when the selection still overlaps', () => {
    expect(reclampWindow({ a: 50, b: 150 }, domain)).toEqual({ a: 100, b: 150 })
    expect(reclampWindow({ a: 150, b: 250 }, domain)).toEqual({ a: 150, b: 200 })
  })

  it('leaves a selection fully inside the domain unchanged', () => {
    expect(reclampWindow({ a: 120, b: 180 }, domain)).toEqual({ a: 120, b: 180 })
  })
})
