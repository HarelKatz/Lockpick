import type { GraphResponse } from '../types'

/**
 * Merge an incremental graph expansion into the existing graph.
 * Node and edge maps are keyed by host_id and "src__dst" respectively;
 * incoming entries override existing ones with the same key.
 */
export function mergeGraphResponses(existing: GraphResponse, incoming: GraphResponse): GraphResponse {
  const nodeMap = new Map(existing.nodes.map(n => [n.host_id, n]))
  for (const n of incoming.nodes) nodeMap.set(n.host_id, n)

  const edgeMap = new Map(existing.edges.map(e => [`${e.src_host_id}__${e.dst_host_id}`, e]))
  for (const e of incoming.edges) edgeMap.set(`${e.src_host_id}__${e.dst_host_id}`, e)

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  }
}
