/**
 * Operation Selector page — lists existing operations and allows creating new ones.
 * This is the entry point of the app before an operation is selected.
 */
import { useState, useEffect, useCallback } from 'react'
import type { Operation, CreateOperationRequest } from '../types'
import { listOperations, createOperation } from '../api/operations'
import styles from './OpSelector.module.css'

interface Props {
  onSelectOp: (op: Operation) => void
}

interface CreateModalProps {
  onClose: () => void
  onCreated: (op: Operation) => void
}

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

function CreateOpModal({ onClose, onCreated }: CreateModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Operation name is required')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data: CreateOperationRequest = {
        name: name.trim(),
        description: description.trim() || null,
      }
      const op = await createOperation(data)
      onCreated(op)
    } catch (err) {
      setError('Failed to create operation. Please try again.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <h2>New Operation</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="op-name">Operation Name *</label>
            <input
              id="op-name"
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Acme Corp Q1 2026"
              autoFocus
              disabled={loading}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="op-desc">Description</label>
            <textarea
              id="op-desc"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Optional notes about this operation"
              rows={3}
              disabled={loading}
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <div className={styles.formActions}>
            <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className={styles.btnPrimary} disabled={loading}>
              {loading ? 'Creating…' : 'Create Operation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function OpSelector({ onSelectOp }: Props) {
  const [operations, setOperations] = useState<Operation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch] = useState('')

  const fetchOps = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const ops = await listOperations()
      setOperations(ops)
    } catch (err) {
      setError('Failed to load operations. Is the backend running?')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOps()
  }, [fetchOps])

  function handleCreated(op: Operation) {
    setShowCreate(false)
    setOperations(prev => [op, ...prev])
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
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
              <a href={`${apiBase}/docs`} target="_blank" rel="noopener noreferrer" className={styles.apiLink}>
                Swagger
              </a>
              <a href={`${apiBase}/redoc`} target="_blank" rel="noopener noreferrer" className={styles.apiLink}>
                ReDoc
              </a>
            </div>
            <button
              className={styles.btnPrimary}
              onClick={() => setShowCreate(true)}
            >
              + New Operation
            </button>
          </div>
        </div>

        {/* Search bar — only shown when there are ops */}
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
              <button className={styles.searchClear} onClick={() => setSearch('')} aria-label="Clear search">
                ✕
              </button>
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
              <button className={styles.btnSecondary} onClick={fetchOps}>
                Retry
              </button>
            </div>
          )}

          {!loading && !error && operations.length === 0 && (
            <div className={styles.state}>
              <LockpickLogo size={48} />
              <p className={styles.stateTitle}>No operations yet</p>
              <p className={styles.stateText}>
                Create your first operation to start tracking SSH pivot paths.
              </p>
              <button className={styles.btnPrimary} onClick={() => setShowCreate(true)}>
                + Create First Operation
              </button>
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
                <li key={op.id}>
                  <button
                    className={styles.opCard}
                    onClick={() => onSelectOp(op)}
                  >
                    <div className={styles.opCardMain}>
                      <span className={styles.opName}>{op.name}</span>
                      {op.description && (
                        <span className={styles.opDesc}>{op.description}</span>
                      )}
                    </div>
                    <div className={styles.opMeta}>
                      <span className={styles.opDate}>{formatDate(op.created_at)}</span>
                      <span className={styles.opArrow}>→</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {showCreate && (
        <CreateOpModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  )
}
