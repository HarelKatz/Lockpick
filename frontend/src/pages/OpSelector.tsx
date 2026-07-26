/**
 * Operation Selector page — lists existing operations and allows creating,
 * editing, and deleting them.
 */
import { useState, useEffect, useCallback } from 'react'
import type { Operation, CreateOperationRequest, UpdateOperationRequest } from '../types'
import { listOperations, createOperation, updateOperation, deleteOperation, getOperation } from '../api/operations'
import ImportOpModal from '../components/ImportOpModal'
import styles from './OpSelector.module.css'

interface Props {
  onSelectOp: (op: Operation) => void
}

// ─── Logo ──────────────────────────────────────────────────────────────────────

function LockpickLogo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="5" y="17" width="17" height="12" rx="3" fill="#58a6ff"/>
      <path d="M8 17V11C8 7.686 10.686 5 13.5 5S19 7.686 19 11v2" stroke="#58a6ff" strokeWidth="2.5" strokeLinecap="round"/>
      <circle cx="13.5" cy="22" r="1.8" fill="#0d1117"/>
      <rect x="12.6" y="22" width="1.8" height="3" rx="0.9" fill="#0d1117"/>
      <path d="M21 10 L27 6" stroke="#a5d6ff" strokeWidth="1.8" strokeLinecap="round"/>
      <circle cx="27" cy="6" r="1.2" fill="#a5d6ff"/>
    </svg>
  )
}

// ─── Create Op Modal ──────────────────────────────────────────────────────────

interface CreateModalProps {
  onClose: () => void
  onCreated: (op: Operation) => void
}

