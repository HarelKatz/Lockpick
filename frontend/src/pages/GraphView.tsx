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
  MergeCandidate,
  Operation,
  PathResult,
} from '../types'
import { fetchGraph, expandHost, findPaths } from '../api/graph'
import GraphCanvas, { type CredFilter, type PathFilter, type LayoutName } from '../components/GraphCanvas'
import HostSelector from '../components/HostSelector'
import HostDetailSidebar from '../components/HostDetailSidebar'
import MergeHostDialog from '../components/MergeHostDialog'
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

/** Format an epoch-ms instant as a compact UTC label for the time slider. */
function fmtInstant(ms: number): string {
  return new Date(ms).toISOString().slice(0, 16).replace('T', ' ')
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
  // First shift-selected host; the second shift-click resolves the BFS path.
  const [pathAnchorId, setPathAnchorId] = useState<string | null>(null)
  const [pathNotice, setPathNotice] = useState<string | null>(null)
  const [layout, setLayout] = useState<LayoutName>('cola')
  const [lockedIds, setLockedIds] = useState<Set<string>>(new Set())
  const [statusFilters, setStatusFilters] = useState<Set<string>>(new Set())
  // Time slider: two independent handle positions (epoch ms). The window is
  // derived as [min,max] of the two (see timeWindow). Independent handles — rather
  // than a mutually clamped {start,end} — prevent the dual-range soft-lock where
  // both thumbs pile onto one domain edge and neither can be dragged back.
  const [timeSel, setTimeSel] = useState<{ a: number; b: number } | null>(null)
  const [panelMode, setPanelMode] = useState<'push' | 'overlay'>('overlay')
  // Two-step merge state: { source, targetCandidate? } when the dialog is
  // open. Set by either the "Merge into…" button on the sidebar (no
  // targetCandidate) or by a CollectionPanel candidate button (target = the
  // sidebar's current host).
  const [mergeState, setMergeState] = useState<{ source: Host; targetCandidate?: Host } | null>(null)
  const canvasAreaRef = useRef<HTMLDivElement>(null)

  // Set by loadFullGraph before it updates selectedIds to prevent the selectedIds
  // useEffect from firing a redundant second fetchGraph call (double-fetch race).
  const skipSelectedEffect = useRef(false)

  // Load full graph on mount
  const loadFullGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchGraph(op.id)
      setGraphData(data)
      skipSelectedEffect.current = true
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
    if (skipSelectedEffect.current) {
      skipSelectedEffect.current = false
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

  // ── Time slider: filter connection edges by evidence timestamp ────────────────
  // Per-edge dated timestamps (epoch ms) from connection-log evidence. key_match
  // evidence carries no timestamp, so key-match-only edges never appear here.
  const edgeTimes = useMemo(() => {
    const map = new Map<string, number[]>()
    for (const e of graphData.edges) {
      const times: number[] = []
      for (const ev of e.evidence) {
        if (!ev.timestamp) continue
        const t = Date.parse(ev.timestamp)
        if (!Number.isNaN(t)) times.push(t)
      }
      if (times.length) map.set(`${e.src_host_id}__${e.dst_host_id}`, times)
    }
    return map
  }, [graphData.edges])

  // Draggable domain = span of all dated evidence. Null (bar hidden) when there
  // are no dated edges, or when every date is identical (min===max → nothing to
  // drag) — the feature self-disables rather than showing a dead slider.
  const timeDomain = useMemo(() => {
    let min = Infinity, max = -Infinity
    for (const times of edgeTimes.values()) {
      for (const t of times) { if (t < min) min = t; if (t > max) max = t }
    }
    return min === Infinity || min === max ? null : { min, max }
  }, [edgeTimes])

  // ~500 draggable increments across the domain, whatever its span.
  const timeStep = useMemo(
    () => (timeDomain ? Math.max(1, Math.floor((timeDomain.max - timeDomain.min) / 500)) : 1),
    [timeDomain],
  )

  // The window the rest of the UI consumes: [earlier handle, later handle].
  const timeWindow = useMemo(
    () => (timeSel ? { start: Math.min(timeSel.a, timeSel.b), end: Math.max(timeSel.a, timeSel.b) } : null),
    [timeSel],
  )

  // Edge keys the current window hides. An edge is hidden iff it has dated
  // evidence AND none of its dates fall inside the window. Two exemptions keep a
  // real pivot from ever being concealed: key-match edges (structural, not
  // time-bound) and undated edges (no basis to hide) are always shown.
  const timeHiddenKeys = useMemo(() => {
    const hidden = new Set<string>()
    if (!timeWindow) return hidden
    for (const e of graphData.edges) {
      if (e.evidence.some(ev => ev.type === 'key_match')) continue   // always shown
      const key = `${e.src_host_id}__${e.dst_host_id}`
      const times = edgeTimes.get(key)
      if (!times) continue                                           // undated → always shown
      if (!times.some(t => t >= timeWindow.start && t <= timeWindow.end)) hidden.add(key)
    }
    return hidden
  }, [graphData.edges, edgeTimes, timeWindow])

  // Nodes the time filter hides: hosts left with no visible edge once the window
  // narrows (all their connections are out-of-window). Key-match / undated edges
  // keep their endpoints visible. Empty when the window isn't narrowing anything,
  // so isolated hosts still show at rest.
  const timeHiddenNodeIds = useMemo(() => {
    const hidden = new Set<string>()
    if (timeHiddenKeys.size === 0) return hidden
    const connected = new Set<string>()
    for (const e of graphData.edges) {
      if (!timeHiddenKeys.has(`${e.src_host_id}__${e.dst_host_id}`)) {
        connected.add(e.src_host_id)
        connected.add(e.dst_host_id)
      }
    }
    for (const n of graphData.nodes) {
      if (!connected.has(n.host_id)) hidden.add(n.host_id)
    }
    return hidden
  }, [graphData.nodes, graphData.edges, timeHiddenKeys])

  // Initialize / re-clamp the handles whenever the domain changes (a host-selection
  // change or data reload can shift it). Fresh domain → full range. A selection that
  // still overlaps the new domain → clamp each handle into it. A selection now
  // entirely outside the new domain → reset to full, rather than collapsing onto a
  // domain edge (which would strand the graph near-empty after a routine change).
  useEffect(() => {
    if (!timeDomain) { setTimeSel(null); return }
    setTimeSel(prev => {
      if (!prev) return { a: timeDomain.min, b: timeDomain.max }
      const lo = Math.min(prev.a, prev.b), hi = Math.max(prev.a, prev.b)
      if (hi < timeDomain.min || lo > timeDomain.max) return { a: timeDomain.min, b: timeDomain.max }
      const clamp = (x: number) => Math.min(Math.max(x, timeDomain.min), timeDomain.max)
      return { a: clamp(prev.a), b: clamp(prev.b) }
    })
  }, [timeDomain])

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
    setPathAnchorId(null)   // a plain click abandons a pending path anchor
    pathReqSeq.current++    // and supersedes any in-flight path search
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
    setPathAnchorId(null)   // background tap clears a pending path anchor
    pathReqSeq.current++    // and supersedes any in-flight path search
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

  // Monotonic token so a slow/out-of-order findPaths response can't clobber newer
  // UI state (a later shift-click, plain click, canvas tap, or Escape supersedes it).
  const pathReqSeq = useRef(0)
  // Timer for the transient path-notice banner — tracked so overlapping notices
  // don't blank each other early, and cleared on unmount.
  const pathNoticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (pathNoticeTimer.current) clearTimeout(pathNoticeTimer.current) }, [])
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'Escape') {
        // Clear a pending path anchor and any active path highlight.
        pathReqSeq.current++   // discard any in-flight path search
        setPathAnchorId(null)
        setPathFilter(null)
        setSelectedPath(null)
        return
      }
      if (e.key !== 'Delete' && e.key !== 'Backspace') return
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
    setPathAnchorId(null)
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

  // Shift+click two hosts → highlight the BFS path between them. Reuses the
  // existing shortest-path API and the PathFinder highlight — no new endpoint.
  async function handleNodeShiftClick(node: GraphNode) {
    if (!pathAnchorId) {                          // first host → set the anchor
      setPathAnchorId(node.host_id)
      setPathNotice(null)
      return
    }
    if (pathAnchorId === node.host_id) {          // same host → cancel the anchor
      setPathAnchorId(null)
      return
    }
    const src = pathAnchorId                       // second host → resolve the path
    setPathAnchorId(null)
    const seq = ++pathReqSeq.current
    try {
      const resp = await findPaths(op.id, {
        src_host_id: src, dst_host_id: node.host_id, mode: 'shortest', waypoints: [],
      })
      if (seq !== pathReqSeq.current) return        // superseded by a newer interaction
      if (resp.paths.length > 0) handleHighlightPath(resp.paths[0])
      else showPathNotice('No path found between the two hosts')
    } catch {
      if (seq !== pathReqSeq.current) return
      showPathNotice('Path search failed')
    }
  }

  function showPathNotice(msg: string) {
    setPathNotice(msg)
    if (pathNoticeTimer.current) clearTimeout(pathNoticeTimer.current)
    pathNoticeTimer.current = setTimeout(() => {
      pathNoticeTimer.current = null
      setPathNotice(null)
    }, 2500)
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

  // A drag landing within one step of a domain edge snaps exactly to it, so the
  // earliest/latest-dated edge is always reachable despite range-input step
  // quantization (browsers snap a full-swing drag to a grid point short of the max).
  function snapTimeHandle(v: number): number {
    if (!timeDomain) return v
    if (v <= timeDomain.min + timeStep) return timeDomain.min
    if (v >= timeDomain.max - timeStep) return timeDomain.max
    return v
  }
  // Handles move independently (no cross-clamp); the window derives from min/max,
  // so a handle dragged past its sibling simply swaps roles — never a soft-lock.
  function handleTimeA(v: number) { setTimeSel(s => (s ? { ...s, a: snapTimeHandle(v) } : s)) }
  function handleTimeB(v: number) { setTimeSel(s => (s ? { ...s, b: snapTimeHandle(v) } : s)) }

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
        onMergeRequested={() => {
          const source = allHosts.find(h => h.id === selectedNode.host_id)
          if (source) setMergeState({ source })
        }}
        onMergeWithCandidate={(c: MergeCandidate) => {
          const source = allHosts.find(h => h.id === c.conflicting_host_id)
          const target = allHosts.find(h => h.id === selectedNode.host_id)
          if (source && target) setMergeState({ source, targetCandidate: target })
        }}
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
          {pathNotice && <div className={styles.pathNotice}>{pathNotice}</div>}
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
            onNodeShiftClick={handleNodeShiftClick}
            pathAnchorId={pathAnchorId}
            timeHiddenKeys={timeHiddenKeys}
            timeHiddenNodeIds={timeHiddenNodeIds}
            timeWindow={timeWindow}
            timeDomain={timeDomain}
          />
        </div>

        {timeDomain && timeSel && timeWindow && (
          <div className={styles.timeBar}>
            <span className={styles.toolbarLabel}>Time:</span>
            <span className={styles.timeValue}>{fmtInstant(timeWindow.start)}</span>
            <div className={styles.timeSlider}>
              <div className={styles.timeTrack} />
              <input
                type="range"
                data-testid="time-start"
                aria-label="Start of time window"
                min={timeDomain.min}
                max={timeDomain.max}
                step={timeStep}
                value={timeSel.a}
                onChange={e => handleTimeA(Number(e.target.value))}
              />
              <input
                type="range"
                data-testid="time-end"
                aria-label="End of time window"
                min={timeDomain.min}
                max={timeDomain.max}
                step={timeStep}
                value={timeSel.b}
                onChange={e => handleTimeB(Number(e.target.value))}
              />
            </div>
            <span className={styles.timeValue}>{fmtInstant(timeWindow.end)}</span>
            {/* Always mounted (visibility, not conditional render) so appearing/
                disappearing never resizes the track or bar height mid-drag — that
                reflow made the thumb jump and the canvas jitter at the boundary. */}
            {(() => {
              const narrowed = timeWindow.start > timeDomain.min || timeWindow.end < timeDomain.max
              return (
                <button
                  className={styles.clearFilterBtn}
                  style={{ visibility: narrowed ? 'visible' : 'hidden' }}
                  tabIndex={narrowed ? 0 : -1}
                  aria-hidden={!narrowed}
                  onClick={() => setTimeSel({ a: timeDomain.min, b: timeDomain.max })}
                >
                  Reset
                </button>
              )
            })()}
          </div>
        )}

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

      {mergeState && (
        <MergeHostDialog
          source={mergeState.source}
          targetCandidate={mergeState.targetCandidate}
          allHosts={allHosts}
          onClose={() => setMergeState(null)}
          onMerged={() => {
            // Source host is gone — drop the sidebar if it was pointing
            // at it. The WS broadcast triggers Workspace.fetchAll which
            // refreshes allHosts; loadFullGraph runs locally for snappier
            // graph redraw without waiting for the round-trip.
            if (selectedNode?.host_id === mergeState.source.id) {
              setSelectedNode(null)
            }
            setMergeState(null)
            loadFullGraph()
          }}
        />
      )}
    </div>
  )
}
