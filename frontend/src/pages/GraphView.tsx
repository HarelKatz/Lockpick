/**
 * GraphView — interactive pivot graph for a single operation.
 * Layout: HostSelector (left) | GraphCanvas (center) | detail panel (right, conditional).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import GraphCanvas, { type CredFilter, type PathFilter, type LayoutName } from '../components/GraphCanvas'
import HostSelector from '../components/HostSelector'
import HostDetailSidebar from '../components/HostDetailSidebar'
import EdgeDetailPanel from '../components/EdgeDetailPanel'
import PathDetailPanel from '../components/PathDetailPanel'
import NodeContextMenu from '../components/NodeContextMenu'
import EdgeContextMenu from '../components/EdgeContextMenu'
import PathFinder from '../components/PathFinder'
import { statusColors, STATUS_LABELS } from '../theme'
import styles from './GraphView.module.css'

interface Props {
  op: Operation
  allHosts: Host[]
  credentials: Credential[]
  focusHostId?: string | null
  onRegisterReload?: (reload: () => void) => void
}

/** Human-readable label for a credential, used in sidebar and panel displays. */
function credLabel(c: Credential): string {
  const type = c.key_type
    ? c.key_type.replace('ssh-', '').toUpperCase()
    : c.cred_type.replace('_', ' ')
  const label = c.name
    || c.comment
    || (c.fingerprint ? c.fingerprint.slice(7, 23) + '…' : c.id.slice(0, 8))
  return `${type}: ${label}`
}

/**
 * Merge two GraphResponse objects, with `incoming` winning on conflicts.
 * Node and edge maps are keyed by host_id and "src__dst" respectively.
 */
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

