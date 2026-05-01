/**
 * ManualEntryForm — three sub-forms for adding data manually.
 * Sub-forms: Host | Credential | Connection
 */
import { useRef, useState, useCallback } from 'react'

function isValidAddress(ip: string, addrType: 'ipv4' | 'ipv6' | 'hostname'): boolean {
  if (addrType === 'hostname') return ip.trim().length > 0
  if (/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)) {
    return ip.split('.').every(n => parseInt(n, 10) <= 255)
  }
  if (ip.includes(':')) {
    return /^[0-9a-fA-F:]+$/.test(ip) && ip.split(':').length <= 8
  }
  return false
}
import type {
  Host,
  Credential,
  CreateCredentialRequest,
  CreateCredentialLinkRequest,
  CreateConnectionRequest,
  CreateHostUserRequest,
  AuthMethod,
} from '../types'
import { createHost, addHostIP, createHostUser } from '../api/hosts'
import { createCredential, createCredentialLink } from '../api/credentials'
import { createConnection } from '../api/connections'
import { RELATIONSHIP_TYPES } from '../constants/credentialLink'
import styles from './ManualEntryForm.module.css'

type FormType = 'host' | 'credential' | 'connection'

interface Props {
  opId: string
  hosts: Host[]
  credentials: Credential[]
  onSuccess: () => void
}

// ─── Host form ────────────────────────────────────────────────────────────────

interface IPEntry {
  ip_address: string
  addr_type: 'ipv4' | 'ipv6' | 'hostname'
}

interface UserEntry {
  username: string
  shell: string
  source: CreateHostUserRequest['source']
}

const USER_SOURCES: { value: CreateHostUserRequest['source']; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: 'passwd_file', label: '/etc/passwd' },
  { value: 'authorized_keys', label: 'authorized_keys' },
  { value: 'log_evidence', label: 'Log evidence' },
]

