/**
 * EditCredentialForm — edits value, passphrase, comment.
 * cred_type is read-only. Shows a hint when value is changed
 * that fingerprint will be re-inferred.
 */
import { useState } from 'react'
import type { Credential } from '../types'
import { updateCredential } from '../api/credentials'
import styles from './EditModal.module.css'

interface Props {
  credential: Credential
  onSaved: (updated: Credential) => void
  onClose: () => void
}

const CRED_TYPE_LABELS: Record<Credential['cred_type'], string> = {
  private_key: 'Private Key (SSH)',
  public_key: 'Public Key (SSH)',
  password: 'Password',
}

export default function EditCredentialForm({ credential, onSaved, onClose }: Props) {
  const [value, setValue] = useState(credential.value)
  const [passphrase, setPassphrase] = useState(credential.passphrase ?? '')
  const [comment, setComment] = useState(credential.comment ?? '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const valueChanged = value !== credential.value

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!value.trim()) {
      setError('Value is required.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const updated = await updateCredential(credential.id, {
        value: value !== credential.value ? value : undefined,
        passphrase: passphrase !== (credential.passphrase ?? '') ? (passphrase || null) : undefined,
        comment: comment !== (credential.comment ?? '') ? (comment || null) : undefined,
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
      <div className={styles.field}>
        <label>Type</label>
        <div className={styles.fieldReadOnly}>{CRED_TYPE_LABELS[credential.cred_type]}</div>
      </div>

      <div className={styles.field}>
        <label>Value *</label>
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          rows={credential.cred_type !== 'password' ? 6 : 2}
          className={styles.codeArea}
          autoFocus
          disabled={loading}
        />
        {valueChanged && (
          <span className={styles.fieldHint}>Fingerprint will be re-inferred on save.</span>
        )}
      </div>

      {credential.cred_type === 'private_key' && (
        <div className={styles.field}>
          <label>Passphrase</label>
          <input
            type="password"
            value={passphrase}
            onChange={e => setPassphrase(e.target.value)}
            placeholder="Leave blank if unencrypted"
            disabled={loading}
          />
        </div>
      )}

      <div className={styles.field}>
        <label>Comment</label>
        <input
          type="text"
          value={comment}
          onChange={e => setComment(e.target.value)}
          placeholder="Optional note"
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
