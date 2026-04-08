/**
 * React Flow graph canvas.
 * Purely driven by props — parent owns graphData and hiddenIds.
 * Events bubble up via callbacks.
 */
import { useCallback, useEffect, useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
  Position,
  Handle,
  type Node,
  type Edge,
  type NodeProps,
  type OnNodesChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import * as d3Force from 'd3-force'
import dagre from '@dagrejs/dagre'
import type { GraphEdge, GraphNode, GraphResponse } from '../types'
import styles from './GraphCanvas.module.css'

// ── Exported types (consumed by GraphView) ─────────────────────────────────────
export type LayoutName = 'cola' | 'cose-bilkent' | 'breadthfirst' | 'grid' | 'circle'
export interface CredFilter { credId: string; mode: 'highlight' | 'filter' }
export interface PathFilter { nodeIds: Set<string>; edgeKeys: Set<string> }

// ── Internal data shapes ────────────────────────────────────────────────────────

interface HostNodeData {
  label: string
  hasCredentials: boolean
  isLocked: boolean
  pathHighlight: boolean
  dimmed: boolean
  _node: GraphNode
}

interface ConfEdgeData {
  _edge: GraphEdge
}

// ── Custom node component ───────────────────────────────────────────────────────

function HostNode({ data: raw, selected }: NodeProps) {
  const data = raw as unknown as HostNodeData
  const { label, hasCredentials, isLocked, pathHighlight, dimmed } = data

  const borderColor = pathHighlight
    ? '#f78166'
    : isLocked
    ? '#d97706'
    : selected
    ? '#58a6ff'
    : hasCredentials
    ? '#d29922'
    : '#3d8bcd'

  const borderWidth = pathHighlight || selected || isLocked ? 3 : 2

  return (
    <div style={{
      width: 48,
      height: 48,
      borderRadius: '50%',
      background: pathHighlight ? '#2d1f1f' : selected ? '#1f2d3d' : '#1a2332',
      border: `${borderWidth}px solid ${borderColor}`,
      opacity: dimmed ? 0.18 : 1,
      cursor: 'pointer',
      position: 'relative',
    }}>
      <Handle type="target" position={Position.Left}
        style={{ opacity: 0, pointerEvents: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right}
        style={{ opacity: 0, pointerEvents: 'none', width: 1, height: 1 }} />
      <div style={{
        position: 'absolute',
        top: '100%',
        left: '50%',
        transform: 'translateX(-50%)',
        marginTop: 6,
        color: '#e6edf3',
        fontSize: 13,
        whiteSpace: 'nowrap',
        background: 'rgba(13,17,23,0.75)',
        padding: '1px 5px',
        borderRadius: 3,
        pointerEvents: 'none',
        userSelect: 'none',
      }}>
        {label}
      </div>
    </div>
  )
}

const nodeTypes = { host: HostNode }

// ── Layout computation ──────────────────────────────────────────────────────────

type EdgePair = { source: string; target: string }
type PosMap = Map<string, { x: number; y: number }>

function computeForceLayout(nodeIds: string[], edgePairs: EdgePair[], spacing = 200): PosMap {
  if (nodeIds.length === 0) return new Map()

  interface SimNode extends d3Force.SimulationNodeDatum { id: string }
  const simNodes: SimNode[] = nodeIds.map(id => ({ id }))

  const simLinks: d3Force.SimulationLinkDatum<SimNode>[] = edgePairs.map(e => ({
    source: e.source,
    target: e.target,
  }))

  const area = Math.max(600, nodeIds.length * spacing)
  const cx = area / 2, cy = area / 2

  const sim = d3Force.forceSimulation<SimNode>(simNodes)
    .force('link', d3Force.forceLink<SimNode, d3Force.SimulationLinkDatum<SimNode>>(simLinks)
      .id(d => d.id).distance(spacing).strength(0.5))
    .force('charge', d3Force.forceManyBody<SimNode>().strength(-500))
    .force('center', d3Force.forceCenter<SimNode>(cx, cy))
    .force('collide', d3Force.forceCollide<SimNode>(50))
    .stop()

  for (let i = 0; i < 300; i++) sim.tick()

  const result: PosMap = new Map()
  simNodes.forEach(n => result.set(n.id, { x: n.x ?? cx, y: n.y ?? cy }))
  return result
}

function computeDagreLayout(nodeIds: string[], edgePairs: EdgePair[]): PosMap {
  if (nodeIds.length === 0) return new Map()
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 120, nodesep: 80, marginx: 60, marginy: 60 })
  g.setDefaultEdgeLabel(() => ({}))
  const nodeSet = new Set(nodeIds)
  nodeIds.forEach(id => g.setNode(id, { width: 60, height: 60 }))
  edgePairs.forEach(e => {
    if (nodeSet.has(e.source) && nodeSet.has(e.target)) g.setEdge(e.source, e.target)
  })
  dagre.layout(g)
  const result: PosMap = new Map()
  nodeIds.forEach(id => {
    const pos = g.node(id)
    if (pos) result.set(id, { x: pos.x - 24, y: pos.y - 24 })
  })
  return result
}

