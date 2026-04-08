/**
 * Cytoscape.js graph canvas.
 * Purely driven by props — parent owns graphData and hiddenIds.
 * Events bubble up via callbacks.
 */
import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import coseBilkent from 'cytoscape-cose-bilkent'
import cola from 'cytoscape-cola'
import type { GraphEdge, GraphNode, GraphResponse } from '../types'
import styles from './GraphCanvas.module.css'

cytoscape.use(coseBilkent)
cytoscape.use(cola)

export type LayoutName = 'cola' | 'cose-bilkent' | 'breadthfirst' | 'grid' | 'circle'

export interface CredFilter {
  credId: string
  mode: 'highlight' | 'filter'
}

export interface PathFilter {
  nodeIds: Set<string>
  edgeKeys: Set<string>
}

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

function computeEdgeLabel(e: GraphEdge): string {
  // Prefer actual connection_type from connection_log evidence
  for (const ev of e.evidence) {
    if (ev.type === 'connection_log' && ev.connection_type) {
      return ev.connection_type.toUpperCase()
    }
  }
  if (e.evidence.some(ev => ev.type === 'key_match')) return 'key match'
  if (e.evidence.some(ev => ev.type === 'bash_history')) return 'bash history'
  if (e.evidence.some(ev => ev.type === 'known_hosts')) return 'known hosts'
  return 'connection'
}

