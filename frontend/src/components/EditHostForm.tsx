/**
 * EditHostForm — pre-filled nickname/comment; IPs managed inline with
 * immediate API calls (add/remove without waiting for form submit).
 */
import { useState } from 'react'

function isValidIP(ip: string): boolean {
  if (/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)) {
    return ip.split('.').every(n => parseInt(n, 10) <= 255)
  }
  if (ip.includes(':')) {
    return /^[0-9a-fA-F:]+$/.test(ip) && ip.split(':').length <= 8
  }
  return false
}
import type { Host, HostIP, HostUser } from '../types'
import { updateHost, addHostIP, deleteHostIP, createHostUser, deleteHostUser } from '../api/hosts'
import styles from './EditModal.module.css'

const USER_SOURCES: { value: HostUser['source']; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: 'passwd_file', label: '/etc/passwd' },
  { value: 'authorized_keys', label: 'authorized_keys' },
  { value: 'log_evidence', label: 'Log evidence' },
]

interface Props {
  host: Host
  onSaved: (updated: Host) => void
  onClose: () => void
}

export default function EditHostForm({ host, onSaved, onClose }: Props) {
  const [nickname, setNickname] = useState(host.nickname)
  const [comment, setComment] = useState(host.comment ?? '')
  const [ips, setIps] = useState<HostIP[]>(host.ips)
  const [users, setUsers] = useState<HostUser[]>(host.users)
  const [newIp, setNewIp] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newShell, setNewShell] = useState('')
  const [newUserSource, setNewUserSource] = useState<HostUser['source']>('manual')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [ipLoading, setIpLoading] = useState(false)
  const [userLoading, setUserLoading] = useState(false)

  async function handleAddIp() {
    const trimmed = newIp.trim()
    if (!trimmed) return
    if (!isValidIP(trimmed)) {
      setError(`"${trimmed}" is not a valid IP address`)
      return
    }
    setIpLoading(true)
    setError(null)
    try {
      const created = await addHostIP(host.id, { ip_address: trimmed })
      setIps(prev => [...prev, created])
      setNewIp('')
    } catch {
      setError('Failed to add IP.')
    } finally {
      setIpLoading(false)
    }
  }

  async function handleRemoveIp(ip: HostIP) {
    if (ips.length <= 1) {
      setError('A host must have at least one IP address.')
      return
    }
    setIpLoading(true)
    setError(null)
    try {
      await deleteHostIP(host.id, ip.id)
      setIps(prev => prev.filter(i => i.id !== ip.id))
    } catch {
      setError('Failed to remove IP.')
    } finally {
      setIpLoading(false)
    }
  }

  async function handleAddUser() {
    const trimmed = newUsername.trim()
    if (!trimmed) return
    setUserLoading(true)
    setError(null)
    try {
      const created = await createHostUser(host.id, {
        username: trimmed,
        shell: newShell.trim() || null,
        source: newUserSource,
      })
      setUsers(prev => [...prev, created])
      setNewUsername('')
      setNewShell('')
      setNewUserSource('manual')
    } catch {
      setError('Failed to add user.')
    } finally {
      setUserLoading(false)
    }
  }

  async function handleRemoveUser(u: HostUser) {
    setUserLoading(true)
    setError(null)
    try {
      await deleteHostUser(host.id, u.id)
      setUsers(prev => prev.filter(x => x.id !== u.id))
    } catch {
      setError('Failed to remove user.')
    } finally {
      setUserLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!nickname.trim()) {
      setError('Nickname is required.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const updated = await updateHost(host.id, {
        nickname: nickname.trim(),
        comment: comment.trim() || null,
      })
      onSaved({ ...updated, ips, users })
    } catch {
      setError('Failed to save changes.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.field}>
        <label>Nickname *</label>
        <input
          type="text"
          value={nickname}
          onChange={e => setNickname(e.target.value)}
          autoFocus
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label>Comment</label>
        <input
          type="text"
          value={comment}
          onChange={e => setComment(e.target.value)}
          placeholder="Optional notes"
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label>IP Addresses</label>
        <div className={styles.ipList}>
          {ips.map(ip => (
            <div key={ip.id} className={styles.ipRow}>
              <span className={styles.ipRowInput}>
                <input
                  type="text"
                  value={ip.ip_address}
                  readOnly
                  disabled
                />
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: '.8em', flexShrink: 0 }}>
                {ip.addr_type}
              </span>
              <button
                type="button"
                className={styles.removeBtn}
                onClick={() => handleRemoveIp(ip)}
                disabled={ipLoading || loading}
                aria-label={`Remove ${ip.ip_address}`}
              >
                ✕
              </button>
            </div>
          ))}
          <div className={styles.ipRow}>
            <span className={styles.ipRowInput}>
              <input
                type="text"
                value={newIp}
                onChange={e => setNewIp(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddIp() } }}
                placeholder="Add IP address…"
                disabled={ipLoading || loading}
              />
            </span>
            <button
              type="button"
              className={styles.addRowBtn}
              onClick={handleAddIp}
              disabled={ipLoading || loading || !newIp.trim()}
            >
              Add
            </button>
          </div>
        </div>
      </div>

      <div className={styles.field}>
        <label>Known Users</label>
        <div className={styles.ipList}>
          {users.map(u => (
            <div key={u.id} className={styles.ipRow}>
              <span className={styles.ipRowInput}>
                <input
                  type="text"
                  value={`${u.username}${u.shell ? '  ·  ' + u.shell : ''}  [${u.source}]`}
                  readOnly
                  disabled
                />
              </span>
              <button
                type="button"
                className={styles.removeBtn}
                onClick={() => handleRemoveUser(u)}
                disabled={userLoading || loading}
                aria-label={`Remove ${u.username}`}
              >
                ✕
              </button>
            </div>
          ))}
          <div className={styles.ipRow}>
            <span className={styles.ipRowInput}>
              <input
                type="text"
                value={newUsername}
                onChange={e => setNewUsername(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddUser() } }}
                placeholder="username…"
                disabled={userLoading || loading}
              />
            </span>
            <span className={styles.ipRowInput}>
              <input
                type="text"
                value={newShell}
                onChange={e => setNewShell(e.target.value)}
                placeholder="shell (opt)"
                disabled={userLoading || loading}
              />
            </span>
            <select
              value={newUserSource}
              onChange={e => setNewUserSource(e.target.value as HostUser['source'])}
              disabled={userLoading || loading}
              style={{ flex: '1', minWidth: 0 }}
            >
              {USER_SOURCES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
            <button
              type="button"
              className={styles.addRowBtn}
              onClick={handleAddUser}
              disabled={userLoading || loading || !newUsername.trim()}
            >
              Add
            </button>
          </div>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>
          Cancel
        </button>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? 'Saving…' : 'Save Changes'}
        </button>
      </div>
    </form>
  )
}
