/**
 * Left sidebar — searchable host list with checkboxes for graph filtering.
 */
import { useState } from 'react'
import type { GraphNode, Host } from '../types'
import styles from './HostSelector.module.css'

interface Props {
  graphNodes: GraphNode[]
  allHosts: Host[]
  selectedIds: Set<string>
  onSelectionChange: (ids: Set<string>) => void
  onShowAll: () => void
  loading: boolean
}

export default function HostSelector({
  graphNodes,
  allHosts,
  selectedIds,
  onSelectionChange,
  onShowAll,
  loading,
}: Props) {
  const [search, setSearch] = useState('')

  // Merge graph nodes and allHosts — prefer graph node data (has counts), fall back to Host
  const items: { id: string; nickname: string; ips: string[] }[] = []
  const seen = new Set<string>()
  for (const n of graphNodes) {
    items.push({ id: n.host_id, nickname: n.nickname, ips: n.ips })
    seen.add(n.host_id)
  }
  for (const h of allHosts) {
    if (!seen.has(h.id)) {
      items.push({ id: h.id, nickname: h.nickname, ips: h.ips.map(i => i.ip_address) })
    }
  }

  const filtered = search.trim()
    ? items.filter(
        h =>
          h.nickname.toLowerCase().includes(search.toLowerCase()) ||
          h.ips.some(ip => ip.includes(search)),
      )
    : items

  function toggle(id: string) {
    const next = new Set(selectedIds)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    onSelectionChange(next)
  }

  function selectAll() {
    onSelectionChange(new Set(filtered.map(h => h.id)))
  }

  function clearAll() {
    onSelectionChange(new Set())
  }

  return (
    <div className={styles.selector}>
      <div className={styles.searchRow}>
        <input
          className={styles.search}
          placeholder="Filter hosts…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          type="text"
        />
      </div>

      <div className={styles.actions}>
        <button className={styles.actionBtn} onClick={selectAll}>All</button>
        <button className={styles.actionBtn} onClick={clearAll}>None</button>
        <button className={styles.actionBtn} onClick={onShowAll} title="Load all hosts into graph">
          Refresh
        </button>
      </div>

      {loading && <div className={styles.loading}>Loading…</div>}

      <div className={styles.list}>
        {filtered.length === 0 && !loading && (
          <p className={styles.empty}>No hosts{search ? ' matching filter' : ''}.</p>
        )}
        {filtered.map(h => (
          <label key={h.id} className={`${styles.row} ${selectedIds.has(h.id) ? '' : styles.rowUnchecked}`}>
            <input
              type="checkbox"
              checked={selectedIds.has(h.id)}
              onChange={() => toggle(h.id)}
              className={styles.checkbox}
            />
            <span className={styles.rowContent}>
              <span className={styles.nickname}>{h.nickname}</span>
              {h.ips.length > 0 && (
                <span className={styles.ip}>{h.ips[0]}{h.ips.length > 1 ? ` +${h.ips.length - 1}` : ''}</span>
              )}
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}
