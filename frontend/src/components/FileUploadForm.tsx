/**
 * FileUploadForm — multi-file upload queue with auto-detect and sequential processing.
 * Renders inside the AddDataModal "File Upload" tab.
 */
import { useRef, useState } from 'react'
import type { Host, UploadFileType, UploadResult } from '../types'
import { uploadFile } from '../api/upload'
import { detectFileType } from '../utils/detectFileType'
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
  { value: 'shadow',          label: '/etc/shadow',          needsUser: false },
  { value: 'sshd_config',     label: '/etc/ssh/sshd_config', needsUser: false },
  { value: 'etc_hosts',       label: '/etc/hosts',           needsUser: false },
  { value: 'sudoers',         label: '/etc/sudoers',         needsUser: false },
  { value: 'nmap_xml',        label: 'nmap XML scan',        needsUser: false },
]

type FileStatus = 'pending' | 'uploading' | 'done' | 'error'

interface QueuedFile {
  id: string
  file: File
  fileType: UploadFileType | null  // null = not yet selected
  username: string
  status: FileStatus
  result: UploadResult | null
  error: string | null
  autoDetected: boolean
}

interface Props {
  opId: string
  hosts: Host[]
  onSuccess: () => void
}

let _nextId = 0
function newId() { return String(++_nextId) }

function needsUser(ft: UploadFileType | null): boolean {
  return FILE_TYPES.find(f => f.value === ft)?.needsUser ?? false
}

