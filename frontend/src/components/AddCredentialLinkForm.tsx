/**
 * AddCredentialLinkForm — inline form for attaching an existing credential
 * to a host. Rendered directly inside the credential card (no modal).
 */
import { useRef, useState } from 'react'
import type { CredentialLink, Host } from '../types'
import { createCredentialLink } from '../api/credentials'
import { RELATIONSHIP_TYPES } from '../constants/credentialLink'
import styles from './EditModal.module.css'

interface Props {
  credentialId: string
  hosts: Host[]
  onAdded: (link: CredentialLink) => void
  onCancel: () => void
}

export default function AddCredentialLinkForm({ credentialId, hosts, onAdded, onCancel }: Props) {
  const [hostId, setHostId] = useState('')
  const [username, setUsername] = useState('')
  const [relationship, setRelationship] = useState<CredentialLink['relationship_type']>('found_on_disk')
  const [fileSource, setFileSource] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // Synchronous guard against rapid double-submits — React's setLoading is
  // async, so the button's `disabled` flag isn't reliable between clicks
  // fired in the same tick.
  const submittingRef = useRef(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submittingRef.current) return
    if (!hostId) {
      setError('Select a host.')
      return
    }
    submittingRef.current = true
    setError(null)
    setLoading(true)
    try {
      const created = await createCredentialLink({
        credential_id: credentialId,
        host_id: hostId,
        username: username.trim() || null,
        relationship_type: relationship,
        file_source: fileSource.trim() || null,
      })
      onAdded(created)
    } catch {
      setError('Failed to add link.')
    } finally {
      submittingRef.current = false
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.row}>
        <div className={styles.field}>
          <label>Host *</label>
          <select
            value={hostId}
            onChange={e => setHostId(e.target.value)}
            disabled={loading}
          >
            <option value="">— select a host —</option>
            {hosts.map(h => {
              const label = h.nickname.length > 60 ? h.nickname.slice(0, 60) + '…' : h.nickname
              return (
                <option key={h.id} value={h.id}>
                  {label}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
                </option>
              )
            })}
          </select>
        </div>
        <div className={styles.field}>
          <label>Username</label>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="e.g. root, bob"
            disabled={loading}
          />
        </div>
      </div>

      <div className={styles.field}>
        <label>Relationship *</label>
        <select
          value={relationship}
          onChange={e => setRelationship(e.target.value as CredentialLink['relationship_type'])}
          disabled={loading}
        >
          {RELATIONSHIP_TYPES.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label>File Source</label>
        <input
          type="text"
          value={fileSource}
          onChange={e => setFileSource(e.target.value)}
          placeholder="e.g. /home/bob/.ssh/id_rsa"
          disabled={loading}
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button type="button" className={styles.btnSecondary} onClick={onCancel} disabled={loading}>
          Cancel
        </button>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? 'Adding…' : 'Add Link'}
        </button>
      </div>
    </form>
  )
}
