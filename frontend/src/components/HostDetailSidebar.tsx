/**
 * Right sidebar — shows detail for a selected graph node.
 * If a full Host object is provided, shows tabs: Info | Sudo Rules | Notes.
 */
import { useState, useEffect, useCallback } from 'react'
import type { GraphEdge, GraphNode, Host, HostNote, SudoRule } from '../types'
import { getSudoRules, deleteSudoRule, getHostNotes, createHostNote, deleteHostNote } from '../api/hosts'
import { updateHost } from '../api/hosts'
import { statusColors, STATUS_LABELS } from '../theme'
import CollectionPanel from './CollectionPanel'
import styles from './HostDetailSidebar.module.css'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  observed: 'Observed',
  indicator: 'Indicator',
}

const ADDR_TYPE_LABEL: Record<string, string> = {
  ipv4: 'IPv4',
  ipv6: 'IPv6',
  hostname: 'hostname',
}

type Tab = 'info' | 'sudo' | 'notes' | 'collection'

interface Props {
  node: GraphNode
  edges: GraphEdge[]
  host?: Host | null
  onClose: () => void
  onHostUpdated?: () => void
  onMergeRequested?: () => void
}

export default function HostDetailSidebar({ node, edges, host, onClose, onHostUpdated, onMergeRequested }: Props) {
  const [tab, setTab] = useState<Tab>('info')

  // Sudo rules state
  const [sudoRules, setSudoRules] = useState<SudoRule[]>([])
  const [sudoLoading, setSudoLoading] = useState(false)
  const [sudoError, setSudoError] = useState<string | null>(null)

  // Status state
  const [currentStatus, setCurrentStatus] = useState<string | null>(host?.status ?? null)

  // Notes state
  const [notes, setNotes] = useState<HostNote[]>([])
  const [notesLoading, setNotesLoading] = useState(false)
  const [notesError, setNotesError] = useState<string | null>(null)
  const [noteText, setNoteText] = useState('')
  const [noteAdding, setNoteAdding] = useState(false)

  const loadSudoRules = useCallback(async () => {
    if (!host) return
    setSudoLoading(true)
    setSudoError(null)
    try {
      const rules = await getSudoRules(host.id)
      setSudoRules(rules)
    } catch {
      setSudoError('Failed to load sudo rules.')
    } finally {
      setSudoLoading(false)
    }
  }, [host])

  const loadNotes = useCallback(async () => {
    if (!host) return
    setNotesLoading(true)
    setNotesError(null)
    try {
      const fetched = await getHostNotes(host.id)
      setNotes(fetched)
    } catch {
      setNotesError('Failed to load notes.')
    } finally {
      setNotesLoading(false)
    }
  }, [host])

  useEffect(() => {
    if (tab === 'sudo') loadSudoRules()
    if (tab === 'notes') loadNotes()
  }, [tab, loadSudoRules, loadNotes])

  // Reset tab and status when a different node is selected
  useEffect(() => {
    setTab('info')
    setSudoRules([])
    setNotes([])
    setNoteText('')
    setCurrentStatus(host?.status ?? null)
  }, [node.host_id, host?.status])

  async function handleStatusChange(value: string) {
    if (!host) return
    const newStatus = value || null
    setCurrentStatus(newStatus)
    try {
      await updateHost(host.id, { status: newStatus })
      onHostUpdated?.()
    } catch {
      // Revert on failure
      setCurrentStatus(host.status ?? null)
    }
  }

  async function handleDeleteRule(ruleId: string) {
    if (!host) return
    try {
      await deleteSudoRule(host.id, ruleId)
      setSudoRules(prev => prev.filter(r => r.id !== ruleId))
    } catch {
      setSudoError('Failed to delete rule.')
    }
  }

  async function handleAddNote() {
    if (!host || !noteText.trim()) return
    setNoteAdding(true)
    setNotesError(null)
    try {
      const note = await createHostNote(host.id, noteText.trim())
      setNotes(prev => [...prev, note])
      setNoteText('')
    } catch {
      setNotesError('Failed to add note.')
    } finally {
      setNoteAdding(false)
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!host) return
    try {
      await deleteHostNote(host.id, noteId)
      setNotes(prev => prev.filter(n => n.id !== noteId))
    } catch {
      setNotesError('Failed to delete note.')
    }
  }

  function formatNoteTimestamp(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  const outgoing = edges.filter(e => e.src_host_id === node.host_id)
  const incoming = edges.filter(e => e.dst_host_id === node.host_id)

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.title}>{node.nickname}</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
      </div>

      {host && (
        <div className={styles.tabBar}>
          <button
            className={`${styles.tabBtn} ${tab === 'info' ? styles.tabActive : ''}`}
            onClick={() => setTab('info')}
          >
            Info
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'sudo' ? styles.tabActive : ''}`}
            onClick={() => setTab('sudo')}
          >
            Sudo Rules
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'notes' ? styles.tabActive : ''}`}
            onClick={() => setTab('notes')}
          >
            Notes
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'collection' ? styles.tabActive : ''}`}
            onClick={() => setTab('collection')}
          >
            Collection
          </button>
        </div>
      )}

      <div className={styles.body}>
        {(!host || tab === 'info') && (
          <>
            {host && onMergeRequested && (
              <div className={styles.section}>
                <button
                  className={styles.mergeBtn}
                  onClick={onMergeRequested}
                  title="Move all of this host's relations onto another host, then delete this host"
                >
                  Merge into…
                </button>
              </div>
            )}
            {host && (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>Status</div>
                <div className={styles.statusPickerRow}>
                  {currentStatus && (
                    <span
                      className={styles.statusDot}
                      style={{ background: statusColors[currentStatus] ?? 'var(--text-muted)' }}
                    />
                  )}
                  <select
                    className={styles.statusSelect}
                    value={currentStatus ?? ''}
                    onChange={e => handleStatusChange(e.target.value)}
                  >
                    <option value="">— unset —</option>
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            {host && host.ips.length > 0 ? (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>IPs / Hostnames</div>
                <div className={styles.addrList}>
                  {host.ips.map(ip => (
                    <div key={ip.id} className={styles.addrRow}>
                      <span className={styles.chip}>{ip.ip_address}</span>
                      <span className={styles.addrTypeBadge}>
                        {ADDR_TYPE_LABEL[ip.addr_type] ?? ip.addr_type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : node.ips.length > 0 ? (
              <div className={styles.section}>
                <div className={styles.sectionLabel}>IPs</div>
                <div className={styles.chips}>
                  {node.ips.map(ip => (
                    <span key={ip} className={styles.chip}>{ip}</span>
                  ))}
                </div>
              </div>
            ) : null}

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
          </>
        )}

        {host && tab === 'sudo' && (
          <div className={styles.section}>
            {sudoLoading && <p className={styles.empty}>Loading…</p>}
            {sudoError && <p className={styles.sudoError}>{sudoError}</p>}
            {!sudoLoading && !sudoError && sudoRules.length === 0 && (
              <p className={styles.empty}>No sudo rules found.</p>
            )}
            {!sudoLoading && sudoRules.map(rule => (
              <div key={rule.id} className={styles.sudoRule}>
                <div className={styles.sudoRuleHeader}>
                  <span className={styles.sudoSubject}>
                    {rule.subject}
                    {rule.subject_type === 'group' && (
                      <span className={styles.groupBadge}>group</span>
                    )}
                  </span>
                  <span className={styles.sudoRunAs}>→ {rule.run_as}</span>
                  {rule.nopasswd && (
                    <span className={styles.nopasswdBadge}>NOPASSWD</span>
                  )}
                  <button
                    className={styles.deleteRuleBtn}
                    onClick={() => handleDeleteRule(rule.id)}
                    aria-label={`Delete sudo rule for ${rule.subject}`}
                    title="Delete rule"
                  >
                    ✕
                  </button>
                </div>
                <div className={styles.sudoCommands}>{rule.commands}</div>
              </div>
            ))}
          </div>
        )}

        {host && tab === 'collection' && (
          <CollectionPanel opId={host.op_id} hostId={host.id} onImported={onHostUpdated} />
        )}

        {host && tab === 'notes' && (
          <div className={styles.section}>
            {notesLoading && <p className={styles.empty}>Loading…</p>}
            {notesError && <p className={styles.sudoError}>{notesError}</p>}
            {!notesLoading && notes.length > 0 && (
              <div className={styles.noteList}>
                {notes.map(note => (
                  <div key={note.id} className={styles.noteItem}>
                    <div className={styles.noteHeader}>
                      <span className={styles.noteTimestamp}>
                        {formatNoteTimestamp(note.created_at)}
                      </span>
                      <button
                        className={styles.deleteNoteBtn}
                        onClick={() => handleDeleteNote(note.id)}
                        aria-label="Delete note"
                        title="Delete note"
                      >
                        ✕
                      </button>
                    </div>
                    <div className={styles.noteContent}>{note.content}</div>
                  </div>
                ))}
              </div>
            )}
            {!notesLoading && notes.length === 0 && !notesError && (
              <p className={styles.empty}>No notes yet.</p>
            )}
            <div className={styles.noteForm}>
              <textarea
                className={styles.noteTextarea}
                placeholder="Add a note…"
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleAddNote()
                }}
              />
              <button
                className={styles.noteAddBtn}
                onClick={handleAddNote}
                disabled={noteAdding || !noteText.trim()}
              >
                {noteAdding ? 'Adding…' : 'Add Note'}
              </button>
            </div>
          </div>
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
