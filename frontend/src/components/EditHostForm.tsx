/**
 * EditHostForm — pre-filled nickname/comment; IPs managed inline with
 * immediate API calls (add/remove without waiting for form submit).
 */
import { useState } from 'react'
import type { Host, HostIP } from '../types'
import { updateHost, addHostIP, deleteHostIP } from '../api/hosts'
import styles from './EditModal.module.css'

interface Props {
  host: Host
  onSaved: (updated: Host) => void
  onClose: () => void
}

export default function EditHostForm({ host, onSaved, onClose }: Props) {
  const [nickname, setNickname] = useState(host.nickname)
  const [comment, setComment] = useState(host.comment ?? '')
  const [ips, setIps] = useState<HostIP[]>(host.ips)
  const [newIp, setNewIp] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [ipLoading, setIpLoading] = useState(false)

  async function handleAddIp() {
    const trimmed = newIp.trim()
    if (!trimmed) return
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
      onSaved({ ...updated, ips })
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
