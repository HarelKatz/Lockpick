/**
 * React Flow graph canvas.
 * Purely driven by props — parent owns graphData and hiddenIds.
 * Events bubble up via callbacks.
 *
 * Physics model (mirrors Neo4j Browser):
 *  - Simulation is initialized from the computed layout but starts STOPPED (alpha=0)
 *  - Drag start → alphaTarget(0.3).restart() wakes the simulation; dragged node is
 *    pinned via fx/fy so spring forces pull its neighbors toward it
 *  - Each tick → React Flow positions updated for non-dragged nodes
 *  - Drag stop → unpin, alphaTarget(0) → simulation cools and stops naturally
 */
import { useCallback, useEffect, useRef } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  useNodesInitialized,
  useInternalNode,
  ReactFlowProvider,
  MarkerType,
  Position,
  Handle,
  BaseEdge,
  getStraightPath,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeProps,
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

// d3-force simulation node — uses CENTER coordinates (RF position = center - 24)
interface SimNode extends d3Force.SimulationNodeDatum {
  id: string
}

// ── Floating edge ───────────────────────────────────────────────────────────────
// Reads actual node positions via useInternalNode and draws a straight line
// between the circular node boundaries, so the arrow always lands correctly
// regardless of the direction between the two nodes.

const NODE_RADIUS = 27

function FloatingEdge({ id, source, target, style, markerEnd, label, labelStyle }: EdgeProps) {
  const sourceNode = useInternalNode(source)
  const targetNode = useInternalNode(target)

  if (!sourceNode || !targetNode) return null

  // positionAbsolute is the top-left corner; centre = pos + 24 (half of 48px)
  const sx = sourceNode.internals.positionAbsolute.x + 24
  const sy = sourceNode.internals.positionAbsolute.y + 24
  const tx = targetNode.internals.positionAbsolute.x + 24
  const ty = targetNode.internals.positionAbsolute.y + 24

  const dx = tx - sx
  const dy = ty - sy
  const len = Math.sqrt(dx * dx + dy * dy) || 1

  const startX = sx + (dx / len) * NODE_RADIUS
  const startY = sy + (dy / len) * NODE_RADIUS
  const endX   = tx - (dx / len) * (NODE_RADIUS + 2)
  const endY   = ty - (dy / len) * (NODE_RADIUS + 2)

  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX: startX, sourceY: startY,
    targetX: endX,   targetY: endY,
  })

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={style}
      markerEnd={markerEnd}
      label={label}
      labelX={labelX}
      labelY={labelY}
      labelStyle={labelStyle}
      interactionWidth={12}
    />
  )
}

// ── Custom host node ────────────────────────────────────────────────────────────

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

  return (
    <div style={{
      width: 48,
      height: 48,
      borderRadius: '50%',
      background: pathHighlight ? '#2d1f1f' : selected ? '#1f2d3d' : '#1a2332',
      border: `${pathHighlight || selected || isLocked ? 3 : 2}px solid ${borderColor}`,
      opacity: dimmed ? 0.18 : 1,
      cursor: 'pointer',
      position: 'relative',
    }}>
      {/* Invisible centered handles — needed by React Flow but ignored by FloatingEdge */}
      <Handle type="target" position={Position.Left}
        style={{ left: '50%', top: '50%', opacity: 0, width: 0, height: 0, minWidth: 0, minHeight: 0, transform: 'none' }} />
      <Handle type="source" position={Position.Right}
        style={{ left: '50%', top: '50%', opacity: 0, width: 0, height: 0, minWidth: 0, minHeight: 0, transform: 'none' }} />
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
const edgeTypes = { floating: FloatingEdge }

// ── Deterministic initial layout ────────────────────────────────────────────────
// Used only for the first placement. After that, drag physics take over.

type EdgePair = { source: string; target: string }
type PosMap   = Map<string, { x: number; y: number }>

function initialLayout(layout: LayoutName, nodeIds: string[], edgePairs: EdgePair[]): PosMap {
  if (nodeIds.length === 0) return new Map()

  switch (layout) {
    case 'breadthfirst': return dagreLayout(nodeIds, edgePairs)
    case 'grid':         return gridLayout(nodeIds)
    case 'circle':       return circleLayout(nodeIds)
    default: {
      // Force-directed: run synchronously for instant placement
      const spacing = layout === 'cose-bilkent' ? 240 : 200
      return forceLayout(nodeIds, edgePairs, spacing)
    }
  }
}

function forceLayout(nodeIds: string[], edgePairs: EdgePair[], spacing: number): PosMap {
  const simNodes: SimNode[] = nodeIds.map(id => ({ id }))
  const simLinks: d3Force.SimulationLinkDatum<SimNode>[] = edgePairs.map(e => ({
    source: e.source, target: e.target,
  }))
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

function dagreLayout(nodeIds: string[], edgePairs: EdgePair[]): PosMap {
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

function gridLayout(nodeIds: string[]): PosMap {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodeIds.length)))
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => result.set(id, { x: (i % cols) * 140 + 60, y: Math.floor(i / cols) * 140 + 60 }))
  return result
}

