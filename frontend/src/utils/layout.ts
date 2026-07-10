/**
 * Pure graph layout algorithms extracted from GraphCanvas.
 * All return TOP-LEFT coords. react-force-graph uses center coords, so add 24
 * (half node size) when passing positions to FGNode.x/y. Kept DOM/React-free so
 * they can be unit-tested directly.
 */
import * as d3Force from 'd3-force'
import dagre from '@dagrejs/dagre'

export type LayoutName = 'cola' | 'cose-bilkent' | 'breadthfirst' | 'grid' | 'circle'
export type EdgePair = { source: string; target: string }
export type PosMap   = Map<string, { x: number; y: number }>

export function initialLayout(layout: LayoutName, nodeIds: string[], edgePairs: EdgePair[]): PosMap {
  if (nodeIds.length === 0) return new Map()
  switch (layout) {
    case 'breadthfirst': return dagreLayout(nodeIds, edgePairs)
    case 'grid':         return gridLayout(nodeIds)
    case 'circle':       return circleLayout(nodeIds)
    default: {
      const spacing = layout === 'cose-bilkent' ? 240 : 200
      return forceLayout(nodeIds, edgePairs, spacing)
    }
  }
}

interface SimNode extends d3Force.SimulationNodeDatum { id: string }

export function forceLayout(nodeIds: string[], edgePairs: EdgePair[], spacing: number): PosMap {
  const simNodes: SimNode[] = nodeIds.map(id => ({ id }))
  // Drop edges whose endpoints aren't in the seed sim — d3-force-link's
  // initialize() does find(nodeById, id) and throws "node not found" otherwise.
  // Mirrors the guard dagreLayout already has below.
  const nodeSet = new Set(nodeIds)
  const simLinks: d3Force.SimulationLinkDatum<SimNode>[] = edgePairs
    .filter(e => nodeSet.has(e.source) && nodeSet.has(e.target))
    .map(e => ({ source: e.source, target: e.target }))
  const cx = (nodeIds.length * spacing) / 2
  const sim = d3Force.forceSimulation<SimNode>(simNodes)
    .force('link', d3Force.forceLink<SimNode, d3Force.SimulationLinkDatum<SimNode>>(simLinks)
      .id(d => d.id).distance(spacing).strength(0.5))
    .force('charge', d3Force.forceManyBody<SimNode>().strength(-500))
    .force('center', d3Force.forceCenter<SimNode>(cx, cx))
    .force('collide', d3Force.forceCollide<SimNode>(50))
    .stop()
  for (let i = 0; i < 300; i++) sim.tick()
  const result: PosMap = new Map()
  simNodes.forEach(n => result.set(n.id, { x: (n.x ?? cx) - 24, y: (n.y ?? cx) - 24 }))
  return result
}

export function dagreLayout(nodeIds: string[], edgePairs: EdgePair[]): PosMap {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 120, nodesep: 80, marginx: 60, marginy: 60 })
  g.setDefaultEdgeLabel(() => ({}))
  const nodeSet = new Set(nodeIds)
  nodeIds.forEach(id => g.setNode(id, { width: 60, height: 60 }))
  edgePairs.forEach(e => { if (nodeSet.has(e.source) && nodeSet.has(e.target)) g.setEdge(e.source, e.target) })
  dagre.layout(g)
  const result: PosMap = new Map()
  nodeIds.forEach(id => { const p = g.node(id); if (p) result.set(id, { x: p.x - 24, y: p.y - 24 }) })
  return result
}

export function gridLayout(nodeIds: string[]): PosMap {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodeIds.length)))
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => result.set(id, { x: (i % cols) * 140 + 60, y: Math.floor(i / cols) * 140 + 60 }))
  return result
}

export function circleLayout(nodeIds: string[]): PosMap {
  const r = Math.max(140, nodeIds.length * 28)
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => {
    const a = (i / nodeIds.length) * 2 * Math.PI - Math.PI / 2
    result.set(id, { x: r + 80 + r * Math.cos(a) - 24, y: r + 80 + r * Math.sin(a) - 24 })
  })
  return result
}
