/**
 * Right sidebar — shows evidence list for a selected graph edge.
 */
import type { EvidenceItem, GraphEdge, GraphNode, PivotableUser } from '../types'
import styles from './EdgeDetailPanel.module.css'

const EVIDENCE_LABELS: Record<string, string> = {
  key_match: 'Key Match',
  connection_log: 'Connection Log',
  bash_history: 'Bash History',
  known_hosts: 'Known Hosts',
}

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  indicator: 'Indicator',
}

interface Props {
  edge: GraphEdge
  nodes: GraphNode[]
  onClose: () => void
}

export default function EdgeDetailPanel({ edge, nodes, onClose }: Props) {
  const srcNickname = nodes.find(n => n.host_id === edge.src_host_id)?.nickname ?? edge.src_host_id
  const dstNickname = nodes.find(n => n.host_id === edge.dst_host_id)?.nickname ?? edge.dst_host_id
  const confidenceClass = `conf_${edge.confidence}` as keyof typeof styles

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <span className={styles.title}>Edge Evidence</span>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className={styles.route}>
          <span className={styles.routeHost}>{srcNickname}</span>
          <span className={styles.routeArrow}>→</span>
          <span className={styles.routeHost}>{dstNickname}</span>
          <span className={`${styles.confBadge} ${styles[confidenceClass]}`}>
            {CONFIDENCE_LABEL[edge.confidence]}
          </span>
        </div>
      </div>

      <div className={styles.body}>
        <div className={styles.sectionLabel}>
          {edge.evidence.length} evidence item{edge.evidence.length !== 1 ? 's' : ''}
        </div>

        {edge.evidence.map((ev, i) => (
          <EvidenceRow key={i} ev={ev} />
        ))}

        {edge.pivotable_users.length > 0 && (
          <div className={styles.pivotSection}>
            <div className={styles.sectionLabel}>Pivot paths</div>
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
