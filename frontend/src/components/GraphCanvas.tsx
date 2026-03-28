/**
 * Cytoscape.js graph canvas.
 * Purely driven by props — parent owns graphData and hiddenIds.
 * Events bubble up via callbacks.
 */
import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import coseBilkent from 'cytoscape-cose-bilkent'
import type { GraphEdge, GraphNode, GraphResponse } from '../types'
import styles from './GraphCanvas.module.css'

cytoscape.use(coseBilkent)

interface Props {
  graphData: GraphResponse
  hiddenIds: Set<string>
  onNodeClick: (node: GraphNode) => void
  onEdgeClick: (edge: GraphEdge) => void
  onNodeDoubleClick: (node: GraphNode) => void
  onNodeContextMenu: (node: GraphNode, x: number, y: number) => void
  onEdgeContextMenu: (edge: GraphEdge, x: number, y: number) => void
  onCanvasTap: () => void
}

export default function GraphCanvas({
  graphData,
  hiddenIds,
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
            'background-color': '#1c2128',
            'border-color': '#30363d',
            'border-width': 1,
            'label': 'data(label)',
            'color': '#c9d1d9',
            'font-size': 11,
            'text-valign': 'bottom',
            'text-margin-y': 4,
            'width': 36,
            'height': 36,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#58a6ff',
            'border-width': 2,
          },
        },
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'width': 2,
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
          style: { 'width': 3 },
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
            edgeLabel: `${e.evidence.length}`,
            _edge: e,
          },
        })),
    ]

    cy.elements().remove()
    cy.add(elements)

    if (elements.length > 0) {
      cy.layout({
        name: 'cose-bilkent',
        animate: false,
        randomize: true,
        nodeDimensionsIncludeLabels: true,
        idealEdgeLength: 150,
        nodeRepulsion: 8000,
      } as cytoscape.LayoutOptions).run()
    }
  }, [graphData, hiddenIds])

  return <div ref={containerRef} className={styles.canvas} />
}
