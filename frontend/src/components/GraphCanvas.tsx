/**
 * Graph canvas using react-force-graph (ForceGraph2D).
 * Replaces @xyflow/react which had unfixable fitView / setViewport issues
 * caused by its internal panZoom/d3Zoom silently no-oping on our container.
 *
 * Purely driven by props — parent owns graphData and hiddenIds.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import * as d3Force from 'd3-force'
import dagre from '@dagrejs/dagre'
import type { GraphEdge, GraphNode, GraphResponse } from '../types'
import styles from './GraphCanvas.module.css'

// ── Exported types (consumed by GraphView) ─────────────────────────────────────
export type LayoutName = 'cola' | 'cose-bilkent' | 'breadthfirst' | 'grid' | 'circle'
export interface CredFilter { credId: string; mode: 'highlight' | 'filter' }
export interface PathFilter { nodeIds: Set<string>; edgeKeys: Set<string> }

// ── Internal data shapes ────────────────────────────────────────────────────────

interface FGNode {
  id: string
  x?: number; y?: number
  vx?: number; vy?: number
  fx?: number; fy?: number
  label: string
  hasCredentials: boolean
  isLocked: boolean
  pathHighlight: boolean
  dimmed: boolean
  _node: GraphNode
}

interface FGLink {
  source: string | FGNode
  target: string | FGNode
  color: string
  lineWidth: number
  dimmed: boolean
  edgeLabel: string
  _edge: GraphEdge
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

// ── Layout algorithms ───────────────────────────────────────────────────────────
// All return top-left coords. react-force-graph uses center coords,
// so add 24 (half node size) when passing positions to FGNode.x/y.

type EdgePair = { source: string; target: string }
type PosMap   = Map<string, { x: number; y: number }>

function initialLayout(layout: LayoutName, nodeIds: string[], edgePairs: EdgePair[]): PosMap {
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

const STATIC_LAYOUTS: LayoutName[] = ['breadthfirst', 'grid', 'circle']

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

// ── Component ───────────────────────────────────────────────────────────────────

export default function GraphCanvas({
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
  // Container dimensions — ForceGraph2D needs explicit px width/height
  const containerRef = useRef<HTMLDivElement>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setDims({ w: Math.floor(width), h: Math.floor(height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const fitNeededRef = useRef(false)

  // Saved node positions (top-left coords, compatible with layout algorithms)
  const savedPos = useRef<PosMap>(new Map())

  const prevLayoutRef = useRef<LayoutName>(layout)
  const prevVisibleCountRef = useRef(0)
  const graphDataRef = useRef(graphData)
  useEffect(() => { graphDataRef.current = graphData }, [graphData])

  // Selected node — tracked internally for visual highlight; not in props
  const selectedNodeIdRef = useRef<string | null>(null)
  // Double-click detection — ForceGraph2D has no onNodeDoubleClick prop
  const lastClickRef = useRef<{ id: string; time: number } | null>(null)

  // ── Graph data state ─────────────────────────────────────────────────────────
  const [fgData, setFgData] = useState<{ nodes: FGNode[]; links: FGLink[] }>({ nodes: [], links: [] })

  // ── Customize d3-force once container is ready ───────────────────────────────
  useEffect(() => {
    if (!graphRef.current || dims.w === 0) return
    graphRef.current.d3Force('link')?.distance(180).strength(0.5)
    graphRef.current.d3Force('charge')?.strength(-80)
    graphRef.current.d3Force('collision', d3Force.forceCollide(52))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dims.w > 0])

  // ── Effect 1: structural rebuild ─────────────────────────────────────────────
  useEffect(() => {
    const layoutChanged = prevLayoutRef.current !== layout
    prevLayoutRef.current = layout
    const prevCount = prevVisibleCountRef.current

    if (layoutChanged) savedPos.current.clear()

    const visibleIds = graphData.nodes
      .filter(n => !hiddenIds.has(n.host_id))
      .map(n => n.host_id)
    prevVisibleCountRef.current = visibleIds.length
    const visibleSet = new Set(visibleIds)

    const edgePairs: EdgePair[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => ({ source: e.src_host_id, target: e.dst_host_id }))

    // Compute positions for new nodes (or all on layout change)
    const needsLayout = visibleIds.filter(id => !savedPos.current.has(id))
    if (needsLayout.length > 0 || layoutChanged) {
      const computed = initialLayout(layout, layoutChanged ? visibleIds : needsLayout, edgePairs)
      for (const [id, pos] of computed) {
        if (!savedPos.current.has(id) || layoutChanged) savedPos.current.set(id, pos)
      }
    }

    const isStatic = STATIC_LAYOUTS.includes(layout)

    const nodes: FGNode[] = graphData.nodes
      .filter(n => visibleSet.has(n.host_id))
      .map(n => {
        const pos = savedPos.current.get(n.host_id) ?? { x: 0, y: 0 }
        const cx = pos.x + 24  // top-left → center (node is 48px wide/tall)
        const cy = pos.y + 24
        const pinned = isStatic || (lockedIds?.has(n.host_id) ?? false)
        return {
          id: n.host_id,
          x: cx, y: cy,
          fx: pinned ? cx : undefined,
          fy: pinned ? cy : undefined,
          label: n.nickname,
          hasCredentials: n.credential_count > 0,
          isLocked: lockedIds?.has(n.host_id) ?? false,
          pathHighlight: false,
          dimmed: false,
          _node: n,
        }
      })

    const links: FGLink[] = graphData.edges
      .filter(e => visibleSet.has(e.src_host_id) && visibleSet.has(e.dst_host_id))
      .map(e => ({
        source: e.src_host_id,
        target: e.dst_host_id,
        color: confidenceColor(e.confidence),
        lineWidth: 2,
        dimmed: false,
        edgeLabel: computeEdgeLabel(e),
        _edge: e,
      }))

    // Flag for auto-fit: initial load or layout switch
    const wasEmpty = prevCount === 0
    if ((wasEmpty || layoutChanged) && visibleIds.length > 0) {
      fitNeededRef.current = true
    }

    setFgData({ nodes, links })

    // Static layouts: pause simulation immediately after data is set
    if (isStatic && graphRef.current) {
      // Slight delay to let ForceGraph2D process the new data
      setTimeout(() => graphRef.current?.pauseAnimation(), 50)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, hiddenIds, layout])

  // ── Effect 2: styling (path filter, cred filter, locks) ──────────────────────
  // Mutates d3 node/link objects IN PLACE — no new objects, no setFgData,
  // no simulation reinitialization.  d3 already mutates these same objects
  // every tick; one extra mutation per style change is safe.
  //
  // fgData is intentionally in deps: re-apply styles after Effect 1 creates
  // fresh node objects (structural rebuild).
  useEffect(() => {
    const gd = graphDataRef.current

    for (const n of fgData.nodes) {
      const node = n._node
      const inPath = pathFilter?.nodeIds.has(node.host_id) ?? null
      n.pathHighlight = pathFilter ? !!inPath : false

      const nodeEdges = gd.edges.filter(
        e => e.src_host_id === node.host_id || e.dst_host_id === node.host_id,
      )
      const nodeMatchesCred = credFilter
        ? nodeEdges.some(e => e.evidence.some(ev => ev.credential_id === credFilter.credId))
        : null
      n.dimmed = !pathFilter && credFilter?.mode === 'highlight'
        ? nodeMatchesCred === false : false

      const pinned = STATIC_LAYOUTS.includes(prevLayoutRef.current) || (lockedIds?.has(node.host_id) ?? false)
      n.fx = pinned ? n.x : undefined
      n.fy = pinned ? n.y : undefined
      n.isLocked = lockedIds?.has(node.host_id) ?? false
    }

    for (const l of fgData.links) {
      const edge = l._edge
      const edgeKey = `${edge.src_host_id}__${edge.dst_host_id}`
      const inPath = pathFilter?.edgeKeys.has(edgeKey) ?? null
      const pathHighlight = pathFilter ? !!inPath : false
      const hiddenByFilter = pathFilter
        ? !inPath
        : credFilter?.mode === 'filter'
        ? !edge.evidence.some(ev => ev.credential_id === credFilter?.credId)
        : false
      const dimmed = !pathFilter && credFilter?.mode === 'highlight'
        ? !edge.evidence.some(ev => ev.credential_id === credFilter?.credId) : false

      l.color = pathHighlight ? '#f78166' : confidenceColor(edge.confidence)
      l.lineWidth = pathHighlight ? 4 : 2
      l.dimmed = dimmed || hiddenByFilter
    }

    // Briefly reheat so d3 applies the fx/fy constraints and the rAF loop
    // redraws the canvas (loop may be stopped if the simulation already settled).
    graphRef.current?.d3ReheatSimulation()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathFilter, credFilter, lockedIds, fgData])

  // ── Focus a specific host ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!focusHostId || !graphRef.current) return
    const node = fgData.nodes.find(n => n.id === focusHostId)
    if (node?.x != null && node?.y != null) {
      graphRef.current.centerAt(node.x, node.y, 400)
      graphRef.current.zoom(1.5, 400)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusHostId])

  // ── Canvas drawing ────────────────────────────────────────────────────────────

  const drawNode = useCallback((node: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const n = node as FGNode
    const { x = 0, y = 0, pathHighlight, dimmed, isLocked, hasCredentials, label } = n
    const isSelected = n.id === selectedNodeIdRef.current
    const r = 27

    ctx.globalAlpha = dimmed ? 0.18 : 1

    // Circle fill
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 2 * Math.PI)
    ctx.fillStyle = pathHighlight ? '#2d1f1f' : isSelected ? '#1f2d3d' : '#1a2332'
    ctx.fill()

    // Circle border
    const borderColor = pathHighlight ? '#f78166'
      : isLocked     ? '#d97706'
      : isSelected   ? '#58a6ff'
      : hasCredentials ? '#d29922'
      : '#3d8bcd'
    ctx.lineWidth = (pathHighlight || isSelected || isLocked ? 3 : 2) / globalScale
    ctx.strokeStyle = borderColor
    ctx.stroke()

    // Label below circle
    const fontSize = Math.max(10, 13 / globalScale)
    ctx.font = `${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = '#e6edf3'
    ctx.fillText(label, x, y + r + 5 / globalScale)

    ctx.globalAlpha = 1
  }, [])

  const drawNodeHitArea = useCallback((node: object, color: string, ctx: CanvasRenderingContext2D) => {
    const n = node as FGNode
    ctx.beginPath()
    ctx.arc(n.x ?? 0, n.y ?? 0, 27, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
  }, [])

  const drawLink = useCallback((link: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const l = link as FGLink
    const src = l.source as FGNode
    const tgt = l.target as FGNode
    if (src.x == null || src.y == null || tgt.x == null || tgt.y == null) return

    const opacity = l.dimmed ? 0.08 : 1
    ctx.globalAlpha = opacity

    // Draw line from source circle edge to target circle edge
    const dx = tgt.x - src.x
    const dy = tgt.y - src.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const r = 27
    const arrowLen = 8 / globalScale

    const startX = src.x + (dx / dist) * r
    const startY = src.y + (dy / dist) * r
    const endX = tgt.x - (dx / dist) * (r + arrowLen)
    const endY = tgt.y - (dy / dist) * (r + arrowLen)

    ctx.beginPath()
    ctx.moveTo(startX, startY)
    ctx.lineTo(endX, endY)
    ctx.strokeStyle = l.color
    ctx.lineWidth = l.lineWidth / globalScale
    ctx.stroke()

    // Arrowhead
    const angle = Math.atan2(dy, dx)
    ctx.beginPath()
    ctx.moveTo(endX + arrowLen * Math.cos(angle), endY + arrowLen * Math.sin(angle))
    ctx.lineTo(endX + arrowLen * Math.cos(angle - 0.5), endY + arrowLen * Math.sin(angle - 0.5))
    ctx.lineTo(endX + arrowLen * Math.cos(angle + 0.5), endY + arrowLen * Math.sin(angle + 0.5))
    ctx.closePath()
    ctx.fillStyle = l.color
    ctx.fill()

    // Edge label at midpoint
    if (l.edgeLabel) {
      const midX = (startX + endX) / 2
      const midY = (startY + endY) / 2
      const lFontSize = Math.max(7, 9 / globalScale)
      ctx.font = `${lFontSize}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillStyle = '#8b949e'
      ctx.globalAlpha = l.dimmed ? 0.08 : 1
      ctx.fillText(l.edgeLabel, midX, midY - 2 / globalScale)
    }

    ctx.globalAlpha = 1
  }, [])

  // ── Event handlers ────────────────────────────────────────────────────────────

  // ForceGraph2D has no onNodeDoubleClick — detect it via click timing
  const handleNodeClick = useCallback((node: object, evt: MouseEvent) => {
    void evt
    const n = node as FGNode
    selectedNodeIdRef.current = n.id
    const now = Date.now()
    const last = lastClickRef.current
    if (last?.id === n.id && now - last.time < 400) {
      onNodeDoubleClick(n._node)
      lastClickRef.current = null
    } else {
      lastClickRef.current = { id: n.id, time: now }
      onNodeClick(n._node)
    }
  }, [onNodeClick, onNodeDoubleClick])

  const handleNodeRightClick = useCallback((node: object, evt: MouseEvent) => {
    onNodeContextMenu((node as FGNode)._node, evt.clientX, evt.clientY)
  }, [onNodeContextMenu])

  const handleLinkClick = useCallback((link: object, evt: MouseEvent) => {
    void evt
    onEdgeClick((link as FGLink)._edge)
  }, [onEdgeClick])

  const handleLinkRightClick = useCallback((link: object, evt: MouseEvent) => {
    onEdgeContextMenu((link as FGLink)._edge, evt.clientX, evt.clientY)
  }, [onEdgeContextMenu])

  const handleNodeDragEnd = useCallback((node: object) => {
    const n = node as FGNode
    if (n.x != null && n.y != null) {
      savedPos.current.set(n.id, { x: n.x - 24, y: n.y - 24 })
    }
  }, [])

  const handleBackgroundClick = useCallback(() => {
    selectedNodeIdRef.current = null
    onCanvasTap()
  }, [onCanvasTap])

  const handleEngineStop = useCallback(() => {
    if (!fitNeededRef.current) return
    fitNeededRef.current = false
    graphRef.current?.zoomToFit(0, 80)
  }, [])

  // ── Node visibility (pathFilter hides out-of-path nodes) ─────────────────────
  const nodeVisible = useCallback((node: object) => {
    const n = node as FGNode
    if (pathFilter && !pathFilter.nodeIds.has(n.id)) return false
    return true
  }, [pathFilter])

  const linkVisible = useCallback((link: object) => {
    const l = link as FGLink
    if (pathFilter) {
      const edgeKey = `${l._edge.src_host_id}__${l._edge.dst_host_id}`
      return pathFilter.edgeKeys.has(edgeKey)
    }
    if (credFilter?.mode === 'filter') {
      return l._edge.evidence.some(ev => ev.credential_id === credFilter.credId)
    }
    return true
  }, [pathFilter, credFilter])

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div ref={containerRef} className={styles.canvas}>
      {dims.w > 0 && dims.h > 0 && (
        <ForceGraph2D
          ref={graphRef}
          width={dims.w}
          height={dims.h}
          backgroundColor="#0d1117"
          graphData={fgData as any}
          nodeCanvasObject={drawNode}
          nodeCanvasObjectMode={() => 'replace'}
          nodePointerAreaPaint={drawNodeHitArea}
          nodeVisibility={nodeVisible}
          linkCanvasObject={drawLink}
          linkCanvasObjectMode={() => 'replace'}
          linkVisibility={linkVisible}
          linkHoverPrecision={6}
          onNodeClick={handleNodeClick}
          onNodeRightClick={handleNodeRightClick}
          onLinkClick={handleLinkClick}
          onLinkRightClick={handleLinkRightClick}
          onNodeDragEnd={handleNodeDragEnd}
          onBackgroundClick={handleBackgroundClick}
          onEngineStop={handleEngineStop}
          enableNodeDrag={true}
          minZoom={0.05}
          maxZoom={4}
          cooldownTicks={150}
          warmupTicks={0}
          d3AlphaDecay={0.04}
          d3VelocityDecay={0.8}
        />
      )}
    </div>
  )
}
