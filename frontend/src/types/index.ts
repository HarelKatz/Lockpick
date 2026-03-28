/**
 * TypeScript interfaces matching backend Pydantic schemas.
 */

export interface Operation {
  id: string
  name: string
  description: string | null
  created_at: string
}

export interface HostIP {
  id: string
  host_id: string
  ip_address: string
  source: 'manual' | 'parsed'
  first_seen_at: string
}

export interface HostUser {
  id: string
  host_id: string
  username: string
  shell: string | null
  home_dir: string | null
  source: 'manual' | 'passwd_file' | 'authorized_keys' | 'log_evidence'
  created_at: string
}

export interface Host {
  id: string
  op_id: string
  nickname: string
  comment: string | null
  created_at: string
  ips: HostIP[]
  users: HostUser[]
}

export interface Credential {
  id: string
  op_id: string
  cred_type: 'password' | 'private_key' | 'public_key'
  value: string
  fingerprint: string | null   // inferred by backend
  key_type: string | null      // inferred by backend
  passphrase: string | null
  comment: string | null
  created_at: string
}

export interface CredentialLink {
  id: string
  credential_id: string
  host_id: string
  username: string | null
  host_user_id: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source: string | null
}

export type AuthMethod = 'publickey' | 'password' | 'keyboard-interactive' | 'hostbased' | 'unknown'

export interface ConnectionRecord {
  id: string
  op_id: string
  src_host_id: string | null
  src_ip: string
  src_user: string | null
  dst_host_id: string | null
  dst_ip: string
  dst_user: string | null
  connection_type: 'ssh' | 'scp' | 'rsync' | 'sftp' | 'ssh_copy_id' | 'unknown'
  direction_context: 'from_src_logs' | 'from_dst_logs'
  auth_method: AuthMethod | null
  credential_id: string | null
  timestamp: string | null
  raw_line: string | null
  source_file: string
  created_at: string
}

// ─── Request bodies ───────────────────────────────────────────────────────────

export interface UpdateOperationRequest {
  name?: string
  description?: string | null
}

export interface UpdateCredentialRequest {
  value?: string
  passphrase?: string | null
  comment?: string | null
}

export interface UpdateCredentialLinkRequest {
  username?: string | null
  relationship_type?: CredentialLink['relationship_type']
  file_source?: string | null
}

export interface UpdateConnectionRequest {
  src_host_id?: string | null
  src_ip?: string
  src_user?: string | null
  dst_host_id?: string | null
  dst_ip?: string
  dst_user?: string | null
  connection_type?: ConnectionRecord['connection_type']
  direction_context?: ConnectionRecord['direction_context']
  auth_method?: AuthMethod | null
  credential_id?: string | null
  timestamp?: string | null
  raw_line?: string | null
  source_file?: string
}

export interface CreateOperationRequest {
  name: string
  description?: string | null
}

export interface CreateHostRequest {
  nickname: string
  comment?: string | null
}

export interface CreateHostIPRequest {
  ip_address: string
  source?: 'manual' | 'parsed'
}

export interface CreateCredentialRequest {
  cred_type: 'password' | 'private_key' | 'public_key'
  value: string
  passphrase?: string | null   // for encrypted private keys
  comment?: string | null
}

export interface CreateCredentialLinkRequest {
  credential_id: string
  host_id: string
  username?: string | null
  host_user_id?: string | null
  relationship_type: 'found_on_disk' | 'authorized_key' | 'accepted_password' | 'used_in_connection'
  file_source?: string | null
}

export interface CreateHostUserRequest {
  username: string
  shell?: string | null
  home_dir?: string | null
  source?: HostUser['source']
}

export interface CreateConnectionRequest {
  src_host_id?: string | null
  src_ip: string
  src_user?: string | null
  dst_host_id?: string | null
  dst_ip: string
  dst_user?: string | null
  connection_type: 'ssh' | 'scp' | 'rsync' | 'sftp' | 'ssh_copy_id' | 'unknown'
  direction_context: 'from_src_logs' | 'from_dst_logs'
  auth_method?: AuthMethod | null
  credential_id?: string | null
  timestamp?: string | null
  raw_line?: string | null
  source_file: string
}