function computeGridLayout(nodeIds: string[]): PosMap {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodeIds.length)))
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => result.set(id, {
    x: (i % cols) * 140 + 60,
    y: Math.floor(i / cols) * 140 + 60,
  }))
  return result
}

function computeCircleLayout(nodeIds: string[]): PosMap {
  const r = Math.max(140, nodeIds.length * 28)
  const cx = r + 80, cy = r + 80
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => {
    const angle = (i / nodeIds.length) * 2 * Math.PI - Math.PI / 2
    result.set(id, { x: cx + r * Math.cos(angle) - 24, y: cy + r * Math.sin(angle) - 24 })
  })
  return result
}

function computeLayout(layout: LayoutName, nodeIds: string[], edgePairs: EdgePair[]): PosMap {
  switch (layout) {
    case 'breadthfirst': return computeDagreLayout(nodeIds, edgePairs)
    case 'grid':         return computeGridLayout(nodeIds)
    case 'circle':       return computeCircleLayout(nodeIds)
    case 'cose-bilkent': return computeForceLayout(nodeIds, edgePairs, 240)
    case 'cola':
    default:             return computeForceLayout(nodeIds, edgePairs, 200)
  }
}

// ── Edge helpers ────────────────────────────────────────────────────────────────

function computeEdgeLabel(e: GraphEdge): string {
  for (const ev of e.evidence) {
    if (ev.type === 'connection_log' && ev.connection_type) return ev.connection_type.toUpperCase()
  }
  if (e.evidence.some(ev => ev.type === 'key_match'))    return 'key match'
  if (e.evidence.some(ev => ev.type === 'bash_history')) return 'bash history'
  if (e.evidence.some(ev => ev.type === 'known_hosts'))  return 'known hosts'
  return 'connection'
}

function confidenceColor(conf: string): string {
  if (conf === 'confirmed') return '#3fb950'
  if (conf === 'observed')  return '#d29922'
  return '#6e7681'
}

// ── Props ───────────────────────────────────────────────────────────────────────

interface Props {
  graphData: GraphResponse
  hiddenIds: Set<string>
  pathFilter: PathFilter | null
  credFilter: CredFilter | null
  layout: LayoutName
  lockedIds?: Set<string>
  focusHostId?: string | null
  onNodeClick: (node: GraphNode) => void
  onEdgeClick: (edge: GraphEdge) => void
  onNodeDoubleClick: (node: GraphNode) => void
  onNodeContextMenu: (node: GraphNode, x: number, y: number) => void
  onEdgeContextMenu: (edge: GraphEdge, x: number, y: number) => void
  onCanvasTap: () => void
}

// ── Inner component (needs ReactFlowProvider above) ─────────────────────────────

