/**
 * Workspace — main page for a selected operation.
 * Shows hosts, credentials, and connections with edit/delete controls,
 * plus an interactive graph visualization tab.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import type {
  Operation, Host, Credential, CredentialLink, ConnectionRecord, UploadFile, ActivityLog,
  SearchResult,
} from '../types'
import { useOpWebSocket } from '../hooks/useOpWebSocket'
import WsStatusIndicator from '../components/WsStatusIndicator'
import { listHosts, deleteHost } from '../api/hosts'
import { listCredentials, deleteCredential, listCredentialLinks, deleteCredentialLink } from '../api/credentials'
import { listConnections, deleteConnection } from '../api/connections'
import { listUploads, uploadFileUrl } from '../api/upload'
import { getOpStats } from '../api/stats'
import { getActivityLog } from '../api/activity'
import { exportOp } from '../api/export_import'
import { ApiError } from '../api/client'
import NotificationBanner from '../components/NotificationBanner'
import SearchModal from '../components/SearchModal'
import AddDataModal from '../components/AddDataModal'
import EditModal from '../components/EditModal'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import EditHostForm from '../components/EditHostForm'
import EditCredentialForm from '../components/EditCredentialForm'
import EditCredentialLinkForm from '../components/EditCredentialLinkForm'
import EditConnectionForm from '../components/EditConnectionForm'
import GraphView from './GraphView'
import styles from './Workspace.module.css'

type WorkspaceTab = 'data' | 'graph'

/** Duration (ms) to highlight a search-jumped element before clearing. */
const HIGHLIGHT_DURATION_MS = 1500

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

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function downloadBlob(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
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
  id?: string
  host: Host
  highlighted?: boolean
  onEdit: (h: Host) => void
  onDelete: (h: Host) => void
}

