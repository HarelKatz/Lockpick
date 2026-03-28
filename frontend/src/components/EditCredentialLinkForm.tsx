/**
 * EditCredentialLinkForm — username, relationship_type, file_source editable;
 * credential and host shown read-only.
 */
import { useState } from 'react'
import type { Credential, CredentialLink, Host } from '../types'
import { updateCredentialLink } from '../api/credentials'
import styles from './EditModal.module.css'

interface Props {
  link: CredentialLink
  credential: Credential
  host: Host | undefined
  onSaved: (updated: CredentialLink) => void
  onClose: () => void
}

const RELATIONSHIP_TYPES: { value: CredentialLink['relationship_type']; label: string }[] = [
  { value: 'found_on_disk', label: 'Found on disk' },
  { value: 'authorized_key', label: 'Authorized key (grants access)' },
  { value: 'accepted_password', label: 'Accepted password' },
  { value: 'used_in_connection', label: 'Used in connection' },
]

export default function EditCredentialLinkForm({ link, credential, host, onSaved, onClose }: Props) {
  const [username, setUsername] = useState(link.username ?? '')
  const [relationship, setRelationship] = useState(link.relationship_type)
  const [fileSource, setFileSource] = useState(link.file_source ?? '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const updated = await updateCredentialLink(link.id, {
        username: username || null,
        relationship_type: relationship,
        file_source: fileSource || null,
      })
      onSaved(updated)
    } catch {
      setError('Failed to save changes.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.row}>
        <div className={styles.field}>
          <label>Credential</label>
          <div className={styles.fieldReadOnly}>
            {credential.cred_type}{credential.fingerprint ? ` · ${credential.fingerprint.slice(0, 20)}…` : ''}
          </div>
        </div>
        <div className={styles.field}>
          <label>Host</label>
          <div className={styles.fieldReadOnly}>{host?.nickname ?? link.host_id}</div>
        </div>
      </div>

      <div className={styles.field}>
        <label>Username</label>
        <input
          type="text"
          value={username}
          onChange={e => setUsername(e.target.value)}
          placeholder="e.g. root, bob"
          autoFocus
          disabled={loading}
        />
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
