/**
 * Right sidebar — shows per-hop evidence breakdown for a selected pivot path.
 * Includes Copy JSON / Copy Markdown export.
 */
import { useState } from 'react'
import type { EvidenceItem, GraphEdge, GraphNode, PathResult, PivotableUser } from '../types'
import { EVIDENCE_LABELS } from '../utils/evidenceLabels'
import { classifyPath, type PathType } from './PathFinder'
import styles from './PathDetailPanel.module.css'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  indicator: 'Indicator',
}

const PATH_TYPE_LABELS: Record<PathType, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  theoretical: 'Theoretical',
}

interface Props {
  path: PathResult
  nodes: GraphNode[]
  onClose: () => void
}

function getNickname(hostId: string, nodes: GraphNode[]): string {
  return nodes.find(n => n.host_id === hostId)?.nickname ?? hostId.slice(0, 8)
}

function buildJsonExport(path: PathResult, nodes: GraphNode[], type: PathType): string {
  return JSON.stringify({
    path: path.host_ids.map(id => getNickname(id, nodes)),
    type,
    hops: path.edges.map(e => ({
      src: getNickname(e.src_host_id, nodes),
      dst: getNickname(e.dst_host_id, nodes),
      confidence: e.confidence,
      evidence: e.evidence,
      pivotable_users: e.pivotable_users,
    })),
  }, null, 2)
}

function buildMarkdownExport(path: PathResult, nodes: GraphNode[], type: PathType): string {
  const nicknames = path.host_ids.map(id => getNickname(id, nodes))
  const pathStr = nicknames.join(' → ')
  const lines: string[] = [
    `## Pivot Path: ${pathStr}`,
    `**Type:** ${PATH_TYPE_LABELS[type]}  **Hops:** ${path.edges.length}`,
    '',
  ]
  path.edges.forEach((edge, i) => {
    const src = getNickname(edge.src_host_id, nodes)
    const dst = getNickname(edge.dst_host_id, nodes)
    lines.push(`### Hop ${i + 1}: ${src} → ${dst} (${edge.confidence})`)
    for (const ev of edge.evidence) {
      lines.push(`- **${EVIDENCE_LABELS[ev.type] ?? ev.type}**: ${ev.detail}`)
    }
    if (edge.pivotable_users.length > 0) {
      const users = edge.pivotable_users
        .map(u => `${u.src_user} → ${u.dst_user} (${u.method})`)
        .join(', ')
      lines.push(`- **Pivot users:** ${users}`)
    }
    lines.push('')
  })
  return lines.join('\n')
}

