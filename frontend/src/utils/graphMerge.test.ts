import type { GraphEdge, GraphNode, GraphResponse } from '../types'
import { mergeGraphResponses } from './graphMerge'

function node(host_id: string, nickname = host_id): GraphNode {
  return { host_id, nickname, ips: [], user_count: 0, credential_count: 0, status: null }
}

function edge(src: string, dst: string, confidence: GraphEdge['confidence'] = 'observed'): GraphEdge {
  return { src_host_id: src, dst_host_id: dst, confidence, evidence: [], pivotable_users: [] }
}

function resp(nodes: GraphNode[], edges: GraphEdge[]): GraphResponse {
  return { nodes, edges }
}

describe('mergeGraphResponses', () => {
  it('unions disjoint nodes and edges', () => {
    const merged = mergeGraphResponses(
      resp([node('a')], [edge('a', 'b')]),
      resp([node('c')], [edge('c', 'd')]),
    )
    expect(merged.nodes.map(n => n.host_id)).toEqual(['a', 'c'])
    expect(merged.edges.map(e => `${e.src_host_id}__${e.dst_host_id}`)).toEqual(['a__b', 'c__d'])
  })

  it('lets an incoming node override an existing one with the same host_id (no duplicate)', () => {
    const merged = mergeGraphResponses(
      resp([node('a', 'old')], []),
      resp([node('a', 'new')], []),
    )
    expect(merged.nodes).toHaveLength(1)
    expect(merged.nodes[0].nickname).toBe('new')
  })

  it('lets an incoming edge override an existing one with the same src__dst', () => {
    const merged = mergeGraphResponses(
      resp([], [edge('a', 'b', 'observed')]),
      resp([], [edge('a', 'b', 'confirmed')]),
    )
    expect(merged.edges).toHaveLength(1)
    expect(merged.edges[0].confidence).toBe('confirmed')
  })

  it('preserves existing order and appends incoming-only entries', () => {
    const merged = mergeGraphResponses(
      resp([node('a'), node('b')], []),
      resp([node('b', 'b2'), node('c')], []),
    )
    // 'b' keeps its original position but gets the incoming value; 'c' appended
    expect(merged.nodes.map(n => n.host_id)).toEqual(['a', 'b', 'c'])
    expect(merged.nodes.find(n => n.host_id === 'b')!.nickname).toBe('b2')
  })

  it('handles an empty existing or empty incoming', () => {
    const incoming = resp([node('a')], [edge('a', 'b')])
    expect(mergeGraphResponses(resp([], []), incoming)).toEqual(incoming)
    expect(mergeGraphResponses(incoming, resp([], []))).toEqual(incoming)
  })

  it('directional edges a__b and b__a are distinct', () => {
    const merged = mergeGraphResponses(
      resp([], [edge('a', 'b')]),
      resp([], [edge('b', 'a')]),
    )
    expect(merged.edges).toHaveLength(2)
  })
})
