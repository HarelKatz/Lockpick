/**
 * GraphView — interactive pivot graph for a single operation.
 * Layout: HostSelector (left) | GraphCanvas (center) | detail panel (right, conditional).
 */
import { useCallback, useEffect, useState } from 'react'
import type {
  Credential,
  GraphEdge,
  GraphNode,
  GraphResponse,
  Host,
  Operation,
  PathResult,
} from '../types'
import { fetchGraph, expandHost } from '../api/graph'
import GraphCanvas from '../components/GraphCanvas'
import HostSelector from '../components/HostSelector'
import HostDetailSidebar from '../components/HostDetailSidebar'
import EdgeDetailPanel from '../components/EdgeDetailPanel'
import NodeContextMenu from '../components/NodeContextMenu'
import EdgeContextMenu from '../components/EdgeContextMenu'
import PathFinder from '../components/PathFinder'
import styles from './GraphView.module.css'

interface Props {
  op: Operation
  allHosts: Host[]
  credentials: Credential[]
}

function mergeGraphResponses(existing: GraphResponse, incoming: GraphResponse): GraphResponse {
  const nodeMap = new Map(existing.nodes.map(n => [n.host_id, n]))
  for (const n of incoming.nodes) nodeMap.set(n.host_id, n)

  const edgeMap = new Map(existing.edges.map(e => [`${e.src_host_id}__${e.dst_host_id}`, e]))
  for (const e of incoming.edges) edgeMap.set(`${e.src_host_id}__${e.dst_host_id}`, e)

  return {
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
  }
}

