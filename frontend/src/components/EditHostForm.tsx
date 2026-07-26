/**
 * EditHostForm — pre-filled nickname/comment; IPs managed inline with
 * immediate API calls (add/remove without waiting for form submit).
 */
import { useRef, useState } from 'react'
import { statusColors, STATUS_LABELS } from '../theme'

type AddrType = 'ipv4' | 'ipv6' | 'hostname'

function isValidIP(ip: string, addrType: AddrType): boolean {
  if (addrType === 'hostname') return ip.trim().length > 0
  if (addrType === 'ipv6' || ip.includes(':')) {
    return /^[0-9a-fA-F:]+$/.test(ip) && ip.split(':').length <= 8
  }
  if (/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)) {
    return ip.split('.').every(n => parseInt(n, 10) <= 255)
  }
  return false
}
import type { Host, HostIP, HostUser } from '../types'
import { createHost, updateHost, addHostIP, deleteHostIP, createHostUser, deleteHostUser } from '../api/hosts'
import styles from './EditModal.module.css'

const USER_SOURCES: { value: HostUser['source']; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: 'passwd_file', label: '/etc/passwd' },
  { value: 'authorized_keys', label: 'authorized_keys' },
  { value: 'log_evidence', label: 'Log evidence' },
]

interface Props {
  /** Existing host to edit. When absent, form is in create mode. */
  host?: Host
  /** Required in create mode — the operation to create the host in. */
  opId?: string
  onSaved: (updated: Host) => void
  onClose: () => void
}

export default function EditHostForm({ host, opId, onSaved, onClose }: Props) {
  const isCreate = !host

  const [nickname, setNickname] = useState(host?.nickname ?? '')
  const [comment, setComment] = useState(host?.comment ?? '')
  const [formStatus, setFormStatus] = useState(host?.status ?? '')
  const [osVersion, setOsVersion] = useState(host?.os_version ?? '')
  const [kernelVersion, setKernelVersion] = useState(host?.kernel_version ?? '')
  const [ips, setIps] = useState<HostIP[]>(host?.ips ?? [])
  const [pendingIps, setPendingIps] = useState<{ ip_address: string; addr_type: AddrType }[]>([])
  const [users, setUsers] = useState<HostUser[]>(host?.users ?? [])
  const [newIp, setNewIp] = useState('')
  const [addrType, setAddrType] = useState<AddrType>('ipv4')
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
    if (!isValidIP(trimmed, addrType)) {
      const label = addrType === 'hostname' ? 'hostname' : 'IP address'
      setError(`"${trimmed}" is not a valid ${label}`)
      return
    }
    setError(null)
    if (isCreate) {
      setPendingIps(prev => [...prev, { ip_address: trimmed, addr_type: addrType }])
      setNewIp('')
      return
    }
    setIpLoading(true)
    try {
      const created = await addHostIP(host!.id, { ip_address: trimmed, addr_type: addrType })
      setIps(prev => [...prev, created])
      setNewIp('')
    } catch {
      setError('Failed to add IP.')
    } finally {
      setIpLoading(false)
    }
  }

  async function handleRemoveIp(ip: HostIP) {
    if (ips.length <= 1 && pendingIps.length === 0) {
      setError('A host must have at least one address.')
      return
    }
    setIpLoading(true)
    setError(null)
    try {
      await deleteHostIP(host!.id, ip.id)
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
      const created = await createHostUser(host!.id, {
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
      await deleteHostUser(host!.id, u.id)
      setUsers(prev => prev.filter(x => x.id !== u.id))
    } catch {
      setError('Failed to remove user.')
    } finally {
      setUserLoading(false)
    }
  }

  const submittingRef = useRef(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submittingRef.current) return
    if (!nickname.trim()) {
      setError('Nickname is required.')
      return
    }
    submittingRef.current = true
    setError(null)
    setLoading(true)
    try {
      if (isCreate) {
        const newHost = await createHost(opId!, {
          nickname: nickname.trim(),
          comment: comment.trim() || null,
          os_version: osVersion.trim() || null,
          kernel_version: kernelVersion.trim() || null,
        })
        // Add any buffered IPs
        const addedIps: HostIP[] = []
        for (const ip of pendingIps) {
          try {
            const created = await addHostIP(newHost.id, ip)
            addedIps.push(created)
          } catch { /* ignore per-IP failures */ }
        }
        onSaved({ ...newHost, ips: addedIps, users: [], notes: [] })
      } else {
        const updated = await updateHost(host!.id, {
          nickname: nickname.trim(),
          comment: comment.trim() || null,
          status: formStatus || null,
          os_version: osVersion.trim() || null,
          kernel_version: kernelVersion.trim() || null,
        })
        onSaved({ ...updated, ips, users })
      }
    } catch {
      setError(isCreate ? 'Failed to create host.' : 'Failed to save changes.')
    } finally {
      submittingRef.current = false
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
        <label>Status</label>
        <select
          value={formStatus}
          onChange={e => setFormStatus(e.target.value)}
          disabled={loading}
          style={{ width: '100%' }}
        >
          <option value="">— unset —</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value} style={{ color: statusColors[value] }}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label>OS Version</label>
        <input
          type="text"
          value={osVersion}
          onChange={e => setOsVersion(e.target.value)}
          placeholder="e.g. Ubuntu 22.04.3 LTS"
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label>Kernel Version</label>
        <input
          type="text"
          value={kernelVersion}
          onChange={e => setKernelVersion(e.target.value)}
          placeholder="e.g. 5.15.0-88-generic"
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label>IPs / Hostnames</label>
        <div className={styles.ipList}>
          {ips.map(ip => (
            <div key={ip.id} className={styles.ipRow}>
              <span className={styles.ipRowInput}>
                <input type="text" value={ip.ip_address} readOnly disabled />
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
          {pendingIps.map((ip, i) => (
            <div key={i} className={styles.ipRow}>
              <span className={styles.ipRowInput}>
                <input type="text" value={ip.ip_address} readOnly disabled />
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: '.8em', flexShrink: 0 }}>
                {ip.addr_type} (pending)
              </span>
              <button
                type="button"
                className={styles.removeBtn}
                onClick={() => setPendingIps(prev => prev.filter((_, j) => j !== i))}
                disabled={loading}
              >
                ✕
              </button>
            </div>
          ))}
          <div className={styles.ipRow}>
            <select
              value={addrType}
              onChange={e => setAddrType(e.target.value as AddrType)}
              disabled={ipLoading || loading}
              style={{ flex: '0 0 auto' }}
            >
              <option value="ipv4">IPv4</option>
              <option value="ipv6">IPv6</option>
              <option value="hostname">Hostname</option>
            </select>
            <span className={styles.ipRowInput}>
              <input
                type="text"
                value={newIp}
                onChange={e => setNewIp(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAddIp() } }}
                placeholder={addrType === 'hostname' ? 'Add hostname…' : 'Add IP address…'}
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

      {!isCreate && <div className={styles.field}>
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
      </div>}

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={loading}>
          Cancel
        </button>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? (isCreate ? 'Creating…' : 'Saving…') : (isCreate ? 'Create Host' : 'Save Changes')}
        </button>
      </div>
    </form>
  )
}
