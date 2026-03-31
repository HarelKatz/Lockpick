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

interface HighlightedPath {
  nodeIds: string[]
  edgeKeys: string[]
}

interface Props {
  graphData: GraphResponse
  hiddenIds: Set<string>
  highlightedPath: HighlightedPath | null
  credentialFilterId: string | null
  onNodeClick: (node: GraphNode) => void
  onEdgeClick: (edge: GraphEdge) => void
  onNodeDoubleClick: (node: GraphNode) => void
  onNodeContextMenu: (node: GraphNode, x: number, y: number) => void
  onEdgeContextMenu: (edge: GraphEdge, x: number, y: number) => void
  onCanvasTap: () => void
}

function computeEdgeLabel(e: GraphEdge): string {
  const primary = e.evidence[0]?.type ?? 'unknown'
  const short: Record<string, string> = {
    key_match: 'key',
    connection_log: 'conn',
    bash_history: 'bash',
    known_hosts: 'known',
  }
  return `${short[primary] ?? primary} \u2022 ${e.evidence.length}`
}

function buildLayoutOptions(): cytoscape.LayoutOptions {
  return {
    name: 'cola',
    animate: true,
    infinite: false,
    fit: true,
    padding: 90,
    nodeSpacing: 40,
    edgeLength: 180,
    maxSimulationTime: 3000,
    convergenceThreshold: 0.01,
    randomize: true,
  } as cytoscape.LayoutOptions
}

export default function GraphCanvas({
  graphData,
  hiddenIds,
  highlightedPath,
  credentialFilterId,
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

  // ── Initialize cytoscape once on mount ──────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#1a2332',
            'border-color': '#3d8bcd',
            'border-width': 2,
            'label': 'data(label)',
            'color': '#e6edf3',
            'font-size': 11,
            'text-valign': 'bottom',
            'text-margin-y': 5,
            'width': 40,
            'height': 40,
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
        // Dimmed elements
        {
          selector: '.dimmed',
          style: {
            'opacity': 0.18,
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

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])  // mount-only — events use cbRef for freshness

  // ── Rebuild elements when graphData or hiddenIds change ─────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const visibleNodeIds = new Set(
      graphData.nodes
        .filter(n => !hiddenIds.has(n.host_id))
        .map(n => n.host_id),
    )

    const elements: cytoscape.ElementDefinition[] = [
      ...graphData.nodes
        .filter(n => visibleNodeIds.has(n.host_id))
        .map(n => ({
          group: 'nodes' as const,
          data: {
            id: n.host_id,
            label: n.nickname,
            hasCredentials: n.credential_count > 0,
            _node: n,
          },
        })),
      ...graphData.edges
        .filter(
          e =>
            visibleNodeIds.has(e.src_host_id) &&
            visibleNodeIds.has(e.dst_host_id),
        )
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
        })),
    ]

    function rebuildAndLayout() {
      const c = cyRef.current
      if (!c) return
      c.elements().remove()
      if (elements.length === 0) return

      const added = c.add(elements)
      added.style({ opacity: 0 })

      const layout = c.layout(buildLayoutOptions())
      layout.one('layoutstop', () => {
        c.fit(undefined, 90)
        c.elements().animate(
          { style: { opacity: 1 } } as cytoscape.AnimationOptions,
          { duration: 250 },
        )
      })
      layout.run()
    }

    // Animate out nodes that are going away before rebuilding
    const goingAway = cy.nodes().filter(n => !visibleNodeIds.has(n.id()))
    if (goingAway.length > 0) {
      goingAway.stop(true, false)
      goingAway.animate(
        { style: { opacity: 0 } } as cytoscape.AnimationOptions,
        { duration: 200, complete: rebuildAndLayout },
      )
    } else {
      rebuildAndLayout()
    }
  }, [graphData, hiddenIds])

  // ── Apply path/credential highlighting ──────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.elements().removeClass('path-highlight dimmed')

    if (highlightedPath) {
      const pathNodeSet = new Set(highlightedPath.nodeIds)
      const pathEdgeSet = new Set(highlightedPath.edgeKeys)
      cy.nodes().forEach(n => {
        if (pathNodeSet.has(n.id())) n.addClass('path-highlight')
        else n.addClass('dimmed')
      })
      cy.edges().forEach(e => {
        if (pathEdgeSet.has(e.id())) e.addClass('path-highlight')
        else e.addClass('dimmed')
      })
    } else if (credentialFilterId) {
      cy.edges().forEach(e => {
        const edge = e.data('_edge') as GraphEdge
        const used = edge?.evidence?.some(ev => ev.credential_id === credentialFilterId)
        if (!used) e.addClass('dimmed')
      })
    }
  }, [highlightedPath, credentialFilterId])

  return <div ref={containerRef} className={styles.canvas} />
}