export default function GraphView({ op, allHosts, credentials }: Props) {
  const [graphData, setGraphData] = useState<GraphResponse>({ nodes: [], edges: [] })
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set())
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [nodeCtxMenu, setNodeCtxMenu] = useState<{ node: GraphNode; x: number; y: number } | null>(null)
  const [edgeCtxMenu, setEdgeCtxMenu] = useState<{ edge: GraphEdge; x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [highlightedPath, setHighlightedPath] = useState<PathResult | null>(null)
  const [credentialFilterId, setCredentialFilterId] = useState<string | null>(null)

  // Load full graph on mount
  const loadFullGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchGraph(op.id)
      setGraphData(data)
      setSelectedIds(new Set(data.nodes.map(n => n.host_id)))
      setHiddenIds(new Set())
    } catch {
      setError('Failed to load graph.')
    } finally {
      setLoading(false)
    }
  }, [op.id])

  useEffect(() => { loadFullGraph() }, [loadFullGraph])

  // Reload when selected host set changes (unless it's the initial load)
  const [isInitialized, setIsInitialized] = useState(false)
  useEffect(() => {
    if (!isInitialized) {
      setIsInitialized(true)
      return
    }
    if (selectedIds.size === 0) {
      setGraphData({ nodes: [], edges: [] })
      return
    }
    async function loadFiltered() {
      setLoading(true)
      try {
        const data = await fetchGraph(op.id, Array.from(selectedIds))
        setGraphData(data)
      } catch {
        // keep previous data on error
      } finally {
        setLoading(false)
      }
    }
    loadFiltered()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, op.id])

  // ── Computed highlight shape for GraphCanvas ──────────────────────────────

  const computedHighlight = highlightedPath
    ? {
        nodeIds: highlightedPath.host_ids,
        edgeKeys: highlightedPath.edges.map(e => `${e.src_host_id}__${e.dst_host_id}`),
      }
    : null

  // ── Event handlers ────────────────────────────────────────────────────────

  function handleNodeClick(node: GraphNode) {
    setSelectedNode(node)
    setSelectedEdge(null)
    setNodeCtxMenu(null)
    setEdgeCtxMenu(null)
  }

  function handleEdgeClick(edge: GraphEdge) {
    setSelectedEdge(edge)
    setSelectedNode(null)
    setNodeCtxMenu(null)
    setEdgeCtxMenu(null)
  }

  async function handleNodeDoubleClick(node: GraphNode) {
    setLoading(true)
    try {
      const expansion = await expandHost(op.id, node.host_id)
      setGraphData(prev => mergeGraphResponses(prev, expansion))
      // Add new neighbors to selected set
      setSelectedIds(prev => {
        const next = new Set(prev)
        for (const n of expansion.nodes) next.add(n.host_id)
        return next
      })
    } catch {
      // ignore — expansion is best-effort
    } finally {
      setLoading(false)
    }
  }

  function handleNodeContextMenu(node: GraphNode, x: number, y: number) {
    setNodeCtxMenu({ node, x, y })
    setEdgeCtxMenu(null)
  }

  function handleEdgeContextMenu(edge: GraphEdge, x: number, y: number) {
    setEdgeCtxMenu({ edge, x, y })
    setNodeCtxMenu(null)
  }

  function handleCanvasTap() {
    setNodeCtxMenu(null)
    setEdgeCtxMenu(null)
  }

  async function handleExpand(node: GraphNode, evidenceType: 'all' | 'key_match' | 'connection_log' | 'indicator') {
    setLoading(true)
    try {
      const expansion = await expandHost(op.id, node.host_id, evidenceType)
      setGraphData(prev => mergeGraphResponses(prev, expansion))
      setSelectedIds(prev => {
        const next = new Set(prev)
        for (const n of expansion.nodes) next.add(n.host_id)
        return next
      })
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  function handleHide(node: GraphNode) {
    setHiddenIds(prev => new Set([...prev, node.host_id]))
    if (selectedNode?.host_id === node.host_id) setSelectedNode(null)
  }

  function handleShowAll() {
    loadFullGraph()
  }

  function handleHighlightPath(path: PathResult | null) {
    setHighlightedPath(path)
    if (path) setCredentialFilterId(null)
  }

  function handleCredentialFilter(credId: string | null) {
    setCredentialFilterId(credId)
    if (credId) setHighlightedPath(null)
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const rightPanel = selectedNode
    ? (
      <HostDetailSidebar
        node={selectedNode}
        edges={graphData.edges.filter(
          e => e.src_host_id === selectedNode.host_id || e.dst_host_id === selectedNode.host_id,
        )}
        onClose={() => setSelectedNode(null)}
      />
    )
    : selectedEdge
    ? (
      <EdgeDetailPanel
        edge={selectedEdge}
        nodes={graphData.nodes}
        onClose={() => setSelectedEdge(null)}
      />
    )
    : null

  return (
    <div className={styles.layout}>
      <HostSelector
        graphNodes={graphData.nodes}
        allHosts={allHosts}
        selectedIds={selectedIds}
        onSelectionChange={ids => {
          setSelectedIds(ids)
          setIsInitialized(true)
        }}
        onShowAll={handleShowAll}
        loading={loading}
      />

      <div className={styles.canvasArea}>
        {/* Toolbar: credential filter */}
        <div className={styles.graphToolbar}>
          <select
            className={styles.credFilterSelect}
            value={credentialFilterId ?? ''}
            onChange={e => handleCredentialFilter(e.target.value || null)}
          >
            <option value="">Filter by credential…</option>
            {credentials.map(c => (
              <option key={c.id} value={c.id}>
                {c.name
                  ? c.name
                  : c.fingerprint
                  ? c.fingerprint.slice(0, 24) + '…'
                  : c.id.slice(0, 8)}
              </option>
            ))}
          </select>
          {credentialFilterId && (
            <button
              className={styles.clearFilterBtn}
              onClick={() => handleCredentialFilter(null)}
            >
              Clear filter
            </button>
          )}
        </div>

        <div className={styles.canvasWrapper}>
          {error && (
            <div className={styles.error}>
              {error}
              <button className={styles.retryBtn} onClick={loadFullGraph}>Retry</button>
            </div>
          )}

          {!error && graphData.nodes.length === 0 && !loading && (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>⬡</div>
              <p className={styles.emptyText}>No hosts to display.</p>
              <p className={styles.emptyHint}>Select hosts from the list or add data first.</p>
            </div>
          )}

          <GraphCanvas
            graphData={graphData}
            hiddenIds={hiddenIds}
            highlightedPath={computedHighlight}
            credentialFilterId={credentialFilterId}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onNodeDoubleClick={handleNodeDoubleClick}
            onNodeContextMenu={handleNodeContextMenu}
            onEdgeContextMenu={handleEdgeContextMenu}
            onCanvasTap={handleCanvasTap}
          />
        </div>

        <PathFinder
          nodes={graphData.nodes}
          opId={op.id}
          onHighlightPath={handleHighlightPath}
        />
      </div>

      {rightPanel}

      {nodeCtxMenu && (
        <NodeContextMenu
          node={nodeCtxMenu.node}
          x={nodeCtxMenu.x}
          y={nodeCtxMenu.y}
          onExpand={handleExpand}
          onHide={handleHide}
          onClose={() => setNodeCtxMenu(null)}
        />
      )}

      {edgeCtxMenu && (
        <EdgeContextMenu
          edge={edgeCtxMenu.edge}
          nodes={graphData.nodes}
          x={edgeCtxMenu.x}
          y={edgeCtxMenu.y}
          onViewEvidence={edge => { setSelectedEdge(edge); setSelectedNode(null) }}
          onClose={() => setEdgeCtxMenu(null)}
        />
      )}
    </div>
  )
}
