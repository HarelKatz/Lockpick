/**
 * Right sidebar — shows detail for a selected graph node.
 */
import type { GraphEdge, GraphNode } from '../types'
import styles from './HostDetailSidebar.module.css'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  indicator: 'Indicator',
}

interface Props {
  node: GraphNode
  edges: GraphEdge[]
  onClose: () => void
  onHostUpdated?: () => void
}

export default function HostDetailSidebar({ node, edges, onClose }: Props) {
  const outgoing = edges.filter(e => e.src_host_id === node.host_id)
  const incoming = edges.filter(e => e.dst_host_id === node.host_id)

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.title}>{node.nickname}</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
      </div>

      <div className={styles.body}>
        {node.ips.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>IPs</div>
            <div className={styles.chips}>
              {node.ips.map(ip => (
                <span key={ip} className={styles.chip}>{ip}</span>
              ))}
            </div>
          </div>
        )}

        <div className={styles.section}>
          <div className={styles.stats}>
            <span className={styles.statItem}>
              <span className={styles.statValue}>{node.user_count}</span>
              <span className={styles.statLabel}>users</span>
            </span>
            <span className={styles.statItem}>
              <span className={styles.statValue}>{node.credential_count}</span>
              <span className={styles.statLabel}>credentials</span>
            </span>
          </div>
        </div>

        {outgoing.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Outgoing ({outgoing.length})</div>
            {outgoing.map(e => (
              <EdgeSummary key={`${e.src_host_id}__${e.dst_host_id}`} edge={e} perspective="dst" />
            ))}
          </div>
        )}

        {incoming.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Incoming ({incoming.length})</div>
            {incoming.map(e => (
              <EdgeSummary key={`${e.src_host_id}__${e.dst_host_id}`} edge={e} perspective="src" />
            ))}
          </div>
        )}

        {outgoing.length === 0 && incoming.length === 0 && (
          <p className={styles.empty}>No connections found.</p>
        )}
      </div>
    </div>
  )
}

function EdgeSummary({ edge, perspective }: { edge: GraphEdge; perspective: 'src' | 'dst' }) {
  const otherId = perspective === 'dst' ? edge.dst_host_id : edge.src_host_id
  const confidenceClass = `conf_${edge.confidence}` as keyof typeof styles

  return (
    <div className={styles.edgeSummary}>
      <span className={`${styles.confBadge} ${styles[confidenceClass]}`}>
        {CONFIDENCE_LABEL[edge.confidence]}
      </span>
      <span className={styles.edgeTarget}>{otherId.slice(0, 8)}…</span>
      <span className={styles.edgeCount}>{edge.evidence.length} evidence</span>
    </div>
  )
}
