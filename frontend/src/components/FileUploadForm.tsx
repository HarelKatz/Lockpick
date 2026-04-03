/**
 * FileUploadForm — drag-and-drop file upload with metadata selection.
 * Renders inside the AddDataModal "File Upload" tab.
 */
import { useState, useRef } from 'react'
import type { Host, UploadFileType, UploadResult } from '../types'
import { uploadFile } from '../api/upload'
import styles from './FileUploadForm.module.css'

const FILE_TYPES: { value: UploadFileType; label: string; needsUser: boolean }[] = [
  { value: 'authorized_keys', label: '.ssh/authorized_keys', needsUser: true },
  { value: 'known_hosts',     label: '.ssh/known_hosts',     needsUser: true },
  { value: 'ssh_config',      label: '.ssh/config',          needsUser: true },
  { value: 'private_key',     label: 'SSH private key',      needsUser: true },
  { value: 'public_key',      label: 'SSH public key',       needsUser: true },
  { value: 'auth_log',        label: 'auth.log / secure',    needsUser: false },
  { value: 'wtmp',            label: 'wtmp / btmp',          needsUser: false },
  { value: 'bash_history',    label: '.bash_history',        needsUser: true },
  { value: 'passwd',          label: '/etc/passwd',          needsUser: false },
]

interface Props {
  opId: string
  hosts: Host[]
  onSuccess: () => void
}

interface ParseResults {
  result: UploadResult
  filename: string
}

export default function FileUploadForm({ opId, hosts, onSuccess }: Props) {
  const [fileType, setFileType] = useState<UploadFileType>('authorized_keys')
  const [hostId, setHostId] = useState<string>(hosts[0]?.id ?? '')
  const [username, setUsername] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<ParseResults | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const needsUser = FILE_TYPES.find(f => f.value === fileType)?.needsUser ?? false

  function handleFileDrop(f: File) {
    setFile(f)
    setError(null)
    setResults(null)
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    setDragging(true)
  }

  function handleDragLeave() {
    setDragging(false)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) handleFileDrop(dropped)
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0]
    if (picked) handleFileDrop(picked)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) { setError('Select a file to upload.'); return }
    if (!hostId) { setError('Select a host.'); return }
    if (needsUser && !username.trim()) { setError('Username is required for this file type.'); return }

    setLoading(true)
    setError(null)
    setResults(null)

    try {
      const result = await uploadFile(opId, file, fileType, hostId, needsUser ? username.trim() : undefined)
      setResults({ result, filename: file.name })
      onSuccess()
      // Reset file selection so user can upload another
      setFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'body' in err) {
        const body = (err as { body: unknown }).body
        if (body && typeof body === 'object' && 'detail' in body) {
          setError(String((body as { detail: unknown }).detail))
        } else {
          setError(String(body))
        }
      } else {
        setError(String(err))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      {/* File type */}
      <div className={styles.field}>
        <label className={styles.label}>File type</label>
        <select
          className={styles.select}
          value={fileType}
          onChange={e => { setFileType(e.target.value as UploadFileType); setResults(null) }}
        >
          {FILE_TYPES.map(ft => (
            <option key={ft.value} value={ft.value}>{ft.label}</option>
          ))}
        </select>
      </div>

      {/* Host */}
      <div className={styles.field}>
        <label className={styles.label}>Host (file came from)</label>
        <select
          className={styles.select}
          value={hostId}
          onChange={e => setHostId(e.target.value)}
        >
          {hosts.length === 0 && <option value="">— add a host first —</option>}
          {hosts.map(h => (
            <option key={h.id} value={h.id}>
              {h.nickname}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Username (conditional) */}
      {needsUser && (
        <div className={styles.field}>
          <label className={styles.label}>
            Username <span className={styles.required}>*</span>
          </label>
          <input
            className={styles.input}
            type="text"
            placeholder="e.g. root, alice"
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
        </div>
      )}

      {/* Drop zone */}
      <div
        className={`${styles.dropZone} ${dragging ? styles.dragging : ''} ${file ? styles.hasFile : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
        aria-label="Drop file here or click to browse"
      >
        <input
          ref={fileInputRef}
          type="file"
          className={styles.hiddenInput}
          onChange={handleFileInput}
          tabIndex={-1}
        />
        {file ? (
          <div className={styles.fileInfo}>
            <span className={styles.fileIcon}>📄</span>
            <span className={styles.fileName}>{file.name}</span>
            <span className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
          </div>
        ) : (
          <div className={styles.dropPrompt}>
            <span className={styles.dropIcon}>⬆</span>
            <span>Drop file here or click to browse</span>
          </div>
        )}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <button
        type="submit"
        className={styles.submitBtn}
        disabled={loading || !file || !hostId || hosts.length === 0}
      >
        {loading ? 'Parsing…' : 'Upload & Parse'}
      </button>

      {/* Results */}
      {results && <ParseResultsPanel results={results} />}
    </form>
  )
}

function ParseResultsPanel({ results: { result, filename } }: { results: ParseResults }) {
  const s = result.summary
  const hasNewData = s.new_credentials > 0 || s.new_connections > 0 || s.new_hosts > 0
  const hasPivots = result.pivot_opportunities.length > 0

  return (
    <div className={styles.results}>
      <p className={styles.resultsTitle}>
        Results for <strong>{filename}</strong>
      </p>

      {hasNewData ? (
        <ul className={styles.resultsList}>
          {s.new_credentials > 0 && (
            <li className={styles.resultsItem}>
              <span className={styles.countBadge}>{s.new_credentials}</span> new credential{s.new_credentials !== 1 ? 's' : ''}
              {s.new_credential_links > s.new_credentials && ` / ${s.new_credential_links} links`}
            </li>
          )}
          {s.new_connections > 0 && (
            <li className={styles.resultsItem}>
              <span className={styles.countBadge}>{s.new_connections}</span> connection record{s.new_connections !== 1 ? 's' : ''}
            </li>
          )}
          {s.new_hosts > 0 && (
            <li className={styles.resultsItem}>
              <span className={styles.countBadge}>{s.new_hosts}</span> new host{s.new_hosts !== 1 ? 's' : ''} (auto-created)
            </li>
          )}
        </ul>
      ) : (
        <p className={styles.noNewData}>No new data added (all records already present or file was empty).</p>
      )}

      {hasPivots && (
        <div className={styles.pivotSection}>
          <p className={styles.pivotTitle}>🔑 New pivot opportunities</p>
          {result.pivot_opportunities.map((msg, i) => (
            <p key={i} className={styles.pivotMsg}>{msg}</p>
          ))}
        </div>
      )}

      {s.warnings.length > 0 && (
        <details className={styles.warnings}>
          <summary className={styles.warningSummary}>
            {s.warnings.length} warning{s.warnings.length !== 1 ? 's' : ''}
          </summary>
          <ul className={styles.warningList}>
            {s.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
