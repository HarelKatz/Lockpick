/**
 * EditConnectionForm — same src/dst grid layout as ConnectionForm, pre-filled.
 */
import { useState } from 'react'
import type { AuthMethod, ConnectionRecord, Credential, Host } from '../types'

function credLabel(c: Credential): string {
  if (c.name) return c.name
  if (c.cred_type === 'password') return c.comment ? `[password] (${c.comment})` : '[password]'
  const parts: string[] = [c.key_type ?? 'key']
  if (c.fingerprint) parts.push(c.fingerprint.slice(7, 19) + '…')
  if (c.comment) parts.push(`(${c.comment})`)
  return parts.join(' ')
}
import { updateConnection } from '../api/connections'
import styles from './EditModal.module.css'

interface Props {
  connection: ConnectionRecord
  hosts: Host[]
  credentials: Credential[]
  onSaved: (updated: ConnectionRecord) => void
  onClose: () => void
}

const CONN_TYPES: { value: ConnectionRecord['connection_type']; label: string }[] = [
  { value: 'ssh', label: 'SSH' },
  { value: 'scp', label: 'SCP' },
  { value: 'rsync', label: 'rsync' },
  { value: 'sftp', label: 'SFTP' },
  { value: 'ssh_copy_id', label: 'ssh-copy-id' },
  { value: 'unknown', label: 'Unknown' },
]

const AUTH_METHODS: { value: AuthMethod; label: string }[] = [
  { value: 'publickey', label: 'Public key' },
  { value: 'password', label: 'Password' },
  { value: 'keyboard-interactive', label: 'Keyboard-interactive' },
  { value: 'hostbased', label: 'Host-based' },
  { value: 'unknown', label: 'Unknown' },
]

export default function EditConnectionForm({ connection, hosts, credentials, onSaved, onClose }: Props) {
  const [srcHostId, setSrcHostId] = useState(connection.src_host_id ?? '')
  const [srcIp, setSrcIp] = useState(connection.src_ip)
  const [srcUser, setSrcUser] = useState(connection.src_user ?? '')
  const [dstHostId, setDstHostId] = useState(connection.dst_host_id ?? '')
  const [dstIp, setDstIp] = useState(connection.dst_ip)
  const [dstUser, setDstUser] = useState(connection.dst_user ?? '')
  const [connType, setConnType] = useState(connection.connection_type)
  const [direction, setDirection] = useState(connection.direction_context)
  const [authMethod, setAuthMethod] = useState<AuthMethod | ''>(connection.auth_method ?? '')
  const [credentialId, setCredentialId] = useState(connection.credential_id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const linkedCredType = authMethod === 'publickey' ? 'private_key' : authMethod === 'password' ? 'password' : null
  const linkedCreds = linkedCredType ? credentials.filter(c => c.cred_type === linkedCredType) : []

  function handleSrcHostChange(id: string) {
    setSrcHostId(id)
    if (id) {
      const h = hosts.find(h => h.id === id)
      if (h?.ips[0]) setSrcIp(h.ips[0].ip_address)
    }
  }

  function handleDstHostChange(id: string) {
    setDstHostId(id)
    if (id) {
      const h = hosts.find(h => h.id === id)
      if (h?.ips[0]) setDstIp(h.ips[0].ip_address)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!srcIp.trim()) { setError('Source IP is required.'); return }
    if (!dstIp.trim()) { setError('Destination IP is required.'); return }
    setError(null)
    setLoading(true)
    try {
      const updated = await updateConnection(connection.id, {
        src_host_id: srcHostId || null,
        src_ip: srcIp.trim(),
        src_user: srcUser.trim() || null,
        dst_host_id: dstHostId || null,
        dst_ip: dstIp.trim(),
        dst_user: dstUser.trim() || null,
        connection_type: connType,
        direction_context: direction,
        auth_method: authMethod || null,
        credential_id: credentialId || null,
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
      <div className={styles.connGrid}>
        <div className={styles.connSide}>
          <p className={styles.connSideLabel}>Source</p>
          <div className={styles.field}>
            <label>Host</label>
            <select value={srcHostId} onChange={e => handleSrcHostChange(e.target.value)} disabled={loading}>
              <option value="">— unknown —</option>
              {hosts.map(h => (
                <option key={h.id} value={h.id}>
                  {h.nickname}{h.ips[0] ? ` (${h.ips[0].ip_address})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label>IP Address *</label>
            <input type="text" value={srcIp} onChange={e => setSrcIp(e.target.value)} disabled={loading} />
          </div>
          <div className={styles.field}>
            <label>Username</label>
            <input type="text" value={srcUser} onChange={e => setSrcUser(e.target.value)} placeholder="bob" disabled={loading} />
          </div>
        </div>

        <div className={styles.connArrow}>→</div>

        <div className={styles.connSide}>
          <p className={styles.connSideLabel}>Destination</p>
          <div className={styles.field}>
            <label>Host</label>
            <select value={dstHostId} onChange={e => handleDstHostChange(e.target.value)} disabled={loading}>
              <option value="">— unknown —</option>
              {hosts.map(h => (
                <option key={h.id} value={h.id}>
                  {h.nickname}{h.ips[0] ? ` (${h.ips[0].ip_address})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label>IP Address *</label>
            <input type="text" value={dstIp} onChange={e => setDstIp(e.target.value)} disabled={loading} />
          </div>
          <div className={styles.field}>
            <label>Username</label>
            <input type="text" value={dstUser} onChange={e => setDstUser(e.target.value)} placeholder="root" disabled={loading} />
          </div>
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label>Connection Type</label>
          <select value={connType} onChange={e => setConnType(e.target.value as ConnectionRecord['connection_type'])} disabled={loading}>
            {CONN_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div className={styles.field}>
          <label>Evidence Source</label>
          <select value={direction} onChange={e => setDirection(e.target.value as ConnectionRecord['direction_context'])} disabled={loading}>
            <option value="from_src_logs">From source's logs / bash_history</option>
            <option value="from_dst_logs">From destination's logs (auth.log)</option>
          </select>
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label>Auth Method</label>
          <select value={authMethod} onChange={e => { setAuthMethod(e.target.value as AuthMethod | ''); setCredentialId('') }} disabled={loading}>
            <option value="">— unknown / not recorded —</option>
            {AUTH_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
        {linkedCredType && (
          <div className={styles.field}>
            <label>{authMethod === 'publickey' ? 'Private Key Used' : 'Password Used'}</label>
            <select value={credentialId} onChange={e => setCredentialId(e.target.value)} disabled={loading}>
              <option value="">— none / unknown —</option>
              {linkedCreds.map(c => (
                <option key={c.id} value={c.id}>{credLabel(c)}</option>
              ))}
            </select>
          </div>
        )}
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