function circleLayout(nodeIds: string[]): PosMap {
  const r = Math.max(140, nodeIds.length * 28)
  const result: PosMap = new Map()
  nodeIds.forEach((id, i) => {
    const a = (i / nodeIds.length) * 2 * Math.PI - Math.PI / 2
    result.set(id, { x: r + 80 + r * Math.cos(a) - 24, y: r + 80 + r * Math.sin(a) - 24 })
  })
  return result
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

// ── Inner component ─────────────────────────────────────────────────────────────

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
  const nodesInitialized = useNodesInitialized()
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges] = useEdgesState<Edge>([])

  // ── Physics simulation state ────────────────────────────────────────────────
  // Simulation uses CENTER coordinates; RF position = center - 24
  const simRef       = useRef<d3Force.Simulation<SimNode, never> | null>(null)
  const simNodeMap   = useRef<Map<string, SimNode>>(new Map())
  const draggingId   = useRef<string | null>(null)
  const rafPending   = useRef(false)

  // Last known RF positions (top-left); source of truth between re-renders
  const savedPos = useRef<Map<string, { x: number; y: number }>>(new Map())

  // graphData ref for callbacks that can't list graphData as dep
  const graphDataRef = useRef(graphData)
  useEffect(() => { graphDataRef.current = graphData }, [graphData])

  const prevLayoutRef = useRef<LayoutName>(layout)

  // ── fitView after React Flow measures nodes ─────────────────────────────────
  const pendingFitView = useRef(false)
  useEffect(() => {
    if (nodesInitialized && pendingFitView.current) {
      pendingFitView.current = false
      fitView({ padding: 0.15, duration: 300 })
    }
  }, [nodesInitialized, fitView])

  // ── Simulation tick → push positions into React Flow ───────────────────────
  const flushSimPositions = useCallback(() => {
    rafPending.current = false
    setNodes(prev => prev.map(n => {
      if (n.id === draggingId.current) return n  // RF owns the dragged node
      const sn = simNodeMap.current.get(n.id)
      if (!sn || sn.x === undefined || sn.y === undefined) return n
      const pos = { x: sn.x - 24, y: sn.y - 24 }
      savedPos.current.set(n.id, pos)
      return { ...n, position: pos }
    }))
  }, [setNodes])

  // ── Build / rebuild the physics simulation ──────────────────────────────────
  const buildSim = useCallback((
    nodePositions: Map<string, { x: number; y: number }>,
    edgePairs: EdgePair[],
  ) => {
    simRef.current?.stop()

    const simNodes: SimNode[] = Array.from(nodePositions.entries()).map(([id, pos]) => ({
      id,
      x: pos.x + 24,  // convert RF top-left → d3 center
      y: pos.y + 24,
    }))
    simNodeMap.current = new Map(simNodes.map(n => [n.id, n]))

    const sim = d3Force.forceSimulation<SimNode>(simNodes)
      .force('link',
        d3Force.forceLink<SimNode, d3Force.SimulationLinkDatum<SimNode>>(
          edgePairs.map(e => ({ source: e.source, target: e.target }))
        ).id(d => d.id).distance(180).strength(0.5)
      )
      .force('charge', d3Force.forceManyBody<SimNode>().strength(-350))
      .force('collide', d3Force.forceCollide<SimNode>(52))
      .alpha(0)   // start stopped — only wakes on drag
      .alphaDecay(0.04)
      .on('tick', () => {
        if (!rafPending.current) {
          rafPending.current = true
          requestAnimationFrame(flushSimPositions)
        }
      })

    simRef.current = sim
  }, [flushSimPositions])

  // ── Effect 1: structural rebuild (layout / graphData / hiddenIds) ─────────────
  useEffect(() => {
    const layoutChanged = prevLayoutRef.current !== layout
    prevLayoutRef.current = layout

    if (layoutChanged) savedPos.current.clear()

    const visibleIds = graphData.nodes
      .filter(n => !hiddenIds.has(n.host_id))
      .map(n => n.host_id)
    const visibleSet = new Set(visibleIds)

    const edgePairs: EdgePair[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => ({ source: e.src_host_id, target: e.dst_host_id }))

    // Compute positions only for nodes that don't already have a saved position
    const needsLayout = visibleIds.filter(id => !savedPos.current.has(id))
    if (needsLayout.length > 0 || layoutChanged) {
      const computed = initialLayout(layout, layoutChanged ? visibleIds : needsLayout, edgePairs)
      for (const [id, pos] of computed) {
        if (!savedPos.current.has(id) || layoutChanged) savedPos.current.set(id, pos)
      }
    }

    // Build RF nodes and edges
    const rfNodes: Node[] = graphData.nodes
      .filter(n => visibleSet.has(n.host_id))
      .map(n => ({
        id: n.host_id,
        type: 'host',
        position: savedPos.current.get(n.host_id) ?? { x: 0, y: 0 },
        draggable: !lockedIds?.has(n.host_id),
        data: {
          label: n.nickname,
          hasCredentials: n.credential_count > 0,
          isLocked: lockedIds?.has(n.host_id) ?? false,
          pathHighlight: false,
          dimmed: false,
          _node: n,
        } satisfies HostNodeData,
      }))

    const rfEdges: Edge[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => {
        const color = confidenceColor(e.confidence)
        return {
          id: `${e.src_host_id}__${e.dst_host_id}`,
          type: 'floating',
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

    // (Re)build simulation from current positions
    const posMap = new Map(
      visibleIds.map(id => [id, savedPos.current.get(id) ?? { x: 0, y: 0 }])
    )
    buildSim(posMap, edgePairs)

    if (visibleIds.length > 0) pendingFitView.current = true

    return () => { simRef.current?.stop() }
  // lockedIds excluded — handled by Effect 2
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, hiddenIds, layout])

  // ── Effect 2: styling updates (filters / locks) — no position recompute ──────
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
        ? nodeMatchesCred === false : false

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
        ? !edge.evidence.some(ev => ev.credential_id === credFilter?.credId) : false

      const color = pathHighlight ? '#f78166' : confidenceColor(edge.confidence)
      return {
        ...e,
        hidden,
        style: { stroke: color, strokeWidth: pathHighlight ? 5 : 3, opacity: dimmed ? 0.18 : 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      }
    }))
  }, [pathFilter, credFilter, lockedIds, setNodes, setEdges])

  // ── Focus a specific host ──────────────────────────────────────────────────
  useEffect(() => {
    if (!focusHostId) return
    const node = getNode(focusHostId)
    if (node) setCenter(node.position.x + 24, node.position.y + 24, { duration: 400, zoom: 1.5 })
  }, [focusHostId, getNode, setCenter])

  // ── Track drag position for savedPos (dragged node only) ───────────────────
  const handleNodesChange: OnNodesChange = useCallback((changes) => {
    for (const change of changes) {
      if (change.type === 'position' && change.position) {
        savedPos.current.set(change.id, change.position)
      }
    }
    onNodesChange(changes)
  }, [onNodesChange])

  // ── Neo4j-style drag using live simulation ─────────────────────────────────
  const handleNodeDragStart = useCallback((_: React.MouseEvent, node: Node) => {
    draggingId.current = node.id
    const sn = simNodeMap.current.get(node.id)
    if (!sn) return
    // Pin the dragged node so forces don't move it — RF owns its position
    sn.fx = node.position.x + 24
    sn.fy = node.position.y + 24
    // Wake the simulation — spring + repulsion forces now act on all neighbors
    simRef.current?.alphaTarget(0.3).restart()
  }, [])

  const handleNodeDrag = useCallback((_: React.MouseEvent, node: Node) => {
    const sn = simNodeMap.current.get(node.id)
    if (!sn) return
    // Follow the cursor: update the pinned position each frame
    sn.fx = node.position.x + 24
    sn.fy = node.position.y + 24
  }, [])

  const handleNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
    draggingId.current = null
    const sn = simNodeMap.current.get(node.id)
    if (sn) {
      sn.fx = undefined
      sn.fy = undefined
    }
    savedPos.current.set(node.id, node.position)
    // Let simulation cool down naturally — nodes settle into their new positions
    simRef.current?.alphaTarget(0)
  }, [])

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
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeContextMenu={handleNodeCtxMenu}
        onEdgeContextMenu={handleEdgeCtxMenu}
        onNodeDragStart={handleNodeDragStart}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={handleNodeDragStop}
        onPaneClick={onCanvasTap}
        colorMode="dark"
        minZoom={0.05}
        maxZoom={4}
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