export default function GraphView({ op, allHosts, credentials, focusHostId, onRegisterReload }: Props) {
  const [graphData, setGraphData] = useState<GraphResponse>({ nodes: [], edges: [] })
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set())
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [nodeCtxMenu, setNodeCtxMenu] = useState<{ node: GraphNode; x: number; y: number } | null>(null)
  const [edgeCtxMenu, setEdgeCtxMenu] = useState<{ edge: GraphEdge; x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pathFilter, setPathFilter] = useState<PathFilter | null>(null)
  const [credFilter, setCredFilter] = useState<CredFilter | null>(null)
  const [selectedPath, setSelectedPath] = useState<PathResult | null>(null)
  const [layout, setLayout] = useState<LayoutName>('cola')
  const [lockedIds, setLockedIds] = useState<Set<string>>(new Set())
  const [statusFilters, setStatusFilters] = useState<Set<string>>(new Set())
  const [panelMode, setPanelMode] = useState<'push' | 'overlay'>('overlay')
  const canvasAreaRef = useRef<HTMLDivElement>(null)

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

  // Expose loadFullGraph to parent (for WS-driven refresh from Workspace)
  useEffect(() => { onRegisterReload?.(loadFullGraph) }, [loadFullGraph, onRegisterReload])

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
  // isInitialized intentionally excluded: including it would re-run on the flag flip itself.
  }, [selectedIds, op.id])

  // ── Selectable hosts for PathFinder (all known hosts, not just visible) ──────

  const allSelectableHosts = useMemo(() => {
    const map = new Map<string, { id: string; nickname: string }>()
    for (const h of allHosts) map.set(h.id, { id: h.id, nickname: h.nickname })
    for (const n of graphData.nodes) map.set(n.host_id, { id: n.host_id, nickname: n.nickname })
    return Array.from(map.values())
  }, [allHosts, graphData.nodes])

  // ── Event handlers ────────────────────────────────────────────────────────

  function getPanelMode(clientX: number): 'push' | 'overlay' {
    if (!canvasAreaRef.current) return 'overlay'
    const rect = canvasAreaRef.current.getBoundingClientRect()
    return clientX > rect.right - 320 ? 'push' : 'overlay'
  }

  function handleNodeClick(node: GraphNode, clientX: number) {
    if (rightPanel === null) setPanelMode(getPanelMode(clientX))
    setSelectedNode(node)
    setSelectedEdge(null)
    setNodeCtxMenu(null)
    setEdgeCtxMenu(null)
  }

  function handleEdgeClick(edge: GraphEdge, clientX: number) {
    if (rightPanel === null) setPanelMode(getPanelMode(clientX))
    setSelectedEdge(edge)
    setSelectedNode(null)
    setNodeCtxMenu(null)
    setEdgeCtxMenu(null)
  }

  function handleNodeDoubleClick(node: GraphNode) {
    setLockedIds(prev => {
      const next = new Set(prev)
      if (next.has(node.host_id)) next.delete(node.host_id)
      else next.add(node.host_id)
      return next
    })
  }

  function handleToggleLock(node: GraphNode) {
    handleNodeDoubleClick(node)
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
      setHiddenIds(prev => {
        const next = new Set(prev)
        for (const n of expansion.nodes) next.delete(n.host_id)
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
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.delete(node.host_id)
      return next
    })
    if (selectedNode?.host_id === node.host_id) setSelectedNode(null)
  }

  function handleShowAll() {
    loadFullGraph()
  }

  // Del key hides the currently selected node
  const selectedNodeRef = useRef(selectedNode)
  useEffect(() => { selectedNodeRef.current = selectedNode }, [selectedNode])
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      const node = selectedNodeRef.current
      if (node) {
        e.preventDefault()
        handleHide(node)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  // Empty deps intentional: handleHide is accessed via selectedNodeRef to avoid
  // re-subscribing the keydown listener on every render while still seeing latest state.
  }, [])

  function handleHighlightPath(path: PathResult | null) {
    if (path) {
      // Ensure all path nodes are loaded onto the graph
      setSelectedIds(prev => {
        const next = new Set(prev)
        for (const id of path.host_ids) next.add(id)
        return next
      })
      setPathFilter({
        nodeIds: new Set(path.host_ids),
        edgeKeys: new Set(path.edges.map(e => `${e.src_host_id}__${e.dst_host_id}`)),
      })
      setCredFilter(null)
      setSelectedPath(path)
      setSelectedNode(null)
      setSelectedEdge(null)
    } else {
      setPathFilter(null)
      setSelectedPath(null)
    }
  }

  function handleCredentialFilter(credId: string | null) {
    if (credId) {
      setCredFilter(prev => ({ credId, mode: prev?.credId === credId ? (prev.mode) : 'highlight' }))
      setPathFilter(null)
    } else {
      setCredFilter(null)
    }
  }

  function handleCredMode(mode: 'highlight' | 'filter') {
    setCredFilter(prev => prev ? { ...prev, mode } : null)
  }

  function handleToggleStatusFilter(status: string) {
    setStatusFilters(prev => {
      const next = new Set(prev)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const rightPanel = selectedPath
    ? (
      <PathDetailPanel
        path={selectedPath}
        nodes={graphData.nodes}
        onClose={() => setSelectedPath(null)}
      />
    )
    : selectedNode
    ? (
      <HostDetailSidebar
        node={selectedNode}
        edges={graphData.edges.filter(
          e => e.src_host_id === selectedNode.host_id || e.dst_host_id === selectedNode.host_id,
        )}
        host={allHosts.find(h => h.id === selectedNode.host_id) ?? null}
        onClose={() => setSelectedNode(null)}
        onHostUpdated={loadFullGraph}
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

  // Keep last panel content in the DOM during the close transition so it slides back out
  const lastPanelRef = useRef<React.ReactNode>(null)
  if (rightPanel !== null) lastPanelRef.current = rightPanel

  return (
    <div className={styles.layout}>
      <HostSelector
        graphNodes={graphData.nodes}
        allHosts={allHosts}
        selectedIds={selectedIds}
        onSelectionChange={ids => {
          setHiddenIds(prev => {
            const next = new Set(prev)
            for (const id of ids) next.delete(id)
            return next
          })
          setSelectedIds(ids)
          setIsInitialized(true)
        }}
        onShowAll={handleShowAll}
        loading={loading}
      />

      <div ref={canvasAreaRef} className={styles.canvasArea}>
        {/* Toolbar: layout + credential filter + status filter */}
        <div className={styles.graphToolbar}>
          <label className={styles.toolbarLabel}>Layout:</label>
          <select
            className={styles.credFilterSelect}
            value={layout}
            onChange={e => setLayout(e.target.value as LayoutName)}
          >
            <option value="cola">Force-directed</option>
            <option value="cose-bilkent">Organic</option>
            <option value="breadthfirst">Hierarchical</option>
            <option value="grid">Grid</option>
            <option value="circle">Circle</option>
          </select>
          <span className={styles.toolbarDivider} />
          <select
            className={styles.credFilterSelect}
            value={credFilter?.credId ?? ''}
            onChange={e => handleCredentialFilter(e.target.value || null)}
          >
            <option value="">Filter by credential…</option>
            {credentials.map(c => (
              <option key={c.id} value={c.id}>{credLabel(c)}</option>
            ))}
          </select>
          {credFilter && (
            <>
              <button
                className={`${styles.modeBtn} ${credFilter.mode === 'highlight' ? styles.modeBtnActive : ''}`}
                onClick={() => handleCredMode('highlight')}
              >
                Highlight
              </button>
              <button
                className={`${styles.modeBtn} ${credFilter.mode === 'filter' ? styles.modeBtnActive : ''}`}
                onClick={() => handleCredMode('filter')}
              >
                Filter
              </button>
              <button
                className={styles.clearFilterBtn}
                onClick={() => handleCredentialFilter(null)}
              >
                Clear
              </button>
              {(() => {
                const c = credentials.find(cr => cr.id === credFilter.credId)
                return c ? (
                  <span className={styles.credActiveLabel} title={credLabel(c)}>
                    {credLabel(c)}
                  </span>
                ) : null
              })()}
            </>
          )}
          <span className={styles.toolbarDivider} />
          <label className={styles.toolbarLabel}>Status:</label>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <button
              key={value}
              className={`${styles.statusPill} ${statusFilters.has(value) ? styles.statusPillActive : ''}`}
              style={statusFilters.has(value) ? { borderColor: statusColors[value], color: statusColors[value] } : undefined}
              onClick={() => handleToggleStatusFilter(value)}
              title={label}
            >
              <span
                className={styles.statusDot}
                style={{ background: statusColors[value] }}
              />
              {label}
            </button>
          ))}
          {statusFilters.size > 0 && (
            <button
              className={styles.clearFilterBtn}
              onClick={() => setStatusFilters(new Set())}
            >
              Clear
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
            pathFilter={pathFilter}
            credFilter={credFilter}
            statusFilters={statusFilters}
            layout={layout}
            lockedIds={lockedIds}
            focusHostId={focusHostId}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onNodeDoubleClick={handleNodeDoubleClick}
            onNodeContextMenu={handleNodeContextMenu}
            onEdgeContextMenu={handleEdgeContextMenu}
            onCanvasTap={handleCanvasTap}
          />
        </div>

        <PathFinder
          nodes={allSelectableHosts}
          opId={op.id}
          onHighlightPath={handleHighlightPath}
        />
      </div>

      <div className={[styles.rightPanelWrapper, rightPanel ? styles.rightPanelOpen : '', panelMode === 'overlay' ? styles.rightPanelOverlay : ''].join(' ')}>
        {rightPanel ?? lastPanelRef.current}
      </div>

      {nodeCtxMenu && (
        <NodeContextMenu
          node={nodeCtxMenu.node}
          x={nodeCtxMenu.x}
          y={nodeCtxMenu.y}
          isLocked={lockedIds.has(nodeCtxMenu.node.host_id)}
          onExpand={handleExpand}
          onHide={handleHide}
          onToggleLock={() => handleToggleLock(nodeCtxMenu.node)}
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
