/**
 * Workspace — main page for a selected operation.
 * Shows hosts, credentials, and connections with edit/delete controls.
 */
import { useState, useEffect, useCallback } from 'react'
import type {
  Operation, Host, Credential, CredentialLink, ConnectionRecord,
} from '../types'
import { listHosts, deleteHost } from '../api/hosts'
import { listCredentials, deleteCredential, listCredentialLinks, deleteCredentialLink } from '../api/credentials'
import { listConnections, deleteConnection } from '../api/connections'
import AddDataModal from '../components/AddDataModal'
import EditModal from '../components/EditModal'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import EditHostForm from '../components/EditHostForm'
import EditCredentialForm from '../components/EditCredentialForm'
import EditCredentialLinkForm from '../components/EditCredentialLinkForm'
import EditConnectionForm from '../components/EditConnectionForm'
import styles from './Workspace.module.css'

interface Props {
  op: Operation
  onBack: () => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

const CRED_TYPE_LABELS: Record<Credential['cred_type'], string> = {
  private_key: 'Private Key',
  public_key: 'Public Key',
  password: 'Password',
}

const CONN_TYPE_LABELS: Record<ConnectionRecord['connection_type'], string> = {
  ssh: 'SSH', scp: 'SCP', rsync: 'rsync',
  sftp: 'SFTP', ssh_copy_id: 'ssh-copy-id', unknown: '?',
}

// ─── Host card ────────────────────────────────────────────────────────────────

interface HostCardProps {
  host: Host
  onEdit: (h: Host) => void
  onDelete: (h: Host) => void
}

function HostCard({ host, onEdit, onDelete }: HostCardProps) {
  return (
    <div className={styles.hostCard}>
      <div className={styles.hostCardHeader}>
        <span className={styles.hostNickname}>{host.nickname}</span>
        <div className={styles.hostCardActions}>
          {host.ips.length > 0 && (
            <span className={styles.badge}>
              {host.ips.length} IP{host.ips.length !== 1 ? 's' : ''}
            </span>
          )}
          <button
            className={styles.iconBtn}
            onClick={() => onEdit(host)}
            title="Edit host"
            aria-label="Edit host"
          >
            ✎
          </button>
          <button
            className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
            onClick={() => onDelete(host)}
            title="Delete host"
            aria-label="Delete host"
          >
            ✕
          </button>
        </div>
      </div>

      {host.ips.length > 0 && (
        <div className={styles.hostIPs}>
          {host.ips.map(ip => (
            <span key={ip.id} className={styles.ipChip}>{ip.ip_address}</span>
          ))}
        </div>
      )}

      {host.comment && (
        <p className={styles.hostComment}>{host.comment}</p>
      )}
    </div>
  )
}

// ─── Credential row ───────────────────────────────────────────────────────────

interface CredentialRowProps {
  cred: Credential
  links: CredentialLink[]
  hosts: Host[]
  onEdit: (c: Credential) => void
  onDelete: (c: Credential) => void
  onEditLink: (l: CredentialLink) => void
  onDeleteLink: (l: CredentialLink) => void
}

function CredentialRow({ cred, links, hosts, onEdit, onDelete, onEditLink, onDeleteLink }: CredentialRowProps) {
  return (
    <div className={styles.credRow}>
      <div className={styles.credHeader}>
        <span className={`${styles.typeBadge} ${styles[`type_${cred.cred_type}`]}`}>
          {CRED_TYPE_LABELS[cred.cred_type]}
        </span>
        <span className={styles.credValue}>{truncate(cred.value, 60)}</span>
        {cred.fingerprint && (
          <span className={styles.fingerprintChip} title={cred.fingerprint}>
            {cred.fingerprint.slice(0, 22)}…
          </span>
        )}
        {cred.comment && (
          <span className={styles.credComment}>{cred.comment}</span>
        )}
        <div className={styles.rowActions}>
          <button className={styles.iconBtn} onClick={() => onEdit(cred)} title="Edit credential" aria-label="Edit credential">✎</button>
          <button className={`${styles.iconBtn} ${styles.iconBtnDanger}`} onClick={() => onDelete(cred)} title="Delete credential" aria-label="Delete credential">✕</button>
        </div>
      </div>

      {links.length > 0 && (
        <div className={styles.linkList}>
          {links.map(link => {
            const host = hosts.find(h => h.id === link.host_id)
            return (
              <div key={link.id} className={styles.linkRow}>
                <span className={styles.linkRelBadge}>{link.relationship_type.replace(/_/g, ' ')}</span>
                <span className={styles.linkHost}>{host?.nickname ?? link.host_id}</span>
                {link.username && <span className={styles.linkUser}>@{link.username}</span>}
                <div className={styles.rowActions}>
                  <button className={styles.iconBtnSm} onClick={() => onEditLink(link)} title="Edit link" aria-label="Edit link">✎</button>
                  <button className={`${styles.iconBtnSm} ${styles.iconBtnDanger}`} onClick={() => onDeleteLink(link)} title="Remove link" aria-label="Remove link">✕</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── Connection row ───────────────────────────────────────────────────────────

interface ConnectionRowProps {
  conn: ConnectionRecord
  hosts: Host[]
  onEdit: (c: ConnectionRecord) => void
  onDelete: (c: ConnectionRecord) => void
}

function ConnectionRow({ conn, hosts, onEdit, onDelete }: ConnectionRowProps) {
  const srcHost = hosts.find(h => h.id === conn.src_host_id)
  const dstHost = hosts.find(h => h.id === conn.dst_host_id)

  return (
    <div className={styles.connRow}>
      <div className={styles.connEndpoint}>
        {srcHost && <span className={styles.connHostName}>{srcHost.nickname}</span>}
        <span className={styles.connIp}>{conn.src_ip}</span>
        {conn.src_user && <span className={styles.connUser}>{conn.src_user}</span>}
      </div>
      <span className={styles.connArrow}>→</span>
      <div className={styles.connEndpoint}>
        {dstHost && <span className={styles.connHostName}>{dstHost.nickname}</span>}
        <span className={styles.connIp}>{conn.dst_ip}</span>
        {conn.dst_user && <span className={styles.connUser}>{conn.dst_user}</span>}
      </div>
      <span className={`${styles.typeBadge} ${styles.type_ssh}`}>{CONN_TYPE_LABELS[conn.connection_type]}</span>
      {conn.timestamp && (
        <span className={styles.connTimestamp}>{formatTimestamp(conn.timestamp)}</span>
      )}
      <div className={styles.rowActions}>
        <button className={styles.iconBtn} onClick={() => onEdit(conn)} title="Edit connection" aria-label="Edit connection">✎</button>
        <button className={`${styles.iconBtn} ${styles.iconBtnDanger}`} onClick={() => onDelete(conn)} title="Delete connection" aria-label="Delete connection">✕</button>
      </div>
    </div>
  )
}

// ─── Workspace ────────────────────────────────────────────────────────────────

export default function Workspace({ op, onBack }: Props) {
  const [hosts, setHosts] = useState<Host[]>([])
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [links, setLinks] = useState<CredentialLink[]>([])
  const [connections, setConnections] = useState<ConnectionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Edit state
  const [editHost, setEditHost] = useState<Host | null>(null)
  const [editCred, setEditCred] = useState<Credential | null>(null)
  const [editLink, setEditLink] = useState<CredentialLink | null>(null)
  const [editConn, setEditConn] = useState<ConnectionRecord | null>(null)

  // Delete confirm state
  const [deleteHostTarget, setDeleteHostTarget] = useState<Host | null>(null)
  const [deleteCredTarget, setDeleteCredTarget] = useState<Credential | null>(null)
  const [deleteLinkTarget, setDeleteLinkTarget] = useState<CredentialLink | null>(null)
  const [deleteConnTarget, setDeleteConnTarget] = useState<ConnectionRecord | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [hostsData, credsData, linksData, connsData] = await Promise.all([
        listHosts(op.id),
        listCredentials(op.id),
        listCredentialLinks(op.id),
        listConnections(op.id),
      ])
      setHosts(hostsData)
      setCredentials(credsData)
      setLinks(linksData)
      setConnections(connsData)
    } catch {
      setError('Failed to load data.')
    } finally {
      setLoading(false)
    }
  }, [op.id])

  useEffect(() => { fetchAll() }, [fetchAll])

  // ─── Delete handlers ─────────────────────────────────────────────────────

  async function confirmDeleteHost() {
    if (!deleteHostTarget) return
    setDeleteLoading(true)
    try {
      await deleteHost(deleteHostTarget.id)
      setHosts(prev => prev.filter(h => h.id !== deleteHostTarget.id))
      setDeleteHostTarget(null)
    } catch {
      /* ignore — leave modal open so user can retry */
    } finally {
      setDeleteLoading(false)
    }
  }

  async function confirmDeleteCred() {
    if (!deleteCredTarget) return
    setDeleteLoading(true)
    try {
      await deleteCredential(deleteCredTarget.id)
      setCredentials(prev => prev.filter(c => c.id !== deleteCredTarget.id))
      setLinks(prev => prev.filter(l => l.credential_id !== deleteCredTarget.id))
      setDeleteCredTarget(null)
    } catch {
      /* ignore */
    } finally {
      setDeleteLoading(false)
    }
  }

  async function confirmDeleteLink() {
    if (!deleteLinkTarget) return
    setDeleteLoading(true)
    try {
      await deleteCredentialLink(deleteLinkTarget.id)
      setLinks(prev => prev.filter(l => l.id !== deleteLinkTarget.id))
      setDeleteLinkTarget(null)
    } catch {
      /* ignore */
    } finally {
      setDeleteLoading(false)
    }
  }

  async function confirmDeleteConn() {
    if (!deleteConnTarget) return
    setDeleteLoading(true)
    try {
      await deleteConnection(deleteConnTarget.id)
      setConnections(prev => prev.filter(c => c.id !== deleteConnTarget.id))
      setDeleteConnTarget(null)
    } catch {
      /* ignore */
    } finally {
      setDeleteLoading(false)
    }
  }

  const hasData = hosts.length > 0 || credentials.length > 0 || connections.length > 0

  return (
    <div className={styles.workspace}>
      {/* Header */}
      <header className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>← Operations</button>
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
            <button className={styles.retryBtn} onClick={fetchAll}>Retry</button>
          </div>
        )}

        {!loading && !error && !hasData && (
          <div className={styles.state}>
            <div className={styles.emptyIcon}>⬡</div>
            <p className={styles.emptyTitle}>No hosts yet</p>
            <p className={styles.emptyHint}>
              Click <strong>+</strong> to add a host, credential, or connection manually.
            </p>
          </div>
        )}

        {!loading && !error && hasData && (
          <div className={styles.content}>
            {/* Hosts */}
            {hosts.length > 0 && (
              <section>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Hosts</h2>
                  <span className={styles.sectionCount}>{hosts.length}</span>
                </div>
                <div className={styles.hostGrid}>
                  {hosts.map(h => (
                    <HostCard
                      key={h.id}
                      host={h}
                      onEdit={setEditHost}
                      onDelete={setDeleteHostTarget}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Credentials */}
            {credentials.length > 0 && (
              <section>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Credentials</h2>
                  <span className={styles.sectionCount}>{credentials.length}</span>
                </div>
                <div className={styles.listPanel}>
                  {credentials.map(cred => (
                    <CredentialRow
                      key={cred.id}
                      cred={cred}
                      links={links.filter(l => l.credential_id === cred.id)}
                      hosts={hosts}
                      onEdit={setEditCred}
                      onDelete={setDeleteCredTarget}
                      onEditLink={setEditLink}
                      onDeleteLink={setDeleteLinkTarget}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Connections */}
            {connections.length > 0 && (
              <section>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Connections</h2>
                  <span className={styles.sectionCount}>{connections.length}</span>
                </div>
                <div className={styles.listPanel}>
                  {connections.map(conn => (
                    <ConnectionRow
                      key={conn.id}
                      conn={conn}
                      hosts={hosts}
                      onEdit={setEditConn}
                      onDelete={setDeleteConnTarget}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>

      {/* FAB + add modal */}
      <AddDataModal opId={op.id} hosts={hosts} onDataAdded={fetchAll} />

      {/* ─── Edit modals ─── */}
      {editHost && (
        <EditModal title={`Edit Host — ${editHost.nickname}`} onClose={() => setEditHost(null)}>
          <EditHostForm
            host={editHost}
            onSaved={updated => {
              setHosts(prev => prev.map(h => h.id === updated.id ? updated : h))
              setEditHost(null)
            }}
            onClose={() => setEditHost(null)}
          />
        </EditModal>
      )}

      {editCred && (
        <EditModal title="Edit Credential" onClose={() => setEditCred(null)}>
          <EditCredentialForm
            credential={editCred}
            onSaved={updated => {
              setCredentials(prev => prev.map(c => c.id === updated.id ? updated : c))
              setEditCred(null)
            }}
            onClose={() => setEditCred(null)}
          />
        </EditModal>
      )}

      {editLink && (
        <EditModal title="Edit Credential Link" onClose={() => setEditLink(null)}>
          <EditCredentialLinkForm
            link={editLink}
            credential={credentials.find(c => c.id === editLink.credential_id)!}
            host={hosts.find(h => h.id === editLink.host_id)}
            onSaved={updated => {
              setLinks(prev => prev.map(l => l.id === updated.id ? updated : l))
              setEditLink(null)
            }}
            onClose={() => setEditLink(null)}
          />
        </EditModal>
      )}

      {editConn && (
        <EditModal title="Edit Connection" onClose={() => setEditConn(null)}>
          <EditConnectionForm
            connection={editConn}
            hosts={hosts}
            onSaved={updated => {
              setConnections(prev => prev.map(c => c.id === updated.id ? updated : c))
              setEditConn(null)
            }}
            onClose={() => setEditConn(null)}
          />
        </EditModal>
      )}

      {/* ─── Delete confirm modals ─── */}
      {deleteHostTarget && (
        <ConfirmDeleteModal
          title="Delete Host"
          message={`Delete "${deleteHostTarget.nickname}"? This will also remove its IPs and all credential links. This cannot be undone.`}
          onConfirm={confirmDeleteHost}
          onClose={() => setDeleteHostTarget(null)}
          loading={deleteLoading}
        />
      )}

      {deleteCredTarget && (
        <ConfirmDeleteModal
          title="Delete Credential"
          message="Delete this credential and all its host links? This cannot be undone."
          onConfirm={confirmDeleteCred}
          onClose={() => setDeleteCredTarget(null)}
          loading={deleteLoading}
        />
      )}

      {deleteLinkTarget && (
        <ConfirmDeleteModal
          title="Remove Credential Link"
          message="Remove this credential link? The credential itself will not be deleted."
          onConfirm={confirmDeleteLink}
          onClose={() => setDeleteLinkTarget(null)}
          loading={deleteLoading}
        />
      )}

      {deleteConnTarget && (
        <ConfirmDeleteModal
          title="Delete Connection"
          message="Delete this connection record? This cannot be undone."
          onConfirm={confirmDeleteConn}
          onClose={() => setDeleteConnTarget(null)}
          loading={deleteLoading}
        />
      )}
    </div>
  )
}