function GraphCanvasInner({
  graphData,
  hiddenIds,
  pathFilter,
  credFilter,
  layout,
  lockedIds,
  focusHostId,
  onNodeClick,
  onEdgeClick,
  onNodeDoubleClick,
  onNodeContextMenu,
  onEdgeContextMenu,
  onCanvasTap,
}: Props) {
  const { fitView, setCenter, getNode } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges] = useEdgesState<Edge>([])

  // Persist drag positions between renders
  const userPositions = useRef<Map<string, { x: number; y: number }>>(new Map())
  // Keep graphData accessible inside filter effect without adding it to deps
  const graphDataRef = useRef(graphData)
  useEffect(() => { graphDataRef.current = graphData }, [graphData])

  // Persist layout name for comparison
  const prevLayoutRef = useRef<LayoutName>(layout)

  // ── Effect: track node drag positions ────────────────────────────────────────
  const handleNodesChange: OnNodesChange = useCallback((changes) => {
    for (const change of changes) {
      if (change.type === 'position' && change.position) {
        userPositions.current.set(change.id, change.position)
      }
    }
    onNodesChange(changes)
  }, [onNodesChange])

  // ── Effect 1: structural rebuild (layout / graphData / hiddenIds) ─────────────
  useEffect(() => {
    const layoutChanged = prevLayoutRef.current !== layout
    prevLayoutRef.current = layout
    if (layoutChanged) userPositions.current.clear()

    const visibleIds = graphData.nodes
      .filter(n => !hiddenIds.has(n.host_id))
      .map(n => n.host_id)
    const visibleSet = new Set(visibleIds)

    const edgePairs: EdgePair[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => ({ source: e.src_host_id, target: e.dst_host_id }))

    // Only compute layout for nodes without a saved position
    const needsLayout = visibleIds.filter(id => !userPositions.current.has(id))
    const computed = needsLayout.length > 0 || layoutChanged
      ? computeLayout(layout, layoutChanged ? visibleIds : needsLayout, edgePairs)
      : new Map<string, { x: number; y: number }>()

    // Merge computed positions into user position store
    for (const [id, pos] of computed) {
      if (!userPositions.current.has(id) || layoutChanged) userPositions.current.set(id, pos)
    }

    const rfNodes: Node[] = graphData.nodes
      .filter(n => visibleSet.has(n.host_id))
      .map(n => {
        const pos = userPositions.current.get(n.host_id) ?? { x: 0, y: 0 }
        return {
          id: n.host_id,
          type: 'host',
          position: pos,
          draggable: !lockedIds?.has(n.host_id),
          data: {
            label: n.nickname,
            hasCredentials: n.credential_count > 0,
            isLocked: lockedIds?.has(n.host_id) ?? false,
            pathHighlight: false,
            dimmed: false,
            _node: n,
          } satisfies HostNodeData,
        }
      })

    const rfEdges: Edge[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => {
        const color = confidenceColor(e.confidence)
        return {
          id: `${e.src_host_id}__${e.dst_host_id}`,
          source: e.src_host_id,
          target: e.dst_host_id,
          label: computeEdgeLabel(e),
          labelStyle: { fill: '#8b949e', fontSize: 9 },
          style: { stroke: color, strokeWidth: 3 },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          data: { _edge: e } satisfies ConfEdgeData,
        }
      })

    setNodes(rfNodes)
    setEdges(rfEdges)

    if (visibleIds.length > 0) {
      setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 50)
    }
  // lockedIds is intentionally excluded — handled by Effect 2
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, hiddenIds, layout])

  // ── Effect 2: styling updates (filters / locks) ────────────────────────────
  useEffect(() => {
    const gd = graphDataRef.current

    setNodes(prev => prev.map(n => {
      const node = (n.data as unknown as HostNodeData)._node

      const inPath = pathFilter?.nodeIds.has(node.host_id) ?? null
      const pathHighlight = pathFilter ? !!inPath : false
      const hidden = pathFilter ? !inPath : false

      const nodeEdges = gd.edges.filter(
        e => e.src_host_id === node.host_id || e.dst_host_id === node.host_id,
      )
      const nodeMatchesCred = credFilter
        ? nodeEdges.some(e => e.evidence.some(ev => ev.credential_id === credFilter.credId))
        : null
      const dimmed = !pathFilter && credFilter?.mode === 'highlight'
        ? nodeMatchesCred === false
        : false

      return {
        ...n,
        hidden,
        draggable: !lockedIds?.has(node.host_id),
        data: {
          ...n.data,
          isLocked: lockedIds?.has(node.host_id) ?? false,
          pathHighlight,
          dimmed,
        },
      }
    }))

    setEdges(prev => prev.map(e => {
      const edge = (e.data as unknown as ConfEdgeData)._edge
      const edgeKey = `${edge.src_host_id}__${edge.dst_host_id}`

      const inPath = pathFilter?.edgeKeys.has(edgeKey) ?? null
      const pathHighlight = pathFilter ? !!inPath : false
      const hidden = pathFilter
        ? !inPath
        : credFilter?.mode === 'filter'
        ? !edge.evidence.some(ev => ev.credential_id === credFilter?.credId)
        : false
      const dimmed = !pathFilter && credFilter?.mode === 'highlight'
        ? !edge.evidence.some(ev => ev.credential_id === credFilter?.credId)
        : false

      const color = pathHighlight ? '#f78166' : confidenceColor(edge.confidence)
      return {
        ...e,
        hidden,
        style: {
          stroke: color,
          strokeWidth: pathHighlight ? 5 : 3,
          opacity: dimmed ? 0.18 : 1,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      }
    }))
  }, [pathFilter, credFilter, lockedIds, setNodes, setEdges])

  // ── Effect: focus a specific host ──────────────────────────────────────────
  useEffect(() => {
    if (!focusHostId) return
    const node = getNode(focusHostId)
    if (node) setCenter(node.position.x + 24, node.position.y + 24, { duration: 400, zoom: 1.5 })
  }, [focusHostId, getNode, setCenter])

  // ── Event handlers ──────────────────────────────────────────────────────────
  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeClick((node.data as unknown as HostNodeData)._node)
  }, [onNodeClick])

  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    onEdgeClick((edge.data as unknown as ConfEdgeData)._edge)
  }, [onEdgeClick])

  const handleNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeDoubleClick((node.data as unknown as HostNodeData)._node)
  }, [onNodeDoubleClick])

  const handleNodeCtxMenu = useCallback((evt: React.MouseEvent, node: Node) => {
    evt.preventDefault()
    onNodeContextMenu((node.data as unknown as HostNodeData)._node, evt.clientX, evt.clientY)
  }, [onNodeContextMenu])

  const handleEdgeCtxMenu = useCallback((evt: React.MouseEvent, edge: Edge) => {
    evt.preventDefault()
    onEdgeContextMenu((edge.data as unknown as ConfEdgeData)._edge, evt.clientX, evt.clientY)
  }, [onEdgeContextMenu])

  return (
    <div className={styles.canvas}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeContextMenu={handleNodeCtxMenu}
        onEdgeContextMenu={handleEdgeCtxMenu}
        onPaneClick={onCanvasTap}
        colorMode="dark"
        minZoom={0.05}
        maxZoom={4}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        elevateEdgesOnSelect
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#21262d" gap={28} />
        <Controls />
      </ReactFlow>
    </div>
  )
}

export default function GraphCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