function HostForm({ opId, onSuccess }: { opId: string; onSuccess: () => void }) {
  const [nickname, setNickname] = useState('')
  const [comment, setComment] = useState('')
  const [ips, setIps] = useState<IPEntry[]>([{ ip_address: '', addr_type: 'ipv4' }])
  const [users, setUsers] = useState<UserEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function addIpRow() {
    setIps(prev => [...prev, { ip_address: '', addr_type: 'ipv4' }])
  }

  function removeIpRow(idx: number) {
    setIps(prev => prev.filter((_, i) => i !== idx))
  }

  function updateIp(idx: number, value: string) {
    setIps(prev => prev.map((row, i) => i === idx ? { ...row, ip_address: value } : row))
  }

  function updateAddrType(idx: number, value: IPEntry['addr_type']) {
    setIps(prev => prev.map((row, i) => i === idx ? { ...row, addr_type: value } : row))
  }

  function addUserRow() {
    setUsers(prev => [...prev, { username: '', shell: '', source: 'manual' }])
  }

  function removeUserRow(idx: number) {
    setUsers(prev => prev.filter((_, i) => i !== idx))
  }

  function updateUser(idx: number, field: keyof UserEntry, value: string) {
    setUsers(prev => prev.map((row, i) => i === idx ? { ...row, [field]: value } : row))
  }

  const submittingRef = useRef(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submittingRef.current) return
    if (!nickname.trim()) {
      setError('Nickname is required')
      return
    }
    const validIps = ips.filter(ip => ip.ip_address.trim())
    if (validIps.length === 0) {
      setError('At least one address is required')
      return
    }
    for (const ip of validIps) {
      if (!isValidAddress(ip.ip_address.trim(), ip.addr_type)) {
        setError(`"${ip.ip_address.trim()}" is not a valid ${ip.addr_type === 'hostname' ? 'hostname' : 'IP address'}`)
        return
      }
    }
    const validUsers = users.filter(u => u.username.trim())
    submittingRef.current = true
    setError(null)
    setLoading(true)
    try {
      const host = await createHost(opId, {
        nickname: nickname.trim(),
        comment: comment.trim() || null,
      })
      for (const ip of validIps) {
        await addHostIP(host.id, { ip_address: ip.ip_address.trim(), addr_type: ip.addr_type })
      }
      for (const u of validUsers) {
        await createHostUser(host.id, {
          username: u.username.trim(),
          shell: u.shell.trim() || null,
          source: u.source,
        })
      }
      onSuccess()
    } catch {
      setError('Failed to create host. Please try again.')
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
          placeholder="e.g. web01, dc01"
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
        <label>IPs / Hostnames</label>
        <div className={styles.ipList}>
          {ips.map((ip, idx) => (
            <div key={idx} className={styles.ipRow}>
              <select
                value={ip.addr_type}
                onChange={e => updateAddrType(idx, e.target.value as IPEntry['addr_type'])}
                className={styles.addrTypeSelect}
                disabled={loading}
              >
                <option value="ipv4">IPv4</option>
                <option value="ipv6">IPv6</option>
                <option value="hostname">Hostname</option>
              </select>
              <input
                type="text"
                value={ip.ip_address}
                onChange={e => updateIp(idx, e.target.value)}
                placeholder={ip.addr_type === 'hostname' ? 'e.g. myserver.example.com' : ip.addr_type === 'ipv6' ? 'e.g. ::1' : 'e.g. 10.0.0.1'}
                className={styles.ipMain}
                disabled={loading}
              />
              {ips.length > 1 && (
                <button
                  type="button"
                  className={styles.removeBtn}
                  onClick={() => removeIpRow(idx)}
                  disabled={loading}
                  aria-label="Remove address"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          <button type="button" className={styles.addRowBtn} onClick={addIpRow} disabled={loading}>
            + Add address
          </button>
        </div>
      </div>

      <div className={styles.field}>
        <label>Known Users</label>
        <div className={styles.ipList}>
          {users.map((u, idx) => (
            <div key={idx} className={styles.userRow}>
              <input
                type="text"
                value={u.username}
                onChange={e => updateUser(idx, 'username', e.target.value)}
                placeholder="username"
                className={styles.userUsername}
                disabled={loading}
              />
              <input
                type="text"
                value={u.shell}
                onChange={e => updateUser(idx, 'shell', e.target.value)}
                placeholder="shell (opt)"
                className={styles.userShell}
                disabled={loading}
              />
              <select
                value={u.source}
                onChange={e => updateUser(idx, 'source', e.target.value)}
                className={styles.userSource}
                disabled={loading}
              >
                {USER_SOURCES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
              <button
                type="button"
                className={styles.removeBtn}
                onClick={() => removeUserRow(idx)}
                disabled={loading}
                aria-label="Remove user"
              >
                ✕
              </button>
            </div>
          ))}
          <button type="button" className={styles.addRowBtn} onClick={addUserRow} disabled={loading}>
            + Add User
          </button>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.formActions}>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? 'Saving…' : 'Add Host'}
        </button>
      </div>
    </form>
  )
}

// ─── Shared helper ────────────────────────────────────────────────────────────

function credLabel(c: { name: string | null; cred_type: string; comment: string | null }): string {
  if (c.name) return c.name
  if (c.comment) return c.comment
  return c.cred_type === 'password' ? '[unnamed password]' : '[unnamed key]'
}

// ─── Credential form ──────────────────────────────────────────────────────────

const CRED_TYPES: { value: CreateCredentialRequest['cred_type']; label: string }[] = [
  { value: 'private_key', label: 'Private Key (SSH)' },
  { value: 'public_key', label: 'Public Key (SSH)' },
  { value: 'password', label: 'Password' },
]

function CredentialForm({
  opId,
  hosts,
  onSuccess,
}: {
  opId: string
  hosts: Host[]
  onSuccess: () => void
}) {
  const [credType, setCredType] = useState<CreateCredentialRequest['cred_type']>('private_key')
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [comment, setComment] = useState('')
  const [link, setLink] = useState(false)
  const [linkHostId, setLinkHostId] = useState('')
  const [linkUsername, setLinkUsername] = useState('')
  const [relationship, setRelationship] = useState<CreateCredentialLinkRequest['relationship_type']>('found_on_disk')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submittingRef = useRef(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submittingRef.current) return
    if (!value.trim()) {
      setError('Credential value is required')
      return
    }
    if (link && !linkHostId) {
      setError('Select a host for the link')
      return
    }
    submittingRef.current = true
    setError(null)
    setLoading(true)
    try {
      const cred = await createCredential(opId, {
        cred_type: credType,
        name: name.trim() || null,
        value: value.trim(),
        passphrase: passphrase.trim() || null,
        comment: comment.trim() || null,
      })
      if (link && linkHostId) {
        await createCredentialLink({
          credential_id: cred.id,
          host_id: linkHostId,
          username: linkUsername.trim() || null,
          relationship_type: relationship,
        })
      }
      onSuccess()
    } catch {
      setError('Failed to save credential. Please try again.')
    } finally {
      submittingRef.current = false
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.field}>
        <label>Type *</label>
        <select
          value={credType}
          onChange={e => setCredType(e.target.value as CreateCredentialRequest['cred_type'])}
          disabled={loading}
        >
          {CRED_TYPES.map(c => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label>Name</label>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. id_rsa for root@web01"
          disabled={loading}
        />
      </div>

      <div className={styles.field}>
        <label>Value *</label>
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder={credType !== 'password' ? '-----BEGIN OPENSSH PRIVATE KEY-----\n…' : 'Password value'}
          rows={credType !== 'password' ? 5 : 2}
          className={styles.codeArea}
          autoFocus
          disabled={loading}
        />
      </div>

      <div className={styles.row}>
        {credType === 'private_key' && (
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
      </div>

      {hosts.length > 0 && (
        <div className={styles.linkSection}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={link}
              onChange={e => setLink(e.target.checked)}
              disabled={loading}
            />
            Link to a host
          </label>

          {link && (
            <div className={styles.linkFields}>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label>Host *</label>
                  <select
                    value={linkHostId}
                    onChange={e => setLinkHostId(e.target.value)}
                    disabled={loading}
                  >
                    <option value="">— select a host —</option>
                    {hosts.map(h => (
                      <option key={h.id} value={h.id}>
                        {h.nickname}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={styles.field}>
                  <label>Username</label>
                  <input
                    type="text"
                    value={linkUsername}
                    onChange={e => setLinkUsername(e.target.value)}
                    placeholder="e.g. root, bob"
                    disabled={loading}
                  />
                </div>
              </div>

              <div className={styles.field}>
                <label>Relationship *</label>
                <select
                  value={relationship}
                  onChange={e => setRelationship(e.target.value as CreateCredentialLinkRequest['relationship_type'])}
                  disabled={loading}
                >
                  {RELATIONSHIP_TYPES.map(r => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
      )}

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.formActions}>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? 'Saving…' : 'Add Credential'}
        </button>
      </div>
    </form>
  )
}

// ─── Connection form ──────────────────────────────────────────────────────────

const CONN_TYPES: { value: CreateConnectionRequest['connection_type']; label: string }[] = [
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

function ConnectionForm({
  opId,
  hosts,
  credentials,
  onSuccess,
}: {
  opId: string
  hosts: Host[]
  credentials: Credential[]
  onSuccess: () => void
}) {
  const [srcHostId, setSrcHostId] = useState('')
  const [srcIp, setSrcIp] = useState('')
  const [srcUser, setSrcUser] = useState('')
  const [dstHostId, setDstHostId] = useState('')
  const [dstIp, setDstIp] = useState('')
  const [dstUser, setDstUser] = useState('')
  const [connType, setConnType] = useState<CreateConnectionRequest['connection_type']>('ssh')
  const [direction, setDirection] = useState<CreateConnectionRequest['direction_context']>('from_src_logs')
  const [authMethod, setAuthMethod] = useState<AuthMethod | ''>('')
  const [credentialId, setCredentialId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function handleSrcHostChange(id: string) {
    setSrcHostId(id)
    const h = hosts.find(h => h.id === id)
    setSrcIp(h && h.ips.length > 0 ? h.ips[0].ip_address : '')
  }

  function handleDstHostChange(id: string) {
    setDstHostId(id)
    const h = hosts.find(h => h.id === id)
    setDstIp(h && h.ips.length > 0 ? h.ips[0].ip_address : '')
  }

  const submittingRef = useRef(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (submittingRef.current) return
    const resolvedSrcIp = srcIp.trim() || (srcHostId ? (hosts.find(h => h.id === srcHostId)?.ips[0]?.ip_address ?? '') : '')
    const resolvedDstIp = dstIp.trim() || (dstHostId ? (hosts.find(h => h.id === dstHostId)?.ips[0]?.ip_address ?? '') : '')

    if (!resolvedSrcIp) {
      setError('Source IP is required (or select a known host with an IP)')
      return
    }
    if (!resolvedDstIp) {
      setError('Destination IP is required (or select a known host with an IP)')
      return
    }
    submittingRef.current = true
    setError(null)
    setLoading(true)
    try {
      await createConnection(opId, {
        src_host_id: srcHostId || null,
        src_ip: resolvedSrcIp,
        src_user: srcUser.trim() || null,
        dst_host_id: dstHostId || null,
        dst_ip: resolvedDstIp,
        dst_user: dstUser.trim() || null,
        connection_type: connType,
        direction_context: direction,
        auth_method: authMethod || null,
        credential_id: credentialId || null,
        source_file: 'manual',
      })
      onSuccess()
    } catch {
      setError('Failed to add connection. Please try again.')
    } finally {
      submittingRef.current = false
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
                  {h.nickname}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label>IP Address *</label>
            {srcHostId && (hosts.find(h => h.id === srcHostId)?.ips.length ?? 0) > 0 ? (
              <select value={srcIp} onChange={e => setSrcIp(e.target.value)} disabled={loading}>
                {hosts.find(h => h.id === srcHostId)!.ips.map(ip => (
                  <option key={ip.id} value={ip.ip_address}>{ip.ip_address}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={srcIp}
                onChange={e => setSrcIp(e.target.value)}
                placeholder="10.0.0.5"
                disabled={loading}
              />
            )}
          </div>
          <div className={styles.field}>
            <label>Username</label>
            <input
              type="text"
              value={srcUser}
              onChange={e => setSrcUser(e.target.value)}
              placeholder="bob"
              disabled={loading}
            />
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
                  {h.nickname}{h.ips.length > 0 ? ` (${h.ips[0].ip_address})` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.field}>
            <label>IP Address *</label>
            {dstHostId && (hosts.find(h => h.id === dstHostId)?.ips.length ?? 0) > 0 ? (
              <select value={dstIp} onChange={e => setDstIp(e.target.value)} disabled={loading}>
                {hosts.find(h => h.id === dstHostId)!.ips.map(ip => (
                  <option key={ip.id} value={ip.ip_address}>{ip.ip_address}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={dstIp}
                onChange={e => setDstIp(e.target.value)}
                placeholder="10.0.0.8"
                disabled={loading}
              />
            )}
          </div>
          <div className={styles.field}>
            <label>Username</label>
            <input
              type="text"
              value={dstUser}
              onChange={e => setDstUser(e.target.value)}
              placeholder="root"
              disabled={loading}
            />
          </div>
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label>Connection Type</label>
          <select value={connType} onChange={e => setConnType(e.target.value as CreateConnectionRequest['connection_type'])} disabled={loading}>
            {CONN_TYPES.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label>Evidence Source</label>
          <select value={direction} onChange={e => setDirection(e.target.value as CreateConnectionRequest['direction_context'])} disabled={loading}>
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
            {AUTH_METHODS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        {(authMethod === 'publickey' || authMethod === 'password') && (
          <div className={styles.field}>
            <label>{authMethod === 'publickey' ? 'Private Key Used' : 'Password Used'}</label>
            <select value={credentialId} onChange={e => setCredentialId(e.target.value)} disabled={loading}>
              <option value="">— none / unknown —</option>
              {credentials
                .filter(c => authMethod === 'publickey' ? c.cred_type === 'private_key' : c.cred_type === 'password')
                .map(c => (
                  <option key={c.id} value={c.id}>{credLabel(c)}</option>
                ))}
            </select>
          </div>
        )}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.formActions}>
        <button type="submit" className={styles.btnPrimary} disabled={loading}>
          {loading ? 'Saving…' : 'Add Connection'}
        </button>
      </div>
    </form>
  )
}

// ─── Top-level ManualEntryForm ─────────────────────────────────────────────────

const FORM_TYPES: { value: FormType; label: string }[] = [
  { value: 'host', label: 'Host' },
  { value: 'credential', label: 'Credential' },
  { value: 'connection', label: 'Connection' },
]

export default function ManualEntryForm({ opId, hosts, credentials, onSuccess }: Props) {
  const [formType, setFormType] = useState<FormType>('host')
  const [resetKey, setResetKey] = useState(0)

  const handleSuccess = useCallback(() => {
    setResetKey(k => k + 1)
    onSuccess()
  }, [onSuccess])

  return (
    <div className={styles.root}>
      <div className={styles.typeSelector}>
        {FORM_TYPES.map(ft => (
          <button
            key={ft.value}
            type="button"
            className={`${styles.typeBtn} ${formType === ft.value ? styles.typeBtnActive : ''}`}
            onClick={() => setFormType(ft.value)}
          >
            {ft.label}
          </button>
        ))}
      </div>

      <div key={`${formType}-${resetKey}`}>
        {formType === 'host' && (
          <HostForm opId={opId} onSuccess={handleSuccess} />
        )}
        {formType === 'credential' && (
          <CredentialForm opId={opId} hosts={hosts} onSuccess={handleSuccess} />
        )}
        {formType === 'connection' && (
          <ConnectionForm opId={opId} hosts={hosts} credentials={credentials} onSuccess={handleSuccess} />
        )}
      </div>
    </div>
  )
}
