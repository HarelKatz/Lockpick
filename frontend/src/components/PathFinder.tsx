/**
 * PathFinder — panel for finding pivot paths between two hosts.
 * Renders below the graph canvas.
 */
import { useState } from 'react'
import type {
  PathFinderResponse,
  PathResult,
  WaypointConstraint,
  WaypointPosition,
} from '../types'
import { findPaths } from '../api/graph'
import styles from './PathFinder.module.css'

interface Props {
  nodes: { id: string; nickname: string }[]
  opId: string
  onHighlightPath: (path: PathResult | null) => void
}

export type PathType = 'confirmed' | 'observed' | 'theoretical'

const POSITION_LABELS: Record<WaypointPosition, string> = {
  anywhere: 'anywhere in path',
  after: 'immediately after',
  before: 'immediately before',
}

const PATH_TYPE_LABELS: Record<PathType, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  theoretical: 'Theoretical',
}

export function classifyPath(path: PathResult): PathType {
  if (path.edges.length === 0) return 'theoretical'
  const rank: Record<string, number> = { confirmed: 2, observed: 1, indicator: 0 }
  const min = path.edges.reduce((worst, e) => {
    return rank[e.confidence] < rank[worst] ? e.confidence : worst
  }, path.edges[0].confidence)
  if (min === 'confirmed') return 'confirmed'
  if (min === 'observed') return 'observed'
  return 'theoretical'
}