function buildLayoutOptions(layout: LayoutName): cytoscape.LayoutOptions {
  switch (layout) {
    case 'cose-bilkent':
      return {
        name: 'cose-bilkent',
        animate: true,
        fit: true,
        padding: 90,
        nodeDimensionsIncludeLabels: true,
        randomize: true,
        idealEdgeLength: 180,
        edgeElasticity: 0.45,
      } as cytoscape.LayoutOptions
    case 'breadthfirst':
      return {
        name: 'breadthfirst',
        animate: true,
        fit: true,
        padding: 90,
        directed: true,
        spacingFactor: 1.5,
      } as cytoscape.LayoutOptions
    case 'grid':
      return {
        name: 'grid',
        animate: true,
        fit: true,
        padding: 90,
      } as cytoscape.LayoutOptions
    case 'circle':
      return {
        name: 'circle',
        animate: true,
        fit: true,
        padding: 90,
      } as cytoscape.LayoutOptions
    case 'cola':
    default:
      return {
        name: 'cola',
        animate: true,
        infinite: false,
        fit: true,
        padding: 90,
        nodeSpacing: 60,
        edgeLength: 240,
        maxSimulationTime: 3000,
        convergenceThreshold: 0.01,
        randomize: false,
        avoidOverlap: true,
      } as cytoscape.LayoutOptions
  }
}

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
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  // Keep callbacks fresh so stable event handlers always call the latest version
  const cbRef = useRef({ onNodeClick, onEdgeClick, onNodeDoubleClick, onNodeContextMenu, onEdgeContextMenu, onCanvasTap })
  useEffect(() => {
    cbRef.current = { onNodeClick, onEdgeClick, onNodeDoubleClick, onNodeContextMenu, onEdgeContextMenu, onCanvasTap }
  })

  // Track current layout for use inside element-rebuild effect
  const layoutRef = useRef<LayoutName>(layout)
  useEffect(() => { layoutRef.current = layout }, [layout])

  // Keep lockedIds fresh so the drag-settle handler can re-apply user locks
  const lockedIdsRef = useRef<Set<string> | undefined>(lockedIds)
  useEffect(() => { lockedIdsRef.current = lockedIds }, [lockedIds])

  // ── Initialize cytoscape once on mount ──────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      pixelRatio: 'auto',
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#1a2332',
            'border-color': '#3d8bcd',
            'border-width': 2,
            'label': 'data(label)',
            'color': '#e6edf3',
            'font-size': 18,
            'min-zoomed-font-size': 8,
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'width': 48,
            'height': 48,
            'text-background-color': '#0d1117',
            'text-background-opacity': 0.7,
            'text-background-padding': '2px',
            'text-background-shape': 'roundrectangle',
          },
        },
        {
          // Nodes with credentials get an amber ring
          selector: 'node[?hasCredentials]',
          style: {
            'border-color': '#d29922',
            'border-width': 3,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#58a6ff',
            'border-width': 3,
            'background-color': '#1f2d3d',
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'width': 3,
            'label': 'data(edgeLabel)',
            'font-size': 9,
            'color': '#8b949e',
            'text-rotation': 'autorotate',
            'text-margin-y': -6,
          },
        },
        {
          selector: 'edge[confidence = "confirmed"]',
          style: {
            'line-color': '#3fb950',
            'target-arrow-color': '#3fb950',
          },
        },
        {
          selector: 'edge[confidence = "observed"]',
          style: {
            'line-color': '#d29922',
            'target-arrow-color': '#d29922',
          },
        },
        {
          selector: 'edge[confidence = "indicator"]',
          style: {
            'line-color': '#6e7681',
            'target-arrow-color': '#6e7681',
          },
        },
        {
          selector: 'edge:selected',
          style: { 'width': 5 },
        },
        // Path highlighting — coral/red
        {
          selector: 'node.path-highlight',
          style: {
            'border-color': '#f78166',
            'border-width': 4,
            'background-color': '#2d1f1f',
          },
        },
        {
          selector: 'edge.path-highlight',
          style: {
            'line-color': '#f78166',
            'target-arrow-color': '#f78166',
            'width': 5,
          },
        },
        // Dimmed elements (for highlight mode)
        {
          selector: '.dimmed',
          style: {
            'opacity': 0.18,
          },
        },
        // Locked nodes — orange border, cannot be dragged
        {
          selector: 'node.node-locked',
          style: {
            'border-color': '#f78166',
            'border-width': 3,
          },
        },
      ],
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    })

    // Stable event handlers — always invoke the latest callback via cbRef
    cy.on('tap', 'node', evt => {
      cbRef.current.onNodeClick(evt.target.data('_node') as GraphNode)
    })
    cy.on('tap', 'edge', evt => {
      cbRef.current.onEdgeClick(evt.target.data('_edge') as GraphEdge)
    })
    cy.on('dbltap', 'node', evt => {
      cbRef.current.onNodeDoubleClick(evt.target.data('_node') as GraphNode)
    })
    cy.on('cxttap', 'node', evt => {
      const me = evt.originalEvent as MouseEvent
      cbRef.current.onNodeContextMenu(evt.target.data('_node') as GraphNode, me.clientX, me.clientY)
    })
    cy.on('cxttap', 'edge', evt => {
      const me = evt.originalEvent as MouseEvent
      cbRef.current.onEdgeContextMenu(evt.target.data('_edge') as GraphEdge, me.clientX, me.clientY)
    })
    cy.on('tap', evt => {
      if (evt.target === cy) cbRef.current.onCanvasTap()
    })

    // Track which node is being dragged so the free handler knows its neighbors.
    let grabbedId: string | null = null
    cy.on('grab', 'node', evt => {
      grabbedId = evt.target.id()
    })

    // After releasing a drag, settle only the dragged node and its direct
    // neighbors — all other nodes stay put.
    cy.on('free', 'node', () => {
      if (layoutRef.current !== 'cola') return
      const id = grabbedId
      grabbedId = null
      if (!id) return

      // Lock everything outside the immediate neighborhood so the cola settle
      // only moves the dragged node and its direct neighbors.
      const neighborhood = cy.$id(id).closedNeighborhood('node')
      cy.nodes().not(neighborhood).lock()

      const settleLayout = cy.layout({
        name: 'cola',
        animate: true,
        infinite: false,
        fit: false,
        padding: 90,
        nodeSpacing: 60,
        edgeLength: 240,
        maxSimulationTime: 1500,
        convergenceThreshold: 0.005,
        randomize: false,
        avoidOverlap: true,
      } as cytoscape.LayoutOptions)

      settleLayout.on('layoutstop', () => {
        // Unlock all, then re-apply user-set locks so double-click locks survive.
        cy.nodes().forEach(n => {
          if (lockedIdsRef.current?.has(n.id())) {
            n.lock()
            n.addClass('node-locked')
          } else {
            n.unlock()
            n.removeClass('node-locked')
          }
        })
      })

      settleLayout.run()
    })

    cyRef.current = cy

    // Resize cytoscape when container becomes visible (e.g. tab switch from display:none)
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) {
        cy.resize()
        if (cy.elements().length > 0) cy.fit(undefined, 90)
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [])  // mount-only — events use cbRef for freshness

  // ── Rebuild/update elements when graphData or hiddenIds change ───────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const visibleNodeIds = new Set(
      graphData.nodes
        .filter(n => !hiddenIds.has(n.host_id))
        .map(n => n.host_id),
    )

    // All elements that should be on canvas
    const allNodes: cytoscape.ElementDefinition[] = graphData.nodes
      .filter(n => visibleNodeIds.has(n.host_id))
      .map(n => ({
        group: 'nodes' as const,
        data: {
          id: n.host_id,
          label: n.nickname,
          hasCredentials: n.credential_count > 0,
          _node: n,
        },
      }))

    const allEdges: cytoscape.ElementDefinition[] = graphData.edges
      .filter(e => visibleNodeIds.has(e.src_host_id) && visibleNodeIds.has(e.dst_host_id))
      .map(e => ({
        group: 'edges' as const,
        data: {
          id: `${e.src_host_id}__${e.dst_host_id}`,
          source: e.src_host_id,
          target: e.dst_host_id,
          confidence: e.confidence,
          edgeLabel: computeEdgeLabel(e),
          _edge: e,
        },
      }))

    const allElements = [...allNodes, ...allEdges]

    const currentNodeIds = new Set(cy.nodes().map(n => n.id()))
    const currentEdgeIds = new Set(cy.edges().map(e => e.id()))

    // Nodes currently on canvas that are no longer visible
    const goingAway = cy.nodes().filter(n => !visibleNodeIds.has(n.id()))

    // New elements not yet on canvas
    const incomingNodes = allNodes.filter(el => !currentNodeIds.has(el.data.id as string))
    const incomingEdges = allEdges.filter(el => !currentEdgeIds.has(el.data.id as string))
    const incoming = [...incomingNodes, ...incomingEdges]

    function fullRebuild() {
      const c = cyRef.current
      if (!c) return
      c.elements().remove()
      if (allElements.length === 0) return

      const added = c.add(allElements)
      added.style({ opacity: 0 })

      const cyLayout = c.layout(buildLayoutOptions(layoutRef.current))
      cyLayout.one('layoutstop', () => {
        c.fit(undefined, 90)
        c.elements().animate(
          { style: { opacity: 1 } } as cytoscape.AnimationOptions,
          { duration: 250 },
        )
      })
      cyLayout.run()
    }

    if (goingAway.length > 0) {
      // Nodes being hidden — animate them out then rebuild
      goingAway.stop(true, false)
      goingAway.animate(
        { style: { opacity: 0 } } as cytoscape.AnimationOptions,
        { duration: 200, complete: fullRebuild },
      )
    } else if (incoming.length > 0 && currentNodeIds.size > 0) {
      // Expand: only new elements — add them without disturbing existing nodes
      const added = cy.add(incoming)
      added.style({ opacity: 0 })
      const cyLayout = cy.layout(buildLayoutOptions(layoutRef.current))
      cyLayout.one('layoutstop', () => {
        cy.fit(undefined, 90)
        added.animate(
          { style: { opacity: 1 } } as cytoscape.AnimationOptions,
          { duration: 250 },
        )
      })
      cyLayout.run()
    } else if (currentNodeIds.size === 0) {
      // Initial load or cleared graph
      fullRebuild()
    }
    // else: no structural change (shouldn't happen in normal flow)
  }, [graphData, hiddenIds])

  // ── Re-run layout when layout prop changes ───────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || cy.elements().length === 0) return
    cy.layout(buildLayoutOptions(layout)).run()
  }, [layout])

  // ── Apply path / credential filter ──────────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    // Reset everything
    cy.elements().removeClass('path-highlight dimmed')
    cy.nodes().style('display', 'element')
    cy.edges().style('display', 'element')

    if (pathFilter) {
      // Show only path nodes and edges; hide everything else
      cy.nodes().forEach(n => {
        if (pathFilter.nodeIds.has(n.id())) {
          n.addClass('path-highlight')
        } else {
          n.style('display', 'none')
        }
      })
      cy.edges().forEach(e => {
        if (pathFilter.edgeKeys.has(e.id())) {
          e.addClass('path-highlight')
        } else {
          e.style('display', 'none')
        }
      })
    } else if (credFilter) {
      if (credFilter.mode === 'filter') {
        // Hide edges not using this credential, hide nodes with no visible edges
        cy.edges().forEach(e => {
          const edge = e.data('_edge') as GraphEdge
          const matches = edge?.evidence?.some(ev => ev.credential_id === credFilter.credId)
          if (matches) {
            e.addClass('path-highlight')
          } else {
            e.style('display', 'none')
          }
        })
        cy.nodes().forEach(n => {
          const hasVisible = n.connectedEdges().some(
            e => e.style('display') !== 'none',
          )
          if (!hasVisible) n.style('display', 'none')
        })
      } else {
        // Highlight mode: keep all visible, highlight matching edges + their nodes; dim rest
        const highlightedNodeIds = new Set<string>()
        cy.edges().forEach(e => {
          const edge = e.data('_edge') as GraphEdge
          const matches = edge?.evidence?.some(ev => ev.credential_id === credFilter.credId)
          if (matches) {
            e.addClass('path-highlight')
            highlightedNodeIds.add(edge.src_host_id)
            highlightedNodeIds.add(edge.dst_host_id)
          } else {
            e.addClass('dimmed')
          }
        })
        cy.nodes().forEach(n => {
          if (highlightedNodeIds.has(n.id())) n.addClass('path-highlight')
          else n.addClass('dimmed')
        })
      }
    }
  // graphData is included so the filter re-applies after a graph rebuild
  // (fullRebuild removes all elements, so classes/display set by this effect
  // would be lost without re-running when graphData changes)
  }, [pathFilter, credFilter, graphData])

  // ── Apply/clear node locks ────────────────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().forEach(n => {
      if (lockedIds?.has(n.id())) {
        n.lock()
        n.addClass('node-locked')
      } else {
        n.unlock()
        n.removeClass('node-locked')
      }
    })
  }, [lockedIds, graphData])  // re-apply after rebuild

  // ── Animate to a focused host ─────────────────────────────────────────────
  useEffect(() => {
    if (!focusHostId) return
    const cy = cyRef.current
    if (!cy) return
    const ele = cy.getElementById(focusHostId)
    if (ele.length === 0) return
    cy.animate({ fit: { eles: ele, padding: 160 }, duration: 400 })
  }, [focusHostId])

  return <div ref={containerRef} className={styles.canvas} />
}
