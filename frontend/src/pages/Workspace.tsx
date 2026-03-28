/**
 * Workspace — main page for a selected operation.
 * Shows hosts list and exposes the AddDataModal for manual entry.
 * Phase 3 will replace the list with a cytoscape.js graph canvas.
 */
import { useState, useEffect, useCallback } from 'react'
import type { Operation, Host } from '../types'
import { listHosts } from '../api/hosts'
import AddDataModal from '../components/AddDataModal'
import styles from './Workspace.module.css'

interface Props {
  op: Operation
  onBack: () => void
}

function HostCard({ host }: { host: Host }) {
  return (
    <div className={styles.hostCard}>
      <div className={styles.hostCardHeader}>
        <span className={styles.hostNickname}>{host.nickname}</span>
        {host.ips.length > 0 && (
          <span className={styles.badge} title="IPs">
            {host.ips.length} IP{host.ips.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {host.ips.length > 0 && (
        <div className={styles.hostIPs}>
          {host.ips.map(ip => (
            <span key={ip.id} className={styles.ipChip}>
              {ip.ip_address}
              {ip.interface_name ? ` (${ip.interface_name})` : ''}
            </span>
          ))}
        </div>
      )}

      {host.comment && (
        <p className={styles.hostComment}>{host.comment}</p>
      )}
    </div>
  )
}

export default function Workspace({ op, onBack }: Props) {
  const [hosts, setHosts] = useState<Host[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchHosts = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listHosts(op.id)
      setHosts(data)
    } catch {
      setError('Failed to load hosts.')
    } finally {
      setLoading(false)
    }
  }, [op.id])

  useEffect(() => {
    fetchHosts()
  }, [fetchHosts])

  // Called by AddDataModal when new data is saved
  function handleDataAdded() {
    fetchHosts()
  }

  return (
    <div className={styles.workspace}>
      {/* Header */}
      <header className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>
          ← Operations
        </button>
        <div className={styles.opInfo}>
          <div className={styles.opNameRow}>
            <span className={styles.opName}>{op.name}</span>
            <span className={styles.opUuid}>{op.id}</span>
          </div>
          {op.description && (
            <span className={styles.opDescription}>{op.description}</span>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className={styles.main}>
        {loading && (
          <div className={styles.state}>
            <p className={styles.stateText}>Loading…</p>
          </div>
        )}

        {error && !loading && (
          <div className={styles.stateError}>
            <p>{error}</p>
            <button className={styles.retryBtn} onClick={fetchHosts}>Retry</button>
          </div>
        )}

        {!loading && !error && hosts.length === 0 && (
          <div className={styles.state}>
            <div className={styles.emptyIcon}>⬡</div>
            <p className={styles.emptyTitle}>No hosts yet</p>
            <p className={styles.emptyHint}>
              Click <strong>+</strong> to add a host, user, credential, or connection manually.
            </p>
          </div>
        )}

        {!loading && !error && hosts.length > 0 && (
          <div className={styles.content}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Hosts</h2>
              <span className={styles.sectionCount}>{hosts.length}</span>
            </div>
            <div className={styles.hostGrid}>
              {hosts.map(h => (
                <HostCard key={h.id} host={h} />
              ))}
            </div>
            <p className={styles.graphHint}>
              Graph visualization will be added in Phase 3.
            </p>
          </div>
        )}
      </main>

      {/* FAB + modal */}
      <AddDataModal opId={op.id} hosts={hosts} onDataAdded={handleDataAdded} />
    </div>
  )
}
