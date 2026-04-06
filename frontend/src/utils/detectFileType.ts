import type { UploadFileType } from '../types'

/**
 * Best-effort file type detection from filename alone.
 * Returns null when ambiguous — user must select manually.
 */
export function detectFileType(filename: string): UploadFileType | null {
  const base = filename.toLowerCase().replace(/^.*\//, '') // strip any path prefix

  if (base === 'authorized_keys') return 'authorized_keys'
  if (base === 'known_hosts') return 'known_hosts'
  if (base === 'passwd') return 'passwd'
  if (base === 'wtmp' || base === 'btmp') return 'wtmp'
  if (base === '.bash_history' || base === 'bash_history') return 'bash_history'
  if (base === 'auth.log' || base === 'secure' || base === 'secure.log' || base === 'auth.log.1') return 'auth_log'
  if (base === 'ssh_config') return 'ssh_config'

  // Private key patterns
  if (
    base === 'id_rsa' || base === 'id_ed25519' || base === 'id_ecdsa' ||
    base === 'id_dsa' || base.endsWith('.pem') || base.endsWith('.key')
  ) {
    return 'private_key'
  }

  // Public key
  if (base.endsWith('.pub')) return 'public_key'

  return null
}