export default function PathDetailPanel({ path, nodes, onClose }: Props) {
  const [copyState, setCopyState] = useState<'json' | 'md' | null>(null)
  const type = classifyPath(path)
  const nicknames = path.host_ids.map(id => getNickname(id, nodes))

  async function handleCopy(format: 'json' | 'md') {
    const text = format === 'json'
      ? buildJsonExport(path, nodes, type)
      : buildMarkdownExport(path, nodes, type)
    await navigator.clipboard.writeText(text)
    setCopyState(format)
    setTimeout(() => setCopyState(null), 1500)
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <span className={styles.title}>Path Detail</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className={styles.route}>
          {nicknames.map((name, i) => (
            <span key={i} className={styles.routePart}>
              <span className={styles.routeHost}>{name}</span>
              {i < nicknames.length - 1 && <span className={styles.routeArrow}>→</span>}
            </span>
          ))}
        </div>
        <div className={styles.pathMeta}>
          <span className={`${styles.typeBadge} ${styles[`type_${type}`]}`}>
            {PATH_TYPE_LABELS[type]}
          </span>
          <span className={styles.hopCount}>
            {path.edges.length} hop{path.edges.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div className={styles.body}>
        {path.edges.map((edge, i) => (
          <HopCard key={i} hopNumber={i + 1} edge={edge} nodes={nodes} />
        ))}
      </div>

      <div className={styles.exportRow}>
        <button className={styles.exportBtn} onClick={() => handleCopy('md')}>
          {copyState === 'md' ? 'Copied!' : 'Copy Markdown'}
        </button>
        <button className={styles.exportBtn} onClick={() => handleCopy('json')}>
          {copyState === 'json' ? 'Copied!' : 'Copy JSON'}
        </button>
      </div>
    </div>
  )
}

function HopCard({ hopNumber, edge, nodes }: { hopNumber: number; edge: GraphEdge; nodes: GraphNode[] }) {
  const src = getNickname(edge.src_host_id, nodes)
  const dst = getNickname(edge.dst_host_id, nodes)
  const confidenceClass = `conf_${edge.confidence}` as keyof typeof styles

  return (
    <div className={styles.hopCard}>
      <div className={styles.hopHeader}>
        <span className={styles.hopLabel}>Hop {hopNumber}</span>
        <span className={styles.hopRoute}>
          <span className={styles.hopHost}>{src}</span>
          <span className={styles.hopArrow}>→</span>
          <span className={styles.hopHost}>{dst}</span>
        </span>
        <span className={`${styles.confBadge} ${styles[confidenceClass]}`}>
          {CONFIDENCE_LABEL[edge.confidence]}
        </span>
      </div>

      <div className={styles.hopBody}>
        {edge.evidence.map((ev, i) => (
          <EvidenceRow key={i} ev={ev} />
        ))}

        {edge.pivotable_users.length > 0 && (
          <div className={styles.pivotSection}>
            <div className={styles.sectionLabel}>Pivot users</div>
            {edge.pivotable_users.map((p, i) => (
              <PivotRow key={i} user={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EvidenceRow({ ev }: { ev: EvidenceItem }) {
  const confidenceClass = `conf_${ev.confidence}` as keyof typeof styles

  return (
    <div className={styles.evidenceRow}>
      <div className={styles.evidenceHeader}>
        <span className={styles.evidenceType}>{EVIDENCE_LABELS[ev.type] ?? ev.type}</span>
        <span className={`${styles.confBadge} ${styles[confidenceClass]}`}>
          {CONFIDENCE_LABEL[ev.confidence]}
        </span>
      </div>
      <p className={styles.evidenceDetail}>{ev.detail}</p>
      {(ev.src_user || ev.dst_user) && (
        <div className={styles.evidenceMeta}>
          {ev.src_user && <span className={styles.metaItem}>src: <code>{ev.src_user}</code></span>}
          {ev.dst_user && <span className={styles.metaItem}>dst: <code>{ev.dst_user}</code></span>}
          {ev.auth_method && <span className={styles.metaItem}>auth: <code>{ev.auth_method}</code></span>}
        </div>
      )}
      {ev.source_file && (
        <div className={styles.evidenceMeta}>
          <span className={styles.metaItem}>file: <code>{ev.source_file}</code></span>
          {ev.timestamp && <span className={styles.metaItem}>{new Date(ev.timestamp).toLocaleString()}</span>}
        </div>
      )}
      {(ev.credential_name || ev.credential_fingerprint) && (
        <div className={styles.evidenceMeta}>
          {ev.credential_name && (
            <span className={styles.metaItem}>cred: <code>{ev.credential_name}</code></span>
          )}
          {ev.credential_fingerprint && (
            <span className={styles.metaItem}>
              fp: <code title={ev.credential_fingerprint}>{ev.credential_fingerprint.slice(0, 24)}&hellip;</code>
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function PivotRow({ user }: { user: PivotableUser }) {
  return (
    <div className={styles.pivotRow}>
      <code className={styles.pivotUser}>{user.src_user}</code>
      <span className={styles.pivotArrow}>→</span>
      <code className={styles.pivotUser}>{user.dst_user}</code>
      <span className={styles.pivotMethod}>{user.method}</span>
    </div>
  )
}