function HostCard({ id, host, highlighted, onEdit, onDelete }: HostCardProps) {
  return (
    <div id={id} className={`${styles.hostCard} ${highlighted ? styles.highlighted : ''}`}>
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
            <span key={ip.id} className={styles.ipChipRow}>
              <span className={styles.ipChip}>{ip.ip_address}</span>
              <span className={styles.ipAddrType}>{ip.addr_type}</span>
            </span>
          ))}
        </div>
      )}

      {host.users.length > 0 && (
        <div className={styles.hostUsers}>
          {host.users.map(u => (
            <span key={u.id} className={styles.userChip} title={`${u.source}${u.shell ? ' · ' + u.shell : ''}`}>
              {u.username}
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

// ─── Credential row ───────────────────────────────────────────────────────────

interface CredentialRowProps {
  id?: string
  cred: Credential
  links: CredentialLink[]
  hosts: Host[]
  highlighted?: boolean
  onEdit: (c: Credential) => void
  onDelete: (c: Credential) => void
  onEditLink: (l: CredentialLink) => void
  onDeleteLink: (l: CredentialLink) => void
}

function CredentialRow({ id, cred, links, hosts, highlighted, onEdit, onDelete, onEditLink, onDeleteLink }: CredentialRowProps) {
  return (
    <div id={id} className={`${styles.credRow} ${highlighted ? styles.highlighted : ''}`}>
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
          <button
            className={styles.iconBtn}
            title="Download credential value"
            aria-label="Download credential value"
            onClick={() => {
              const ext = cred.cred_type === 'private_key' ? 'pem'
                : cred.cred_type === 'public_key' ? 'pub' : 'txt'
              const name = cred.name ? cred.name.replace(/[^a-z0-9_\-\.]/gi, '_') : cred.id
              downloadBlob(cred.value, `${name}.${ext}`)
            }}
          >⬇</button>
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
  id?: string
  conn: ConnectionRecord
  hosts: Host[]
  highlighted?: boolean
  onEdit: (c: ConnectionRecord) => void
  onDelete: (c: ConnectionRecord) => void
}

function ConnectionRow({ id, conn, hosts, highlighted, onEdit, onDelete }: ConnectionRowProps) {
  const srcHost = hosts.find(h => h.id === conn.src_host_id)
  const dstHost = hosts.find(h => h.id === conn.dst_host_id)

  return (
    <div id={id} className={`${styles.connRow} ${highlighted ? styles.highlighted : ''}`}>
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

// ─── Evidence file row ────────────────────────────────────────────────────────

interface EvidenceFileRowProps {
  opId: string
  file: UploadFile
  hosts: Host[]
  onView: (file: UploadFile) => void
}

function EvidenceFileRow({ opId, file, hosts, onView }: EvidenceFileRowProps) {
  const hostNames = file.host_ids
    .map(id => hosts.find(h => h.id === id)?.nickname ?? id.slice(0, 8))
    .filter((v, i, a) => a.indexOf(v) === i)  // deduplicate

  return (
    <div className={styles.fileRow}>
      <span className={styles.fileIcon}>📄</span>
      <span className={styles.fileName}>{file.original_name}</span>
      <div className={styles.fileHosts}>
        {hostNames.map(n => (
          <span key={n} className={styles.fileHostChip}>{n}</span>
        ))}
      </div>
      <span className={styles.fileMeta}>{formatFileSize(file.size_bytes)}</span>
      <span className={styles.fileMeta}>{formatTimestamp(file.uploaded_at)}</span>
      <div className={styles.rowActions}>
        <button
          className={styles.iconBtn}
          onClick={() => onView(file)}
          title="View file"
          aria-label="View file"
        >👁</button>
        <a
          className={styles.iconBtn}
          href={uploadFileUrl(opId, file.safe_name, true)}
          title="Download file"
          aria-label="Download file"
          style={{ textDecoration: 'none' }}
        >⬇</a>
      </div>
    </div>
  )
}

// ─── File viewer modal ────────────────────────────────────────────────────────

interface FileViewerProps {
  opId: string
  file: UploadFile
  onClose: () => void
}

function FileViewer({ opId, file, onClose }: FileViewerProps) {
  const [content, setContent] = useState<string | null>(null)
  const [binary, setBinary] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(uploadFileUrl(opId, file.safe_name, false))
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.arrayBuffer()
      })
      .then(buf => {
        if (cancelled) return
        const bytes = new Uint8Array(buf)
        // Detect binary: look for null bytes in first 8 KB
        const sample = bytes.slice(0, 8192)
        if (sample.includes(0)) {
          setBinary(true)
          setContent(null)
        } else {
          setBinary(false)
          setContent(new TextDecoder('utf-8', { fatal: false }).decode(buf))
        }
      })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [opId, file.safe_name])

  return (
    <div className={styles.viewerOverlay} onClick={onClose}>
      <div className={styles.viewerModal} onClick={e => e.stopPropagation()}>
        <div className={styles.viewerHeader}>
          <span className={styles.viewerTitle}>{file.original_name}</span>
          <span className={styles.viewerMeta}>{formatFileSize(file.size_bytes)} · {formatTimestamp(file.uploaded_at)}</span>
          <div className={styles.viewerActions}>
            <a
              className={styles.iconBtn}
              href={uploadFileUrl(opId, file.safe_name, true)}
              title="Download"
              style={{ textDecoration: 'none' }}
            >⬇ Download</a>
            <button className={styles.iconBtn} onClick={onClose} title="Close" aria-label="Close viewer">✕</button>
          </div>
        </div>
        <div className={styles.viewerBody}>
          {loading && <p className={styles.viewerHint}>Loading…</p>}
          {error && <p className={styles.viewerHint} style={{ color: 'var(--danger)' }}>Failed to load: {error}</p>}
          {!loading && !error && binary && (
            <p className={styles.viewerHint}>Binary file — <a href={uploadFileUrl(opId, file.safe_name, true)} className={styles.viewerLink}>download</a> to view.</p>
          )}
          {!loading && !error && !binary && content !== null && (
            <pre className={styles.viewerPre}>{content}</pre>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Workspace ────────────────────────────────────────────────────────────────

export default function Workspace({ op, onBack }: Props) {
  const [tab, setTab] = useState<WorkspaceTab>(() => {
    try {
      const stored = sessionStorage.getItem(`lockpick_tab_${op.id}`)
      return (stored === 'graph' ? 'graph' : 'data') as WorkspaceTab
    } catch {
      return 'data'
    }
  })
  const [hosts, setHosts] = useState<Host[]>([])
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [links, setLinks] = useState<CredentialLink[]>([])
  const [connections, setConnections] = useState<ConnectionRecord[]>([])
  const [uploads, setUploads] = useState<UploadFile[]>([])
  const [viewingFile, setViewingFile] = useState<UploadFile | null>(null)
  const [activityLog, setActivityLog] = useState<ActivityLog[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [focusEntityId, setFocusEntityId] = useState<string | null>(null)
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [baselineTotal, setBaselineTotal] = useState<number | null>(null)
  const [currentTotal, setCurrentTotal] = useState<number | null>(null)

  // Callback registered by GraphView so Workspace can trigger a graph reload
  // (used by WS event handler when host entity changes)
  const graphReloadRef = useRef<(() => void) | null>(null)

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
      const [hostsData, credsData, linksData, connsData, uploadsData, statsData, activityData] = await Promise.all([
        listHosts(op.id),
        listCredentials(op.id),
        listCredentialLinks(op.id),
        listConnections(op.id),
        listUploads(op.id),
        getOpStats(op.id),
        getActivityLog(op.id),
      ])
      setHosts(hostsData)
      setCredentials(credsData)
      setLinks(linksData)
      setConnections(connsData)
      setUploads(uploadsData)
      setActivityLog(activityData)
      setBaselineTotal(statsData.total_records)
      setCurrentTotal(statsData.total_records)
    } catch (err) {
      // If the op no longer exists (e.g. deleted elsewhere), go back to selector
      if (err instanceof ApiError && err.status === 404) {
        onBack()
        return
      }
      setError('Failed to load data.')
    } finally {
      setLoading(false)
    }
  }, [op.id, onBack])

  useEffect(() => { fetchAll() }, [fetchAll])

  const refreshActivity = useCallback(async () => {
    try {
      setActivityLog(await getActivityLog(op.id))
    } catch (err) {
      console.error('Failed to refresh activity log:', err)
    }
  }, [op.id])

  // WebSocket live push — refetch stats on any event
  const { status: wsStatus, reconnectIn, reconnect } = useOpWebSocket(
    op.id,
    useCallback(async () => {
      try {
        const s = await getOpStats(op.id)
        setCurrentTotal(s.total_records)
      } catch {
        // ignore errors — banner will just not update
      }
    }, [op.id]),
  )

  // Fallback: poll every 30s when WS is disconnected
  useEffect(() => {
    if (wsStatus !== 'disconnected') return
    const id = setInterval(async () => {
      try {
        const s = await getOpStats(op.id)
        setCurrentTotal(s.total_records)
      } catch {
        // ignore poll errors
      }
    }, 30_000)
    return () => clearInterval(id)
  }, [op.id, wsStatus])

  // Ctrl+F → open search modal (wired to SearchModal in step 5)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'f' && (e.ctrlKey || e.metaKey)) {
        const tag = (e.target as HTMLElement).tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // ─── Search select handler ────────────────────────────────────────────────

  function handleSearchSelect(result: SearchResult) {
    setSearchOpen(false)
    if (tab === 'graph') {
      if (result.host_id) setFocusEntityId(result.host_id)
    } else {
      let elementId: string | null = null
      if (result.type === 'host' || result.type === 'host_ip' || result.type === 'host_user') {
        elementId = result.host_id ? `host-${result.host_id}` : null
      } else if (result.type === 'credential') {
        elementId = result.credential_id ? `cred-${result.credential_id}` : null
      } else if (result.type === 'connection') {
        elementId = result.connection_id ? `conn-${result.connection_id}` : null
      }
      if (elementId) {
        setHighlightId(elementId)
        setTimeout(() => setHighlightId(null), HIGHLIGHT_DURATION_MS)
        requestAnimationFrame(() => {
          document.getElementById(elementId!)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        })
      }
    }
  }

  // ─── Delete handlers ─────────────────────────────────────────────────────

  async function confirmDeleteHost() {
    if (!deleteHostTarget) return
    setDeleteLoading(true)
    try {
      await deleteHost(deleteHostTarget.id)
      setHosts(prev => prev.filter(h => h.id !== deleteHostTarget.id))
      setDeleteHostTarget(null)
      refreshActivity()
    } catch (err) {
      console.error('Failed to delete host:', err)
      // Leave modal open so user can retry.
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
      refreshActivity()
    } catch (err) {
      console.error('Failed to delete credential:', err)
      // Leave modal open so user can retry.
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
      refreshActivity()
    } catch (err) {
      console.error('Failed to delete credential link:', err)
      // Leave modal open so user can retry.
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
      refreshActivity()
    } catch (err) {
      console.error('Failed to delete connection:', err)
      // Leave modal open so user can retry.
    } finally {
      setDeleteLoading(false)
    }
  }

  const hasData = hosts.length > 0 || credentials.length > 0 || connections.length > 0

  const notificationDelta =
    baselineTotal !== null && currentTotal !== null && currentTotal > baselineTotal
      ? currentTotal - baselineTotal
      : 0

  function handleBannerRefresh() {
    fetchAll()
  }

  return (
    <div className={styles.workspace}>
      {/* Notification banner — shown when new records detected via polling */}
      <NotificationBanner delta={notificationDelta} onRefresh={handleBannerRefresh} />

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
        <div className={styles.headerActions}>
          <WsStatusIndicator
            status={wsStatus}
            reconnectIn={reconnectIn}
            onReconnect={reconnect}
          />
          <button
            className={styles.headerBtn}
            onClick={() => exportOp(op.id)}
            title="Export op as JSON"
            aria-label="Export op"
          >
            ⬇ Export
          </button>
          <button
            className={styles.headerBtn}
            onClick={() => setSearchOpen(true)}
            title="Search (Ctrl+F)"
            aria-label="Open search"
          >
            ⌕
          </button>
        </div>
        <div className={styles.tabBar}>
          <button
            className={`${styles.tabBtn} ${tab === 'data' ? styles.tabActive : ''}`}
            onClick={() => { setTab('data'); sessionStorage.setItem(`lockpick_tab_${op.id}`, 'data') }}
          >
            Data
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'graph' ? styles.tabActive : ''}`}
            onClick={() => { setTab('graph'); sessionStorage.setItem(`lockpick_tab_${op.id}`, 'graph') }}
          >
            Graph
          </button>
        </div>
      </header>

      {/* Tab content area — both panels always rendered with real dimensions.
          visibility:hidden (not display:none) keeps real dimensions in layout
          so ForceGraph2D's ResizeObserver measures the container correctly. */}
      <div style={{ position: 'relative', flex: 1, minHeight: 0, overflow: 'hidden' }}>

        {/* Graph panel */}
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          visibility: tab === 'graph' ? 'visible' : 'hidden',
          pointerEvents: tab === 'graph' ? 'auto' : 'none',
        }}>
          <GraphView
            op={op}
            allHosts={hosts}
            credentials={credentials}
            focusHostId={focusEntityId}
            onRegisterReload={reload => { graphReloadRef.current = reload }}
          />
        </div>

        {/* Data panel */}
        <main className={styles.main} style={{
          position: 'absolute', inset: 0,
          visibility: tab === 'data' ? 'visible' : 'hidden',
          pointerEvents: tab === 'data' ? 'auto' : 'none',
        }}>
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
                      id={`host-${h.id}`}
                      host={h}
                      highlighted={highlightId === `host-${h.id}`}
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
                      id={`cred-${cred.id}`}
                      cred={cred}
                      links={links.filter(l => l.credential_id === cred.id)}
                      hosts={hosts}
                      highlighted={highlightId === `cred-${cred.id}`}
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
                      id={`conn-${conn.id}`}
                      conn={conn}
                      hosts={hosts}
                      highlighted={highlightId === `conn-${conn.id}`}
                      onEdit={setEditConn}
                      onDelete={setDeleteConnTarget}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Evidence Files */}
            {uploads.length > 0 && (
              <section>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Evidence Files</h2>
                  <span className={styles.sectionCount}>{uploads.length}</span>
                </div>
                <div className={styles.listPanel}>
                  {uploads.map(f => (
                    <EvidenceFileRow
                      key={f.safe_name}
                      opId={op.id}
                      file={f}
                      hosts={hosts}
                      onView={setViewingFile}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Activity Log */}
            {activityLog.length > 0 && (
              <section>
                <div className={styles.sectionHeader}>
                  <h2 className={styles.sectionTitle}>Activity</h2>
                  <span className={styles.sectionCount}>{activityLog.length}</span>
                </div>
                <div className={styles.listPanel}>
                  {activityLog.map(entry => (
                    <div key={entry.id} className={styles.activityRow}>
                      <span className={styles.activityAction}>{entry.action}</span>
                      {entry.detail && <span className={styles.activityDetail}>{entry.detail}</span>}
                      <span className={styles.activityTime}>{formatTimestamp(entry.created_at)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>
      </div>{/* end overlay container */}

      {/* File viewer modal */}
      {viewingFile && (
        <FileViewer
          opId={op.id}
          file={viewingFile}
          onClose={() => setViewingFile(null)}
        />
      )}

      {/* Search modal */}
      {searchOpen && (
        <SearchModal opId={op.id} onClose={() => setSearchOpen(false)} onSelectResult={handleSearchSelect} />
      )}

      {/* FAB + add modal */}
      <AddDataModal opId={op.id} hosts={hosts} credentials={credentials} onDataAdded={fetchAll} />

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
            credentials={credentials}
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