export default function FileUploadForm({ opId, hosts, onSuccess }: Props) {
  const [hostId, setHostId] = useState<string>('')
  const [queue, setQueue] = useState<QueuedFile[]>([])
  const [dragging, setDragging] = useState(false)
  const [processing, setProcessing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files)
    setQueue(prev => [
      ...prev,
      ...arr.map(f => {
        const detected = detectFileType(f.name)
        return {
          id: newId(),
          file: f,
          fileType: detected,
          username: '',
          status: 'pending' as FileStatus,
          result: null,
          error: null,
          autoDetected: detected !== null,
        }
      }),
    ])
  }

  function removeQueued(id: string) {
    setQueue(prev => prev.filter(q => q.id !== id))
  }

  function setQueuedType(id: string, ft: UploadFileType) {
    setQueue(prev => prev.map(q => q.id === id ? { ...q, fileType: ft } : q))
  }

  function setQueuedUsername(id: string, username: string) {
    setQueue(prev => prev.map(q => q.id === id ? { ...q, username } : q))
  }

  function handleDragOver(e: React.DragEvent) { e.preventDefault(); setDragging(true) }
  function handleDragLeave() { setDragging(false) }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
  }
  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) {
      addFiles(e.target.files)
      e.target.value = ''
    }
  }

  async function processOne(item: QueuedFile): Promise<void> {
    if (!item.fileType) return  // shouldn't happen — button disabled

    setQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'uploading', error: null } : q))

    try {
      const usernameArg = needsUser(item.fileType) && item.username.trim() ? item.username.trim() : undefined
      const result = await uploadFile(opId, item.file, item.fileType, hostId, usernameArg)
      setQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'done', result } : q))
    } catch (err: unknown) {
      let msg = 'Upload failed.'
      if (err && typeof err === 'object') {
        const body = ('body' in err) ? (err as { body: unknown }).body : null
        if (body && typeof body === 'object' && 'detail' in body) {
          msg = String((body as { detail: unknown }).detail)
        } else if (body) {
          msg = String(body)
        } else if ('message' in err) {
          msg = String((err as { message: unknown }).message)
        }
      }
      setQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'error', error: msg } : q))
    }
  }

  async function handleUploadAll(e: React.FormEvent) {
    e.preventDefault()
    if (!hostId || processing) return
    const pending = queue.filter(q => q.status === 'pending' && q.fileType !== null)
    if (!pending.length) return

    setProcessing(true)
    for (const item of pending) {
      await processOne(item)
    }
    setProcessing(false)
    onSuccess()
  }

  async function handleRetry(item: QueuedFile) {
    setQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'pending', error: null } : q))
    setProcessing(true)
    await processOne({ ...item, status: 'pending', error: null })
    setProcessing(false)
    onSuccess()
  }

  const pendingCount = queue.filter(q => q.status === 'pending' && q.fileType !== null).length
  const allNeedType = queue.some(q => q.status === 'pending' && q.fileType === null)

  return (
    <form className={styles.form} onSubmit={handleUploadAll}>
      {/* Host */}
      <div className={styles.field}>
        <label className={styles.label}>
          Which host did these files come from? <span className={styles.required}>*</span>
        </label>
        <select
          className={`${styles.select} ${!hostId ? styles.selectUnset : ''}`}
          value={hostId}
          onChange={e => setHostId(e.target.value)}
        >
          <option value="" disabled>
            {hosts.length === 0 ? '— add a host first —' : '— select host —'}
          </option>
          {hosts.map(h => (
            <option key={h.id} value={h.id}>
              {h.nickname}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div
        className={`${styles.dropZone} ${dragging ? styles.dragging : ''} ${queue.length > 0 ? styles.hasFile : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
        aria-label="Drop files here or click to browse"
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className={styles.hiddenInput}
          onChange={handleFileInput}
          tabIndex={-1}
        />
        <div className={styles.dropPrompt}>
          <span className={styles.dropIcon}>⬆</span>
          <span>{queue.length > 0 ? 'Drop more files or click to add' : 'Drop files here or click to browse'}</span>
        </div>
      </div>

      {/* File queue */}
      {queue.length > 0 && (
        <div className={styles.queue}>
          {queue.map(item => (
            <QueueItem
              key={item.id}
              item={item}
              onRemove={() => removeQueued(item.id)}
              onTypeChange={ft => setQueuedType(item.id, ft)}
              onUsernameChange={u => setQueuedUsername(item.id, u)}
              onRetry={() => handleRetry(item)}
            />
          ))}
        </div>
      )}

      {/* Validation hints */}
      {allNeedType && queue.some(q => q.status === 'pending') && (
        <p className={styles.hint}>Select a file type for all files before uploading.</p>
      )}

      {/* Submit */}
      {queue.some(q => q.status === 'pending') && (
        <button
          type="submit"
          className={styles.submitBtn}
          disabled={processing || !hostId || hosts.length === 0 || pendingCount === 0}
        >
          {processing ? 'Processing…' : `Upload ${pendingCount} file${pendingCount !== 1 ? 's' : ''}`}
        </button>
      )}
    </form>
  )
}

// ─── Queue item row ───────────────────────────────────────────────────────────

interface QueueItemProps {
  item: QueuedFile
  onRemove: () => void
  onTypeChange: (ft: UploadFileType) => void
  onUsernameChange: (username: string) => void
  onRetry: () => void
}

function QueueItem({ item, onRemove, onTypeChange, onUsernameChange, onRetry }: QueueItemProps) {
  const s = item.result?.summary
  return (
    <div className={`${styles.queueItem} ${styles[`status_${item.status}`]}`}>
      <div className={styles.queueItemHeader}>
        <span className={styles.queueFileName}>{item.file.name}</span>
        <span className={styles.queueFileSize}>{(item.file.size / 1024).toFixed(1)} KB</span>

        {item.status === 'pending' && (
          <select
            className={styles.queueTypeSelect}
            value={item.fileType ?? ''}
            onChange={e => onTypeChange(e.target.value as UploadFileType)}
            onClick={e => e.stopPropagation()}
          >
            {!item.fileType && <option value="">— select type —</option>}
            {FILE_TYPES.map(ft => (
              <option key={ft.value} value={ft.value}>{ft.label}</option>
            ))}
          </select>
        )}

        {item.autoDetected && item.status === 'pending' && (
          <span className={styles.autoTag}>auto</span>
        )}


        <span className={styles.queueStatus}>
          {item.status === 'uploading' && '⟳'}
          {item.status === 'done' && '✓'}
          {item.status === 'error' && '✕'}
        </span>

        {item.status === 'error' && (
          <button className={styles.retryBtn} onClick={onRetry} type="button">Retry</button>
        )}
        {item.status === 'pending' && (
          <button className={styles.removeBtn} onClick={onRemove} type="button" aria-label="Remove">✕</button>
        )}
      </div>

      {item.status === 'pending' && needsUser(item.fileType) && (
        <input
          className={styles.queueUsernameInput}
          type="text"
          placeholder="Username (e.g. root, alice)"
          value={item.username}
          onChange={e => onUsernameChange(e.target.value)}
          onClick={e => e.stopPropagation()}
        />
      )}

      {item.status === 'error' && item.error && (
        <p className={styles.queueError}>{item.error}</p>
      )}

      {item.status === 'done' && s && (
        <p className={styles.queueSummary}>
          {[
            s.new_credentials > 0 && `${s.new_credentials} cred${s.new_credentials !== 1 ? 's' : ''}`,
            s.new_connections > 0 && `${s.new_connections} conn${s.new_connections !== 1 ? 's' : ''}`,
            s.new_hosts > 0 && `${s.new_hosts} host${s.new_hosts !== 1 ? 's' : ''}`,
          ].filter(Boolean).join(' · ') || 'No new data'}
        </p>
      )}
    </div>
  )
}