function CreateOpModal({ onClose, onCreated }: CreateModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Operation name is required'); return }
    setLoading(true)
    setError(null)
    try {
      const data: CreateOperationRequest = {
        name: name.trim(),
        description: description.trim() || null,
      }
      const op = await createOperation(data)
      onCreated(op)
    } catch {
      setError('Failed to create operation. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2>New Operation</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="op-name">Operation Name *</label>
            <input id="op-name" type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Acme Corp Q1 2026" autoFocus disabled={loading} />
          </div>
          <div className={styles.field}>
            <label htmlFor="op-desc">Description</label>
            <textarea id="op-desc" value={description} onChange={e => setDescription(e.target.value)}
              placeholder="Optional notes about this operation" rows={3} disabled={loading} />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <div className={styles.formActions}>
            <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>Cancel</button>
            <button type="submit" className={styles.btnPrimary} disabled={loading}>
              {loading ? 'Creating…' : 'Create Operation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Edit Op Modal ────────────────────────────────────────────────────────────

interface EditOpModalProps {
  op: Operation
  onClose: () => void
  onSaved: (op: Operation) => void
}

function EditOpModal({ op, onClose, onSaved }: EditOpModalProps) {
  const [name, setName] = useState(op.name)
  const [description, setDescription] = useState(op.description ?? '')
  const [summary, setSummary] = useState(op.summary ?? '')
  const [briefing, setBriefing] = useState(op.briefing ?? '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Operation name is required'); return }
    setLoading(true)
    setError(null)
    try {
      const data: UpdateOperationRequest = {
        name: name.trim(),
        description: description.trim() || null,
        summary: summary.trim() || null,
        briefing: briefing.trim() || null,
      }
      const updated = await updateOperation(op.id, data)
      onSaved(updated)
    } catch {
      setError('Failed to save changes.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2>Edit Operation</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="edit-op-name">Operation Name *</label>
            <input id="edit-op-name" type="text" value={name} onChange={e => setName(e.target.value)}
              autoFocus disabled={loading} />
          </div>
          <div className={styles.field}>
            <label htmlFor="edit-op-desc">Description</label>
            <textarea id="edit-op-desc" value={description} onChange={e => setDescription(e.target.value)}
              placeholder="Optional notes about this operation" rows={3} disabled={loading} />
          </div>
          <div className={styles.field}>
            <label htmlFor="edit-op-summary">Summary</label>
            <textarea id="edit-op-summary" value={summary} onChange={e => setSummary(e.target.value)}
              placeholder="Short status line shown in the op header (markdown)" rows={2} disabled={loading} />
          </div>
          <div className={styles.field}>
            <label htmlFor="edit-op-briefing">Briefing</label>
            <textarea id="edit-op-briefing" value={briefing} onChange={e => setBriefing(e.target.value)}
              placeholder="Long-form briefing — scope, RoE, objectives (markdown)" rows={6} disabled={loading} />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <div className={styles.formActions}>
            <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>Cancel</button>
            <button type="submit" className={styles.btnPrimary} disabled={loading}>
              {loading ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Delete Op Modal ──────────────────────────────────────────────────────────

interface DeleteOpModalProps {
  op: Operation
  onClose: () => void
  onDeleted: (opId: string) => void
}

function DeleteOpModal({ op, onClose, onDeleted }: DeleteOpModalProps) {
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const confirmed = confirmation === op.id

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!confirmed) { setError('UUID does not match.'); return }
    setLoading(true)
    setError(null)
    try {
      await deleteOperation(op.id)
      onDeleted(op.id)
    } catch {
      setError('Failed to delete operation.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2 className={styles.dangerTitle}>Delete Operation</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close" disabled={loading}>✕</button>
        </div>
        <form onSubmit={handleSubmit} className={styles.form}>
          <p className={styles.deleteWarning}>
            This will permanently delete <strong>{op.name}</strong> and all its hosts, credentials,
            and connections. This cannot be undone.
          </p>
          <div className={styles.field}>
            <label htmlFor="delete-confirm">
              Type the operation UUID to confirm:
              <span className={styles.uuidHint}>{op.id}</span>
            </label>
            <input
              id="delete-confirm"
              type="text"
              value={confirmation}
              onChange={e => setConfirmation(e.target.value)}
              placeholder={op.id}
              autoFocus
              disabled={loading}
              className={styles.uuidInput}
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <div className={styles.formActions}>
            <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>Cancel</button>
            <button type="submit" className={styles.btnDanger} disabled={!confirmed || loading}>
              {loading ? 'Deleting…' : 'Delete Operation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── OpSelector ───────────────────────────────────────────────────────────────

export default function OpSelector({ onSelectOp }: Props) {
  const [operations, setOperations] = useState<Operation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [editTarget, setEditTarget] = useState<Operation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Operation | null>(null)
  const [search, setSearch] = useState('')

  const fetchOps = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const ops = await listOperations()
      setOperations(ops)
    } catch {
      setError('Failed to load operations. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchOps() }, [fetchOps])

  function handleCreated(op: Operation) {
    onSelectOp(op)
  }

  async function handleImported(opId: string) {
    setShowImport(false)
    try {
      const op = await getOperation(opId)
      onSelectOp(op)
    } catch {
      // Fall back to refreshing the list
      fetchOps()
    }
  }

  function handleSaved(updated: Operation) {
    setOperations(prev => prev.map(o => o.id === updated.id ? updated : o))
    setEditTarget(null)
  }

  function handleDeleted(opId: string) {
    setOperations(prev => prev.filter(o => o.id !== opId))
    setDeleteTarget(null)
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  const apiBase = `http://${window.location.hostname}:8000`
  const filteredOps = operations.filter(op =>
    op.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>
              <LockpickLogo size={32} />
              Lockpick
            </h1>
            <p className={styles.subtitle}>Select an operation to continue, or create a new one</p>
          </div>
          <div className={styles.headerActions}>
            <div className={styles.apiLinks}>
              <a href={`${apiBase}/docs`} target="_blank" rel="noopener noreferrer" className={styles.apiLink}>Swagger</a>
              <a href={`${apiBase}/redoc`} target="_blank" rel="noopener noreferrer" className={styles.apiLink}>ReDoc</a>
            </div>
            <button className={styles.btnSecondary} onClick={() => setShowImport(true)}>
              ⬆ Import
            </button>
            <button className={styles.btnPrimary} onClick={() => setShowCreate(true)}>
              + New Operation
            </button>
          </div>
        </div>

        {/* Search bar */}
        {!loading && !error && operations.length > 0 && (
          <div className={styles.searchBar}>
            <span className={styles.searchIcon}>⌕</span>
            <input
              type="text"
              placeholder="Search operations…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className={styles.searchInput}
              autoComplete="off"
            />
            {search && (
              <button className={styles.searchClear} onClick={() => setSearch('')} aria-label="Clear search">✕</button>
            )}
          </div>
        )}

        {/* Content */}
        <div className={styles.content}>
          {loading && (
            <div className={styles.state}>
              <p className={styles.stateText}>Loading operations…</p>
            </div>
          )}

          {error && !loading && (
            <div className={styles.stateError}>
              <p>{error}</p>
              <button className={styles.btnSecondary} onClick={fetchOps}>Retry</button>
            </div>
          )}

          {!loading && !error && operations.length === 0 && (
            <div className={styles.state}>
              <LockpickLogo size={48} />
              <p className={styles.stateTitle}>No operations yet</p>
              <p className={styles.stateText}>Create your first operation to start tracking SSH pivot paths.</p>
              <button className={styles.btnPrimary} onClick={() => setShowCreate(true)}>+ Create First Operation</button>
            </div>
          )}

          {!loading && !error && operations.length > 0 && filteredOps.length === 0 && (
            <div className={styles.state}>
              <p className={styles.stateTitle}>No results</p>
              <p className={styles.stateText}>No operations match "{search}"</p>
            </div>
          )}

          {!loading && !error && filteredOps.length > 0 && (
            <ul className={styles.opList}>
              {filteredOps.map(op => (
                <li key={op.id} className={styles.opItem}>
                  <button className={styles.opCard} onClick={() => onSelectOp(op)}>
                    <div className={styles.opCardMain}>
                      <div className={styles.opNameRow}>
                        <span className={styles.opName}>{op.name}</span>
                        <span className={styles.opId}>#{op.id.split('-')[0]}</span>
                      </div>
                      {op.description && (
                        <span className={styles.opDesc}>{op.description}</span>
                      )}
                    </div>
                    <div className={styles.opMeta}>
                      <span className={styles.opDate}>{formatDate(op.created_at)}</span>
                      <span className={styles.opArrow}>→</span>
                    </div>
                  </button>
                  <div className={styles.opActions}>
                    <button
                      className={styles.opActionBtn}
                      onClick={e => { e.stopPropagation(); setEditTarget(op) }}
                      title="Edit operation"
                      aria-label="Edit operation"
                    >
                      ✎
                    </button>
                    <button
                      className={`${styles.opActionBtn} ${styles.opActionBtnDanger}`}
                      onClick={e => { e.stopPropagation(); setDeleteTarget(op) }}
                      title="Delete operation"
                      aria-label="Delete operation"
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {showCreate && (
        <CreateOpModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      )}
      {showImport && (
        <ImportOpModal onClose={() => setShowImport(false)} onImported={handleImported} />
      )}
      {editTarget && (
        <EditOpModal op={editTarget} onClose={() => setEditTarget(null)} onSaved={handleSaved} />
      )}
      {deleteTarget && (
        <DeleteOpModal op={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={handleDeleted} />
      )}
    </div>
  )
}