export default function PathFinder({ nodes, opId, onHighlightPath }: Props) {
  const [open, setOpen] = useState(false)
  const [src, setSrc] = useState('')
  const [dst, setDst] = useState('')
  const [mode, setMode] = useState<'shortest' | 'all'>('shortest')
  const [waypoints, setWaypoints] = useState<WaypointConstraint[]>([])
  const [result, setResult] = useState<PathFinderResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activePathIdx, setActivePathIdx] = useState<number | null>(null)
  const [filterConfirmed, setFilterConfirmed] = useState(true)
  const [filterObserved, setFilterObserved] = useState(true)
  const [filterTheoretical, setFilterTheoretical] = useState(true)

  function addWaypoint() {
    setWaypoints(prev => [...prev, { host_id: '', position: 'anywhere', relative_to: null }])
  }

  function removeWaypoint(i: number) {
    setWaypoints(prev => prev.filter((_, idx) => idx !== i))
  }

  function updateWaypoint(i: number, patch: Partial<WaypointConstraint>) {
    setWaypoints(prev => prev.map((wp, idx) => idx === i ? { ...wp, ...patch } : wp))
  }

  async function handleFind() {
    if (!src || !dst) return
    setLoading(true)
    setError(null)
    setResult(null)
    setActivePathIdx(null)
    onHighlightPath(null)
    try {
      const resp = await findPaths(opId, {
        src_host_id: src,
        dst_host_id: dst,
        mode,
        waypoints: waypoints.filter(wp => wp.host_id),
      })
      setResult(resp)
    } catch {
      setError('Path search failed.')
    } finally {
      setLoading(false)
    }
  }

  function handleSelectPath(originalIdx: number, path: PathResult) {
    if (activePathIdx === originalIdx) {
      setActivePathIdx(null)
      onHighlightPath(null)
    } else {
      setActivePathIdx(originalIdx)
      onHighlightPath(path)
    }
  }

  function handleClose() {
    setOpen(false)
    setResult(null)
    setActivePathIdx(null)
    onHighlightPath(null)
  }

  function getNickname(hostId: string) {
    return nodes.find(n => n.id === hostId)?.nickname ?? hostId.slice(0, 8)
  }

  const filteredPaths = result?.paths
    .map((path, i) => ({ path, originalIdx: i, type: classifyPath(path) }))
    .filter(({ type }) => {
      if (type === 'confirmed') return filterConfirmed
      if (type === 'observed') return filterObserved
      return filterTheoretical
    }) ?? []

  if (!open) {
    return (
      <div className={styles.collapsed}>
        <button className={styles.openBtn} onClick={() => setOpen(true)}>
          Find pivot path
        </button>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>Pivot Path Finder</span>
        <button className={styles.closeBtn} onClick={handleClose} aria-label="Close">✕</button>
      </div>

      {/* Source / destination row */}
      <div className={styles.row}>
        <label className={styles.fieldLabel}>From</label>
        <select className={styles.select} value={src} onChange={e => setSrc(e.target.value)}>
          <option value="">Select source…</option>
          {nodes.map(n => (
            <option key={n.id} value={n.id}>{n.nickname}</option>
          ))}
        </select>
        <label className={styles.fieldLabel}>To</label>
        <select className={styles.select} value={dst} onChange={e => setDst(e.target.value)}>
          <option value="">Select destination…</option>
          {nodes.map(n => (
            <option key={n.id} value={n.id}>{n.nickname}</option>
          ))}
        </select>
      </div>

      {/* Mode toggle */}
      <div className={styles.row}>
        <label className={styles.fieldLabel}>Mode</label>
        <div className={styles.modeGroup}>
          <button
            className={`${styles.modeBtn} ${mode === 'shortest' ? styles.modeBtnActive : ''}`}
            onClick={() => setMode('shortest')}
          >
            Shortest
          </button>
          <button
            className={`${styles.modeBtn} ${mode === 'all' ? styles.modeBtnActive : ''}`}
            onClick={() => setMode('all')}
          >
            All paths
          </button>
        </div>
      </div>

      {/* Waypoints */}
      {waypoints.map((wp, i) => (
        <div key={i} className={styles.waypointRow}>
          <select
            className={styles.select}
            value={wp.host_id}
            onChange={e => updateWaypoint(i, { host_id: e.target.value })}
          >
            <option value="">Select host…</option>
            {nodes.map(n => (
              <option key={n.id} value={n.id}>{n.nickname}</option>
            ))}
          </select>
          <select
            className={styles.selectSm}
            value={wp.position}
            onChange={e => updateWaypoint(i, {
              position: e.target.value as WaypointPosition,
              relative_to: null,
            })}
          >
            {(Object.keys(POSITION_LABELS) as WaypointPosition[]).map(p => (
              <option key={p} value={p}>{POSITION_LABELS[p]}</option>
            ))}
          </select>
          {wp.position !== 'anywhere' && (
            <select
              className={styles.selectSm}
              value={wp.relative_to ?? ''}
              onChange={e => updateWaypoint(i, { relative_to: e.target.value || null })}
            >
              <option value="">src/dst</option>
              {nodes.filter(n => n.id !== wp.host_id).map(n => (
                <option key={n.id} value={n.id}>{n.nickname}</option>
              ))}
            </select>
          )}
          <button className={styles.removeBtn} onClick={() => removeWaypoint(i)} aria-label="Remove waypoint">✕</button>
        </div>
      ))}

      <button className={styles.addWaypointBtn} onClick={addWaypoint}>
        + Add waypoint
      </button>

      <button
        className={styles.findBtn}
        onClick={handleFind}
        disabled={!src || !dst || loading}
      >
        {loading ? 'Searching…' : 'Find paths'}
      </button>

      {error && <p className={styles.error}>{error}</p>}

      {result && (
        <div className={styles.results}>
          {/* Confidence filter */}
          <div className={styles.filterRow}>
            <span className={styles.filterLabel}>Show:</span>
            {(['confirmed', 'observed', 'theoretical'] as PathType[]).map(type => (
              <label key={type} className={styles.filterCheck}>
                <input
                  type="checkbox"
                  checked={type === 'confirmed' ? filterConfirmed : type === 'observed' ? filterObserved : filterTheoretical}
                  onChange={e => {
                    if (type === 'confirmed') setFilterConfirmed(e.target.checked)
                    else if (type === 'observed') setFilterObserved(e.target.checked)
                    else setFilterTheoretical(e.target.checked)
                  }}
                />
                <span className={`${styles.typeBadge} ${styles[`type_${type}`]}`}>
                  {PATH_TYPE_LABELS[type]}
                </span>
              </label>
            ))}
          </div>

          {filteredPaths.length === 0 && (
            <p className={styles.noResults}>
              {result.paths.length === 0 ? 'No paths found.' : 'No paths match the selected filters.'}
            </p>
          )}

          <div className={styles.pathList}>
            {filteredPaths.map(({ path, originalIdx, type }) => (
              <div
                key={originalIdx}
                className={`${styles.pathRow} ${activePathIdx === originalIdx ? styles.pathRowActive : ''}`}
                onClick={() => handleSelectPath(originalIdx, path)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && handleSelectPath(originalIdx, path)}
              >
                <div className={styles.pathHops}>
                  {path.host_ids.map(id => getNickname(id)).join(' → ')}
                </div>
                <div className={styles.pathMeta}>
                  {path.host_ids.length - 1} hop{path.host_ids.length !== 2 ? 's' : ''}
                  <span className={`${styles.typeBadge} ${styles[`type_${type}`]}`}>
                    {PATH_TYPE_LABELS[type]}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {result.truncated && (
            <p className={styles.truncationWarning}>Results capped at 30 paths.</p>
          )}
        </div>
      )}
    </div>
  )
}
